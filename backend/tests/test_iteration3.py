"""Iteration 3 backend tests: config extras, glossary, digest, transcript append."""
import os
import time

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

TRANSCRIPT = (
    "Today we discuss photosynthesis. Chlorophyll inside the chloroplast absorbs "
    "photons and drives the light-dependent reactions, producing ATP and NADPH. "
    "The Calvin cycle then fixes carbon dioxide into glucose using the enzyme "
    "RuBisCO. Stomata regulate gas exchange, and transpiration pulls water up the "
    "xylem. Cellular respiration in the mitochondria later oxidizes glucose to "
    "release energy. We also compare C3, C4 and CAM plants and their adaptation "
    "to arid environments, where photorespiration becomes a costly side reaction."
)


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def created_ids():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(client, created_ids):
    yield
    for lid in created_ids:
        client.delete(f"{API}/lectures/{lid}", timeout=60)


@pytest.fixture(scope="module")
def lecture(client, created_ids):
    r = client.post(f"{API}/lectures", json={
        "title": "TEST_Glossary Iter3", "source_type": "paste",
        "transcript": TRANSCRIPT,
    }, timeout=60)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    created_ids.append(data["id"])
    return data


# ---- /api/config ----
class TestConfigIter3:
    def test_config_fields(self, client):
        r = client.get(f"{API}/config", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["llm_mode"] == "deepseek", d
        assert d["email_enabled"] is True, d
        assert d["digest_email"] == "workspace67676752@gmail.com", d
        assert "sun 20:00 UTC" in d["digest_schedule"], d
        assert d.get("is_mocked") is False, d


# ---- transcript append (used by /m/{id}) ----
class TestTranscriptAppend:
    def test_append_chunk(self, client, created_ids):
        r = client.post(f"{API}/lectures", json={
            "title": "TEST_Append Iter3", "source_type": "mic", "transcript": "First part.",
        }, timeout=60)
        assert r.status_code in (200, 201)
        lid = r.json()["id"]
        created_ids.append(lid)

        r2 = client.patch(f"{API}/lectures/{lid}/transcript", json={
            "transcript": "Second part.", "append": True, "duration_sec": 12,
        }, timeout=60)
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert "First part." in body["transcript"]
        assert "Second part." in body["transcript"]

        g = client.get(f"{API}/lectures/{lid}", timeout=30)
        assert g.status_code == 200
        got = g.json()
        assert "First part." in got["transcript"] and "Second part." in got["transcript"]
        assert got.get("duration_sec") == 12
        assert "_id" not in got

    def test_replace_not_append(self, client, created_ids):
        r = client.post(f"{API}/lectures", json={
            "title": "TEST_Replace Iter3", "source_type": "paste", "transcript": "Old text.",
        }, timeout=60)
        lid = r.json()["id"]
        created_ids.append(lid)
        r2 = client.patch(f"{API}/lectures/{lid}/transcript",
                          json={"transcript": "New text.", "append": False}, timeout=60)
        assert r2.status_code == 200
        assert r2.json()["transcript"].strip() == "New text."

    def test_append_404(self, client):
        r = client.patch(f"{API}/lectures/does-not-exist/transcript",
                         json={"transcript": "x", "append": True}, timeout=30)
        assert r.status_code == 404


# ---- glossary ----
class TestGlossary:
    def test_generate_glossary(self, client, lecture):
        r = client.post(f"{API}/lectures/{lecture['id']}/glossary", timeout=180)
        assert r.status_code == 200, r.text
        terms = r.json()["terms"]
        assert 8 <= len(terms) <= 15, f"expected 8-15 terms, got {len(terms)}"
        for t in terms:
            assert set(["term", "translation", "definition"]).issubset(t.keys()), t
            assert t["term"].strip() and t["translation"].strip()
            assert t["definition"].strip(), t
            # translation should contain Cyrillic
            assert any("\u0400" <= c <= "\u04FF" for c in t["translation"]), t

    def test_glossary_persisted_on_lecture(self, client, lecture):
        g = client.get(f"{API}/lectures/{lecture['id']}", timeout=30)
        assert g.status_code == 200
        doc = g.json()
        assert isinstance(doc.get("glossary"), list)
        assert len(doc["glossary"]) >= 8, doc.get("glossary")
        assert "term" in doc["glossary"][0]

    def test_glossary_terms_appear_in_transcript(self, client, lecture):
        g = client.get(f"{API}/lectures/{lecture['id']}", timeout=30).json()
        lower = g["transcript"].lower()
        hits = [t["term"] for t in g["glossary"] if t["term"].lower() in lower]
        # highlighting depends on exact-form terms; report if most are missing
        assert len(hits) >= max(1, len(g["glossary"]) // 2), (
            f"only {len(hits)}/{len(g['glossary'])} terms literally present: "
            f"{[t['term'] for t in g['glossary']]}"
        )

    def test_glossary_404(self, client):
        r = client.post(f"{API}/lectures/nope/glossary", timeout=60)
        assert r.status_code == 404

    def test_glossary_400_no_transcript(self, client, created_ids):
        r = client.post(f"{API}/lectures", json={"title": "TEST_Empty Iter3",
                                                "source_type": "paste", "transcript": ""}, timeout=60)
        lid = r.json()["id"]
        created_ids.append(lid)
        r2 = client.post(f"{API}/lectures/{lid}/glossary", timeout=60)
        assert r2.status_code == 400, r2.text

    def test_glossary_all_aggregated(self, client, lecture):
        r = client.get(f"{API}/glossary/all", timeout=60)
        assert r.status_code == 200
        terms = r.json()["terms"]
        assert isinstance(terms, list) and len(terms) >= 8
        lowered = [t["term"].lower() for t in terms]
        assert len(lowered) == len(set(lowered)), "duplicate terms in /glossary/all"
        assert lowered == sorted(lowered), "terms not sorted"
        for t in terms:
            assert t.get("lecture_id") and t.get("lecture_title")
        assert lecture["id"] in {t["lecture_id"] for t in terms}


# ---- digest ----
class TestDigest:
    def test_preview(self, client):
        r = client.get(f"{API}/digest/preview", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("subject", "html", "new_lectures", "due_count", "avg_score"):
            assert k in d, d.keys()
        assert d["subject"].startswith("upsidestudy"), d["subject"]
        assert isinstance(d["new_lectures"], int)
        assert isinstance(d["due_count"], int)
        assert isinstance(d["avg_score"], int)
        assert "<!doctype html>" in d["html"].lower()
        assert "upsidestudy" in d["html"]

    def test_send_empty_body(self, client):
        r = client.post(f"{API}/digest/send", json={}, timeout=120)
        if r.status_code == 200:
            d = r.json()
            assert d["ok"] is True
            assert d["to"] == "workspace67676752@gmail.com"
            assert d.get("email_id"), d
        else:
            assert r.status_code == 502, f"unexpected {r.status_code}: {r.text[:300]}"
            assert "Resend" in r.text

    def test_send_no_body_at_all(self, client):
        """Frontend axios always sends {}; verify raw no-body behaviour too."""
        time.sleep(1)
        r = requests.post(f"{API}/digest/send", timeout=120)
        assert r.status_code in (200, 422, 502), r.text[:300]
        if r.status_code == 422:
            pytest.skip("no-body POST returns 422 (body required) - frontend sends {} so OK")

    def test_send_explicit_recipient(self, client):
        time.sleep(1)
        r = client.post(f"{API}/digest/send",
                        json={"to": "workspace67676752@gmail.com"}, timeout=120)
        assert r.status_code in (200, 502), r.text[:300]
        if r.status_code == 200:
            assert r.json()["to"] == "workspace67676752@gmail.com"
