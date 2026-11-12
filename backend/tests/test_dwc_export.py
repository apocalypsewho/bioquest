"""Darwin Core export of field observations and EXIF stripping of uploaded photos."""
import csv
import io
import json
import os
import tempfile
import zipfile
from types import SimpleNamespace
from xml.dom import minidom

os.environ.setdefault("BIOQUEST_DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ.setdefault("BIOQUEST_STORAGE_DIR", tempfile.mkdtemp())

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.main import app  # noqa: E402
from app.services import dwc  # noqa: E402
from app.services.geo import haversine_km  # noqa: E402
from app.services.media import strip_image_metadata  # noqa: E402


def obs(**kw):
    import datetime as dt
    base = dict(id=7, client_uuid="abc-123", lat=-13.16312, lon=-72.54501, accuracy_m=8.0, altitude_m=2430.0,
                coordinate_privacy="public", observed_at=dt.datetime(2026, 8, 14, 9, 30, tzinfo=dt.timezone.utc),
                created_at=None, notes="Under\tbark\nof Polylepis", habitat="Polylepis forest", microhabitat="bark",
                temperature_c=11.5, method="visual observation", individual_count=2, sex=None, measurements={},
                morphology={}, observer="J. Explorer", is_demo=False, inat_observation_id=None,
                taxon_name="Oreobates sp.", taxon_key="inat:1", id_status="user_identified", ai_suggestion=None,
                mission_id=None, expedition_id=None, photos=[SimpleNamespace(id=3)])
    base.update(kw)
    return SimpleNamespace(**base)


TAXON = {"classification": {"kingdom": "Animalia", "class": "Amphibia", "family": "Strabomantidae"},
         "rank": "Genus", "common_name": None, "is_sensitive": False}


def test_exact_mode_keeps_position():
    r = dwc.observation_to_dwc(obs(coordinate_privacy="approximate"), dwc.ExportOptions(coordinates="exact"), TAXON)
    assert (r["decimalLatitude"], r["decimalLongitude"]) == (-13.16312, -72.54501)
    assert r["coordinateUncertaintyInMeters"] == 8 and r["minimumElevationInMeters"] == 2430
    assert r["dataGeneralizations"] == "" and r["family"] == "Strabomantidae"
    assert r["eventDate"] == "2026-08-14T09:30:00+00:00" and r["habitat"] == "Polylepis forest; bark"
    assert r["occurrenceID"] == "urn:bioquest:observation:abc-123"


def test_public_mode_generalises_and_true_point_stays_inside_uncertainty():
    for privacy, sensitive, cell in [("approximate", False, 0.1), ("public", True, 0.2), ("approximate", True, 0.2)]:
        o = obs(coordinate_privacy=privacy)
        r = dwc.observation_to_dwc(o, dwc.ExportOptions(), {**TAXON, "is_sensitive": sensitive})
        assert r["decimalLatitude"] != o.lat and str(cell) in r["dataGeneralizations"]
        assert r["minimumElevationInMeters"] is None and r["informationWithheld"]
        d_m = haversine_km(o.lat, o.lon, r["decimalLatitude"], r["decimalLongitude"]) * 1000
        assert d_m <= r["coordinateUncertaintyInMeters"]


def test_public_mode_private_record_has_no_location_or_media():
    r = dwc.observation_to_dwc(obs(coordinate_privacy="private"), dwc.ExportOptions(base_url="https://x"), TAXON)
    assert r["decimalLatitude"] is None and r["decimalLongitude"] is None and r["geodeticDatum"] == ""
    assert "private" in r["informationWithheld"] and r["associatedMedia"] == ""


def test_public_record_untouched_and_media_linked():
    r = dwc.observation_to_dwc(obs(), dwc.ExportOptions(base_url="https://bq.example/"), TAXON)
    assert r["decimalLatitude"] == -13.16312 and r["associatedMedia"] == "https://bq.example/api/photos/3"


def test_demo_rows_are_flagged():
    r = dwc.observation_to_dwc(obs(is_demo=True), dwc.ExportOptions(), None)
    assert r["occurrenceRemarks"].startswith("[DEMO DATA") and json.loads(r["dynamicProperties"])["isDemo"]


def test_archive_structure_and_tsv_alignment():
    rows = [dwc.observation_to_dwc(obs(), dwc.ExportOptions(), TAXON)]
    z = zipfile.ZipFile(io.BytesIO(dwc.dwca_zip(rows, dwc.eml_xml("T & <t>", "Me", rows, dwc.ExportOptions(), "p"))))
    assert sorted(z.namelist()) == ["eml.xml", "meta.xml", "occurrence.txt"]
    minidom.parseString(z.read("eml.xml"))
    meta = minidom.parseString(z.read("meta.xml"))
    n_fields = len(meta.getElementsByTagName("field"))
    lines = z.read("occurrence.txt").decode().rstrip("\n").split("\n")
    assert all(len(line.split("\t")) == n_fields + 1 for line in lines)
    assert "Under bark of Polylepis" in lines[1]


def _jpeg_with_gps() -> bytes:
    im = Image.new("RGB", (40, 20), (10, 120, 30))
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 90° CW
    gps = exif.get_ifd(0x8825)
    gps[2] = (13.0, 9.0, 47.0)
    gps[1] = "S"
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif.tobytes())
    return buf.getvalue()


def test_strip_image_metadata_removes_gps_and_applies_orientation():
    raw = _jpeg_with_gps()
    assert Image.open(io.BytesIO(raw)).getexif().get_ifd(0x8825)
    clean = Image.open(io.BytesIO(strip_image_metadata(raw, "image/jpeg")))
    assert not clean.getexif() and "exif" not in clean.info
    assert clean.size == (20, 40)  # orientation baked into the pixels
    assert strip_image_metadata(b"ID3audio", "audio/mpeg") == b"ID3audio"


def test_export_endpoints_end_to_end():
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"username": "dwc_user", "password": "secret1"}).json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        base = {"lat": -12.04, "lon": -77.03, "accuracy_m": 5, "taxon_name": "Zonotrichia capensis",
                "observed_at": "2026-05-02T07:00:00Z"}
        a = c.post("/api/observations", headers=h, json={**base, "coordinate_privacy": "approximate"}).json()
        c.post("/api/observations", headers=h, json={**base, "coordinate_privacy": "private"})
        c.post("/api/observations", headers=h, json={**base, "is_demo": True})
        up = c.post(f"/api/observations/{a['id']}/photos", headers=h,
                    files={"file": ("p.jpg", _jpeg_with_gps(), "image/jpeg")}).json()
        assert not Image.open(io.BytesIO(c.get(up["url"]).content)).getexif()

        res = c.get("/api/observations/export?format=csv", headers=h)
        assert res.status_code == 200 and res.headers["x-records"] == "2"  # DEMO excluded by default
        rows = list(csv.DictReader(io.StringIO(res.text)))
        assert rows[0]["decimalLatitude"] != "-12.04" and rows[1]["decimalLatitude"] == ""
        assert rows[0]["associatedMedia"].endswith(f"/api/photos/{up['id']}")

        exact = list(csv.DictReader(io.StringIO(
            c.get("/api/observations/export?format=csv&coordinates=exact", headers=h).text)))
        assert exact[1]["decimalLatitude"] == "-12.04"

        z = c.get("/api/observations/export?include_demo=true&license=cc0", headers=h)
        assert z.headers["content-type"] == "application/zip" and z.headers["x-records"] == "3"
        eml = zipfile.ZipFile(io.BytesIO(z.content)).read("eml.xml").decode()
        assert "publicdomain/zero" in eml and "DEMO" in eml

        pid = c.post("/api/projects", headers=h, json={"name": "Lomas de Lima", "description": ""}).json()["id"]
        c.post(f"/api/projects/{pid}/observations", headers=h, json={"observation_id": a["id"]})
        p = c.get(f"/api/projects/{pid}/export?format=csv", headers=h)
        assert p.headers["x-records"] == "1" and "bioquest-lomas-de-lima-dwc.csv" in p.headers["content-disposition"]
        assert list(csv.DictReader(io.StringIO(p.text)))[0]["dataGeneralizations"]

        assert c.get("/api/observations/export").status_code == 401
