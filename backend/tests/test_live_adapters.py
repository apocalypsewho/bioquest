"""Live adapters tested against mocked HTTP (respx). Verifies URLs/params we send and how we parse responses."""
import httpx
import pytest
import respx

from app.services import hub
from app.services.occurrence_qc import QCConfig, run_qc

from . import fixtures as F

INAT = "https://api.inaturalist.org/v1"
GBIF = "https://api.gbif.org/v1"


@pytest.fixture(autouse=True)
def no_throttle():
    hub.inat.api.min_interval_s = 0
    hub.gbif.client.min_interval_s = 0


@respx.mock
@pytest.mark.asyncio
async def test_search_merges_sources():
    respx.get(f"{INAT}/taxa/autocomplete").mock(return_value=httpx.Response(200, json=F.INAT_AUTOCOMPLETE))
    respx.get(f"{GBIF}/species/suggest").mock(return_value=httpx.Response(200, json=F.GBIF_SUGGEST))
    out = await hub.search_taxa("Testgenus", "live")
    keys = [r["key"] for r in out["results"]]
    assert keys == ["inat:900001", "gbif:7000001"]
    assert out["provenance"] == "LIVE DATA"
    assert out["results"][1]["classification"]["family"] == "Testidae"


@respx.mock
@pytest.mark.asyncio
async def test_occurrences_qc_and_cross_source_dedup():
    respx.get(f"{INAT}/taxa/900001").mock(return_value=httpx.Response(200, json=F.INAT_TAXON))
    respx.get(f"{GBIF}/species/match").mock(return_value=httpx.Response(200, json=F.GBIF_MATCH))
    obs_route = respx.get(f"{INAT}/observations").mock(return_value=httpx.Response(200, json=F.INAT_OBSERVATIONS))

    def gbif_occ(request):
        if request.url.params.get("hasCoordinate") == "false":
            return httpx.Response(200, json=F.GBIF_NO_COORD)
        return httpx.Response(200, json=F.GBIF_OCCURRENCES)

    respx.get(f"{GBIF}/occurrence/search").mock(side_effect=gbif_occ)
    data = await hub.occurrences("inat:900001", "live")
    assert data["keys"] == {"inat": "inat:900001", "gbif": "gbif:7000001"}
    assert obs_route.calls[0].request.url.params["geo"] == "true"
    assert data["source_info"]["gbif"]["without_coordinates"] == 7
    recs = {r.uid: r for r in data["records"]}
    assert len(recs) == 7
    run_qc(data["records"], QCConfig(target_keys=data["keys"], target_rank="species"))
    assert recs["inaturalist:101"].qc_status == "VALID"
    assert recs["inaturalist:102"].qc_status == "QUESTIONABLE"
    assert recs["inaturalist:103"].qc_status == "EXCLUDED"  # captive + casual
    assert recs["gbif:2"].qc_status == "EXCLUDED"  # 0,0
    assert recs["gbif:3"].duplicate_of == "inaturalist:101"
    assert recs["gbif:4"].qc_status == "EXCLUDED"  # country mismatch
    assert recs["gbif:1"].qc_status == "VALID"
    assert recs["inaturalist:101"].photo_url.endswith("medium.jpg")


@respx.mock
@pytest.mark.asyncio
async def test_upstream_error_is_reported_not_faked():
    respx.get(f"{INAT}/taxa/autocomplete").mock(return_value=httpx.Response(503))
    respx.get(f"{GBIF}/species/suggest").mock(side_effect=httpx.ConnectError("down"))
    out = await hub.search_taxa("x y", "live")
    assert out["results"] == []
    assert {e["service"] for e in out["errors"]} == {"iNaturalist", "GBIF"}


@respx.mock
@pytest.mark.asyncio
async def test_gbif_facets():
    respx.get(f"{GBIF}/occurrence/search").mock(return_value=httpx.Response(200, json=F.GBIF_FACETS))
    f = await hub.gbif.facets("7000001")
    assert f["countries"][0] == {"code": "PE", "count": 10}
    assert f["years"] == [1987, 2019]


def test_inat_oauth_url(monkeypatch):
    s = hub.inat.s
    monkeypatch.setattr(s, "inat_client_id", "abc")
    url = hub.inat.authorize_url("st")
    assert url.startswith("https://www.inaturalist.org/oauth/authorize?")
    assert "response_type=code" in url and "client_id=abc" in url
