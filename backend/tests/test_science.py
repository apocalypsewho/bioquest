import numpy as np
import pytest

from app.services.demo import DemoDataProvider
from app.services.environment import DemoEnvironmentalProvider, WorldClimProvider
from app.services.geo import Grid
from app.services.occurrence_qc import QCConfig, run_qc
from app.services.priority import score
from app.services.privacy import public_coords
from app.services.sampling import compute_gap
from app.services.sdm import INSUFFICIENT_MSG, DistributionModelService, SDMConfig
from app.services.types import OccurrenceRecord


def rec(i, lat, lon, **kw):
    return OccurrenceRecord(source="gbif", source_record_id=str(i), scientific_name="X y", taxon_key="gbif:1",
                            lat=lat, lon=lon, **kw)


def test_qc_never_drops_records():
    recs = [rec(1, None, None), rec(2, 95, 10), rec(3, -12.123, -75.456), rec(4, -12.123, -75.456),
            rec(5, -12.5, -75.5, uncertainty_m=50_000)]
    recs[2].event_date = recs[3].event_date = "2020-01-01"
    s = run_qc(recs, QCConfig())
    assert s["total"] == 5 and len(recs) == 5
    assert [r.qc_status for r in recs] == ["EXCLUDED", "EXCLUDED", "VALID", "EXCLUDED", "EXCLUDED"]
    assert all(r.qc_reasons for r in recs if r.qc_status != "VALID")


def test_expected_country():
    r = rec(1, -12.12, -75.45, country_code="BO")
    run_qc([r], QCConfig(expected_countries=["PE"]))
    assert r.qc_status == "QUESTIONABLE"


def test_insufficient_data_produces_no_map():
    recs = [rec(i, -12 - i * 0.05, -75 - i * 0.05) for i in range(6)]
    run_qc(recs, QCConfig())
    res = DistributionModelService().run(recs, DemoEnvironmentalProvider(), SDMConfig())
    assert res.status == "insufficient_data" and res.message == INSUFFICIENT_MSG and not res.layers


def test_sdm_demo_runs_three_models_and_ensemble():
    demo = DemoDataProvider()
    recs = demo.occurrences("demo:2")
    run_qc(recs, QCConfig(target_keys={"demo": "demo:2"}))
    res = DistributionModelService().run(recs, DemoEnvironmentalProvider(), SDMConfig(n_background=1500))
    assert res.status == "completed"
    assert {"maxent", "random_forest", "glm", "ensemble", "agreement"} <= set(res.layers)
    ens = res.layers["ensemble"]
    assert np.nanmin(ens) >= 0 and np.nanmax(ens) <= 1
    for a in ("maxent", "random_forest", "glm"):
        assert res.metrics[a]["spatial_cv"]["auc"]["mean"] > 0.5
    assert any("not probability" in w for w in res.warnings)


def test_gap_distinguishes_unsampled_from_poor():
    grid = Grid([0, 0, 1, 1], 0.5)
    # Top-left cell heavily sampled, the rest empty
    records = [{"lat": 0.9, "lon": 0.1 + i * 1e-3, "observer": f"o{i % 5}", "taxon": f"t{i % 3}", "year": 2000 + i % 12}
               for i in range(200)]
    g = compute_gap(records, grid)
    assert g["gap"][0, 0] < 40
    assert g["class"][1, 1] == "UNDER-SAMPLED"


def test_priority_is_transparent_and_renormalised():
    s = score({"suitability": None, "model_agreement": None, "sampling_gap": 80, "biodiversity_potential": 60,
               "accessibility": 40, "taxonomic_uncertainty": None})
    used = [c for c in s["components"] if c["used"]]
    assert len(used) == 3 and abs(sum(c["effective_weight"] for c in used) - 1) < 1e-6
    assert s["score"] == round((0.25 * 80 + 0.15 * 60 + 0.10 * 40) / 0.5)


def test_privacy():
    assert public_coords(-12.123456, -75.98765, "private")[:2] == (None, None)
    lat, lon, _ = public_coords(-12.123456, -75.98765, "approximate")
    assert abs(lat - (-12.15)) < 1e-9 and abs(lon - (-75.95)) < 1e-9
    assert public_coords(-12.1, -75.9, "private", is_owner=True)[:2] == (-12.1, -75.9)
    assert public_coords(-12.123, -75.987, "public", sensitive=True)[2].startswith("generalised 0.2")


def test_worldclim_provider_reads_geotiffs(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    tr = from_origin(-80, 0, 0.5, 0.5)  # 20x20 cells covering -80..-70, -10..0
    for name, val in [("bio_1", 10.0), ("bio_4", 200.0), ("bio_12", 900.0), ("bio_15", 50.0), ("elev", 3000.0)]:
        arr = np.full((20, 20), val, dtype="float32")
        arr[:, 10:] += 100  # east half differs
        with rasterio.open(tmp_path / f"wc2.1_10m_{name}.tif", "w", driver="GTiff", height=20, width=20, count=1,
                           dtype="float32", crs="EPSG:4326", transform=tr, nodata=-3.4e38) as dst:
            dst.write(arr, 1)
    p = WorldClimProvider(str(tmp_path))
    assert p.available()[0]
    env = p.grid(Grid([-78, -8, -72, -2], 0.5))
    assert env["bio1"][0, 0] == 10.0 and env["bio1"][0, -1] == 110.0
    assert env["slope"].shape == env["elev"].shape
