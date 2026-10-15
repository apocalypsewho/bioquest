"""End-to-end DEMO flow through the HTTP API (section 36 of the brief)."""
import os
import tempfile
import time

os.environ["BIOQUEST_DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["BIOQUEST_STORAGE_DIR"] = tempfile.mkdtemp()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


def test_full_demo_flow():
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"username": "explorer", "password": "secret1"}).json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        # 3-4 explore
        ex = c.post("/api/explore", json={"mode": "demo", "lat": -11.95, "lon": -75.25}).json()
        assert ex["status"] == "ok" and ex["provenance"] == "DEMO DATA"
        assert ex["zone"]["priority"]["score"] > 0
        # 5 mission from explore zone
        m = c.post("/api/missions", json={"zone": ex["zone"]}, headers=h).json()
        assert m["code"].isdigit()
        # 6-7 species + occurrences
        t = c.get("/api/taxa/search", params={"q": "Demoquestia", "mode": "demo"}).json()["results"][0]
        occ = c.get(f"/api/taxa/{t['key']}/occurrences", params={"mode": "demo"}).json()
        assert occ["qc"]["EXCLUDED"] > 0 and occ["qc"]["total"] == len(occ["records"])
        # 8-10 model
        rid = c.post("/api/models", json={"taxon_key": t["key"], "mode": "demo"}).json()["id"]
        for _ in range(120):
            run = c.get(f"/api/models/{rid}").json()
            if run["status"] != "running":
                break
            time.sleep(0.5)
        assert run["status"] == "completed", run["warnings"]
        assert {"maxent", "random_forest", "glm", "ensemble"} <= set(run["layers"])
        cell = c.get(f"/api/models/{rid}/cell", params={"lat": -11.95, "lon": -75.25}).json()
        assert cell["inside"]
        # 11-12 gap + priority
        z = c.post(f"/api/models/{rid}/zone", json={"lat": -11.95, "lon": -75.25}).json()
        assert z["status"] == "ok"
        assert z["zone"]["sampling"]["sampling_gap_score"] >= 0
        assert len(z["zone"]["priority"]["components"]) == 6
        m2 = c.post("/api/missions", json={"zone": z["zone"]}, headers=h).json()
        assert m2["target_name"] == t["scientific_name"]
        # 13 observation (+ photo) inside an expedition
        e = c.post("/api/expeditions", json={"mission_id": m2["id"], "is_demo": True}, headers=h).json()
        c.post(f"/api/expeditions/{e['id']}/track", json={"points": [[-75.25, -11.95, "t0"], [-75.24, -11.94, "t1"]]},
               headers=h)
        o = c.post("/api/observations", json={"taxon_name": "Demoquestia sp.", "lat": -11.94, "lon": -75.24,
                                              "expedition_id": e["id"], "is_demo": True, "habitat": "scrub"},
                   headers=h).json()
        ph = c.post(f"/api/observations/{o['id']}/photos", files={"file": ("x.png", PNG, "image/png")}, headers=h)
        assert ph.status_code == 200
        d = c.post("/api/discoveries", json={"observation_id": o["id"], "category": "range_extension",
                                             "evidence_level": 5, "rationale": "outside known range"}, headers=h).json()
        assert d["evidence_level"] == 3  # self-reported discoveries are capped
        fin = c.post(f"/api/expeditions/{e['id']}/finish", headers=h).json()
        assert fin["observations"] == 1 and fin["distance_km"] > 0
        # demo observations can never be sent to iNaturalist
        assert c.post(f"/api/observations/{o['id']}/inat-submit", json={"consent": True}, headers=h).status_code == 400
        # 14 profile
        p = c.get("/api/profile", headers=h).json()
        assert p["stats"]["observations"] == 1 and p["user"]["xp"] > 0
        # offline sync idempotency
        payload = {"observations": [{"client_uuid": "abc-1", "taxon_name": "X", "is_demo": True}]}
        r1 = c.post("/api/observations/sync", json=payload, headers=h).json()
        r2 = c.post("/api/observations/sync", json=payload, headers=h).json()
        assert r1["synced"][0]["created"] and not r2["synced"][0]["created"]


def test_live_model_refuses_without_real_env_layers():
    with TestClient(app) as c:
        r = c.post("/api/models", json={"taxon_key": "inat:1", "mode": "live"})
        assert r.status_code == 409
