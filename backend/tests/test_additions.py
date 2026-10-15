"""GAM, target-group background, country QC, land cover, roads (Overpass), literature, anomaly screening,
projects, iNaturalist validation refresh and mission guidance."""
import os
import tempfile
import time

os.environ.setdefault("BIOQUEST_DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ.setdefault("BIOQUEST_STORAGE_DIR", tempfile.mkdtemp())

import httpx  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
import respx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import hub  # noqa: E402
from app.services.access import AccessibilityProvider, nearest_from_overpass, road_access_score  # noqa: E402
from app.services.anomaly import assess  # noqa: E402
from app.services.environment import get_provider  # noqa: E402
from app.services.landcover import WorldCoverProvider, tile_name  # noqa: E402
from app.services.literature import LiteratureProvider  # noqa: E402
from app.services.occurrence_qc import QCConfig, run_qc  # noqa: E402
from app.services.sampling_guide import recommendations  # noqa: E402
from app.services.sdm import DistributionModelService, SDMConfig  # noqa: E402
from app.services.types import OccurrenceRecord  # noqa: E402


def rec(i, lat, lon, **kw):
    return OccurrenceRecord(source="gbif", source_record_id=str(i), scientific_name="X y", taxon_key="gbif:1",
                            lat=lat, lon=lon, **kw)


def test_country_check_flags_mismatch_and_fills_missing():
    recs = [rec(1, -12.0464, -77.0428, country_code="BO"),  # Lima reported as Bolivia
            rec(2, -12.1211, -77.0297),                       # no country → derived PE
            rec(3, -16.4897, -68.1193, country_code="BO")]    # La Paz, consistent
    s = run_qc(recs, QCConfig())
    assert recs[0].qc_status == "QUESTIONABLE" and "nearest GeoNames place is in PE" in recs[0].qc_reasons[0]
    assert recs[1].derived_country_code == "PE" and recs[1].qc_status == "VALID"
    assert recs[2].qc_status == "VALID"
    assert any("country check" in n for n in s["notes"])
    # expected-country check uses the derived country when none was reported
    recs2 = [rec(4, -12.0464, -77.0428)]
    run_qc(recs2, QCConfig(expected_countries=["EC"]))
    assert recs2[0].qc_status == "QUESTIONABLE"


def test_gam_and_target_group_background():
    recs = hub.demo.occurrences("demo:1")
    run_qc(recs, QCConfig(target_keys={"demo": "demo:1"}))
    svc, prov = DistributionModelService(), get_provider("demo")
    cfg = SDMConfig(algorithms=("gam",), background="target_group", n_folds=3)
    bbox = svc.choose_grid([r for r in recs if r.qc_status == "VALID"], prov, cfg).bbox
    cfg.bias_points = [(r["lat"], r["lon"]) for r in hub.demo.effort_records(bbox)]
    cfg.bias_source = "DEMO effort"
    res = svc.run(recs, prov, cfg)
    assert res.status == "completed"
    assert res.metrics["background"]["method"] == "target_group"
    assert res.metrics["gam"]["spatial_cv"]["auc"]["mean"] > 0.6
    assert any("TARGET-GROUP" in w for w in res.warnings)
    # background cells come only from cells with target-group records
    assert res.n_background <= len({(round(a, 2), round(b, 2)) for a, b in cfg.bias_points})


def test_worldcover_summary(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    name = tile_name(-11.95, -75.25)
    assert name == "ESA_WorldCover_10m_2021_v200_S12W078_Map.tif"
    arr = np.full((300, 300), 10, dtype="uint8")
    arr[:, 150:] = 30
    with rasterio.open(tmp_path / name, "w", driver="GTiff", height=300, width=300, count=1, dtype="uint8",
                       crs="EPSG:4326", transform=from_origin(-75.26, -11.94, 0.0001, 0.0001)) as dst:
        dst.write(arr, 1)
    lc = WorldCoverProvider(str(tmp_path)).summary(-11.955, -75.245, 300)
    classes = {c["class"] for c in lc["composition"]}
    assert classes == {"Tree cover", "Grassland"} and "WorldCover" in lc["source"]
    assert WorldCoverProvider(str(tmp_path / "none")).summary(-11.95, -75.25) is None


OVERPASS = {"elements": [
    {"type": "way", "id": 1, "tags": {"highway": "track", "name": "Camino"},
     "geometry": [{"lat": -12.00, "lon": -75.30}, {"lat": -12.00, "lon": -75.20}]},
    {"type": "way", "id": 2, "tags": {"highway": "path"},
     "geometry": [{"lat": -11.96, "lon": -75.26}, {"lat": -11.95, "lon": -75.26}]},
    {"type": "way", "id": 3, "tags": {"highway": "construction"}, "geometry": [{"lat": -11.95, "lon": -75.25}]},
]}


def test_overpass_parsing():
    best = nearest_from_overpass(OVERPASS, -11.95, -75.25)
    assert best["road"]["osm_way_id"] == 1 and 5.4 < best["road"]["distance_km"] < 5.7
    assert best["trail"]["osm_way_id"] == 2 and best["trail"]["distance_km"] < 1.2


@respx.mock
@pytest.mark.asyncio
async def test_overpass_live_and_failure():
    acc = AccessibilityProvider()
    acc.client.min_interval_s = 0
    route = respx.post("https://overpass-api.de/api/interpreter").mock(return_value=httpx.Response(200, json=OVERPASS))
    out = await acc.nearest_ways("live", -11.95, -75.25)
    assert out["status"] == "ok" and out["provenance"] == "LIVE DATA"
    assert b"around%3A10000" in route.calls[0].request.content
    assert road_access_score(out) > 80
    respx.post("https://overpass-api.de/api/interpreter").mock(return_value=httpx.Response(504, text="timeout"))
    bad = await acc.nearest_ways("live", -10.0, -75.0)
    assert bad["status"] == "error" and road_access_score(bad) is None


@respx.mock
@pytest.mark.asyncio
async def test_literature_sources():
    lit = LiteratureProvider()
    lit.gbif.min_interval_s = lit.crossref.min_interval_s = 0
    g = respx.get("https://api.gbif.org/v1/literature/search").mock(return_value=httpx.Response(200, json={
        "results": [{"title": "A survey", "year": 2020, "authors": [{"lastName": "Pérez"}],
                     "source": "Zootaxa", "identifiers": {"doi": "10.1/abc"}}]}))
    respx.get("https://api.crossref.org/works").mock(return_value=httpx.Response(200, json={"message": {"items": [
        {"DOI": "10.1/ABC", "title": ["A survey"], "issued": {"date-parts": [[2020]]}},
        {"DOI": "10.2/xyz", "title": ["Another"], "author": [{"family": "Lee"}], "container-title": ["J"]}]}}))
    out = await lit.search("Testus testus", "7000001")
    assert g.calls[0].request.url.params["gbifTaxonKey"] == "7000001"
    assert [i["doi"].lower() for i in out["items"]] == ["10.1/abc", "10.2/xyz"]  # deduplicated by DOI
    respx.get("https://api.crossref.org/works").mock(return_value=httpx.Response(500))
    out2 = await lit.search("Testus testus")
    assert out2["errors"] and out2["errors"][0]["service"] == "Crossref" and out2["items"]


def test_anomaly_flags_are_suggestions():
    known = [{"lat": -12 + i * 0.01, "lon": -75, "elevation_m": 3000 + i} for i in range(20)]
    grid = {"bbox": [-76, -13, -74, -11], "res": 1.0, "width": 2, "height": 2, "values": [0.1, 0.9, 0.9, 0.9]}
    out = assess(-11.5, -73.0, 4500, known, {"grid": grid, "threshold": 0.5, "run_id": 1})
    assert "POTENTIAL RANGE EXTENSION" in out["flags"] and "UNUSUAL OBSERVATION" in out["flags"]
    assert out["suggested_discovery_category"] == "range_extension" and "not a certification" in out["disclaimer"]
    near = assess(-12.0, -75.0, 3005, known, None)
    assert near["flags"] == []


def test_guidance():
    g = recommendations("Amphibia", "Tree cover")
    assert g["group"] == "Amphibia" and "edge" in g["habitat_tip"] and g["label"].startswith("GUIDANCE")
    assert recommendations(None, None)["group"] == "all taxa"


def test_projects_assess_refresh_and_guidance():
    with TestClient(app) as c:
        def user(name):
            r = c.post("/api/auth/register", json={"username": name, "password": "secret1"})
            if r.status_code != 200:
                r = c.post("/api/auth/login", json={"username": name, "password": "secret1"})
            return {"Authorization": f"Bearer {r.json()['token']}"}

        a, b = user("ana_add"), user("beto_add")
        # mission guidance (DEMO species zone target → Arachnida methods)
        ex = c.post("/api/explore", json={"mode": "demo", "lat": -11.95, "lon": -75.25}).json()
        assert ex["zone"]["road_access"]["provenance"] == "DEMO DATA"
        zone = {**ex["zone"], "target": {"key": "demo:1", "scientific_name": "Demoquestia andina"}}
        m = c.post("/api/missions", json={"zone": zone}, headers=a).json()
        assert m["guidance"]["group"] == "Arachnida"
        # observation + projects
        o = c.post("/api/observations", json={"taxon_name": "Demoquestia andina", "lat": -11.9512, "lon": -75.2534,
                                              "is_demo": True, "coordinate_privacy": "approximate"}, headers=a).json()
        p = c.post("/api/projects", json={"name": "Valle DEMO"}, headers=a).json()
        assert c.post(f"/api/projects/{p['id']}/members", json={"username": "nobody"}, headers=a).status_code == 404
        c.post(f"/api/projects/{p['id']}/members", json={"username": "beto_add"}, headers=a)
        c.post(f"/api/projects/{p['id']}/observations", json={"observation_id": o["id"]}, headers=a)
        seen = c.get(f"/api/projects/{p['id']}", headers=b).json()
        shared = seen["observations"][0]
        assert shared["shared_by"] == "ana_add" and shared["lat"] != -11.9512  # generalised for non-owner
        assert c.post(f"/api/projects/{p['id']}/members", json={"username": "ana_add"}, headers=b).status_code == 403
        assert [x["name"] for x in c.get("/api/projects", headers=b).json()] == ["Valle DEMO"]
        # anomaly screening against DEMO records (far from the known range)
        far = c.post("/api/observations", json={"taxon_name": "Demoquestia andina", "lat": -10.2, "lon": -73.1,
                                                "is_demo": True}, headers=a).json()
        r = c.post(f"/api/observations/{far['id']}/assess", headers=a).json()
        assert "POTENTIAL RANGE EXTENSION" in r["flags"] and r["provenance"] == "MODEL OUTPUT"
        # compare: DEMO literature is explicitly empty
        cmp_ = c.get("/api/compare", params={"keys": "demo:1", "mode": "demo"}, headers=a).json()
        assert cmp_["taxa"][0]["literature"]["status"] == "demo"
        # iNaturalist validation refresh (mocked iNat): research grade → validation XP once
        live = c.post("/api/observations", json={"taxon_name": "Testus testus", "lat": -12.1, "lon": -75.1},
                      headers=a).json()
        from app.db import SessionLocal
        from app.models import Observation

        db = SessionLocal()
        db.get(Observation, live["id"]).inat_observation_id = 555
        db.commit()
        db.close()
        hub.inat.api.min_interval_s = 0
        with respx.mock(assert_all_called=False) as rx:
            rx.route(host="testserver").pass_through()
            rx.get("https://api.inaturalist.org/v1/observations/555").mock(return_value=httpx.Response(
                200, json={"results": [{"id": 555, "quality_grade": "research", "identifications_count": 3,
                                        "community_taxon": {"name": "Testus testus"}}]}))
            r1 = c.post(f"/api/observations/{live['id']}/inat-refresh", headers=a).json()
            r2 = c.post(f"/api/observations/{live['id']}/inat-refresh", headers=a).json()
        assert r1["quality_grade"] == "research" and r1["xp_awarded"] == 100 and r2["xp_awarded"] == 0
        assert r1["observation"]["id_status"] == "research_grade"


def test_model_with_gam_via_api():
    with TestClient(app) as c:
        rid = c.post("/api/models", json={"taxon_key": "demo:1", "mode": "demo", "model3": "gam",
                                          "background": "target_group"}).json()["id"]
        for _ in range(160):
            run = c.get(f"/api/models/{rid}").json()
            if run["status"] != "running":
                break
            time.sleep(0.5)
        assert run["status"] == "completed", run["warnings"]
        assert {"maxent", "random_forest", "gam", "ensemble"} <= set(run["layers"]) and "glm" not in run["layers"]
        assert run["metrics"]["background"]["method"] == "target_group"
