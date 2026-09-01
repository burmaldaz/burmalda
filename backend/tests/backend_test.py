"""Iteration 2 backend tests: DeepSeek config/fallback, Whisper endpoint,
spaced repetition loop. Plus regression on lecture/test/grade flow."""
import os
import subprocess
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
    "Today we discuss photosynthesis. Photosynthesis is the process by which "
    "green plants convert light energy into chemical energy stored in glucose. "
    "It occurs in the chloroplasts, specifically in the thylakoid membranes for "
    "the light-dependent reactions and in the stroma for the Calvin cycle. "
    "Chlorophyll a is the primary pigment absorbing red and blue light. "
    "The overall equation is six CO2 plus six H2O plus light yields C6H12O6 plus "
    "six O2. In the light reactions, photosystem II splits water, releasing oxygen, "
    "and produces ATP via chemiosmosis and NADPH. The Calvin cycle then fixes "
    "carbon dioxide using the enzyme RuBisCO. Factors limiting the rate include "
    "light intensity, CO2 concentration and temperature. C4 and CAM plants have "
    "adaptations to reduce photorespiration in hot dry climates."
) * 2


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="class")
def lecture(client):
    """Class-scoped because pytest.ini uses xdist --dist loadscope (classes
    run on different workers, so session state cannot be shared)."""
    r = client.post(f"{API}/lectures", json={
        "title": "TEST_SR_iter2", "source_type": "paste",
        "transcript": TRANSCRIPT})
    assert r.status_code == 200, r.text
    lec = r.json()
    yield lec
    client.delete(f"{API}/lectures/{lec['id']}")


@pytest.fixture(scope="class")
def lecture_with_test(client, lecture):
    s = client.post(f"{API}/lectures/{lecture['id']}/summary", timeout=180)
    assert s.status_code == 200, s.text
    t = client.post(f"{API}/lectures/{lecture['id']}/test", timeout=180)
    assert t.status_code == 200, t.text
    lecture["test"] = t.json()
    return lecture


# ---- Config ----
class TestConfig:
    def test_config(self, client):
        r = client.get(f"{API}/config")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["llm_mode"] == "deepseek", d
        assert d["is_mocked"] is False, d


# ---- AI summary + test generation (DeepSeek w/ Gemini fallback) ----
class TestAI:
    def test_summary(self, client, lecture):
        r = client.post(f"{API}/lectures/{lecture['id']}/summary", timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["summary"] and len(d["summary"]) > 200, len(d.get("summary") or "")
        # Russian (cyrillic) content check
        cyr = sum(1 for c in d["summary"] if "\u0400" <= c <= "\u04FF")
        assert cyr > 100, f"not enough cyrillic: {cyr}"
        assert isinstance(d["key_points"], list) and len(d["key_points"]) >= 3
        lecture["summary"] = d["summary"]

    def test_generate_test(self, client, lecture):
        r = client.post(f"{API}/lectures/{lecture['id']}/test", timeout=180)
        assert r.status_code == 200, r.text
        t = r.json()
        assert t["lecture_id"] == lecture["id"]
        qs = t["questions"]
        assert len(qs) == 8, f"expected 8 questions, got {len(qs)}"
        types = [q["type"] for q in qs]
        assert types.count("mcq") == 4 and types.count("tf") == 2 and types.count("short") == 2, types
        for q in qs:
            if q["type"] == "mcq":
                assert q["answer"].strip().upper() in list("ABCD"), q
                assert q["options"] and len(q["options"]) == 4
            if q["type"] == "tf":
                assert q["answer"] in ("True", "False"), q
            cyr = sum(1 for c in q["prompt"] if "\u0400" <= c <= "\u04FF")
            assert cyr > 3, q["prompt"]
        lecture["test"] = t


# ---- Spaced repetition ----
class TestSpacedRepetition:
    def test_grade_all_wrong_creates_review_items(self, client, lecture_with_test):
        t = lecture_with_test["test"]
        answers = [{"question_id": q["id"], "response": "ZZZ_wrong"} for q in t["questions"]]
        r = client.post(f"{API}/tests/{t['id']}/grade", json={"answers": answers}, timeout=60)
        assert r.status_code == 200, r.text
        att = r.json()
        assert att["score"] == 0 and att["correct"] == 0

        # seed-now so items become due
        s = client.post(f"{API}/review/seed-now")
        assert s.status_code == 200, s.text
        assert "updated" in s.json()

        due = client.get(f"{API}/review/due")
        assert due.status_code == 200, due.text
        items = [i for i in due.json() if i["lecture_id"] == lecture_with_test["id"]]
        assert len(items) == 8, f"expected 8 review items, got {len(items)}"
        for i in items:
            assert i["interval_days"] == 1
            assert i["last_result"] == "wrong"
            assert i["misses"] >= 1
            assert "_id" not in i
        lecture_with_test["review_items"] = items

    def test_review_stats(self, client, lecture_with_test):
        r = client.get(f"{API}/review/stats")
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(d) == {"total", "due"}
        assert isinstance(d["total"], int) and isinstance(d["due"], int)
        assert d["total"] >= 8 and d["due"] >= 7

    def test_review_answer_correct_doubles_interval(self, client, lecture_with_test):
        item = next(i for i in lecture_with_test["review_items"] if i["question"]["type"] == "mcq")
        r = client.post(f"{API}/review/{item['id']}/answer",
                        json={"response": item["question"]["answer"]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["is_correct"] is True, d
        assert d["next_due_days"] == 2, d
        assert d["correct_answer"] == item["question"]["answer"]
        # no longer due
        due = client.get(f"{API}/review/due").json()
        assert item["id"] not in [i["id"] for i in due]

    def test_review_answer_wrong_resets(self, client, lecture_with_test):
        item = next(i for i in lecture_with_test["review_items"]
                    if i["question"]["type"] == "tf")
        r = client.post(f"{API}/review/{item['id']}/answer",
                        json={"response": "definitely-not-the-answer"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["is_correct"] is False, d
        assert d["next_due_days"] == 1, d

    def test_short_answer_cyrillic_is_graded_correct(self, client, lecture_with_test):
        """BUG: _norm() strips all Cyrillic ([^a-z0-9]) so a short answer that
        exactly matches the expected Russian phrase is graded WRONG."""
        item = next(i for i in lecture_with_test["review_items"]
                    if i["question"]["type"] == "short")
        exact = item["question"]["answer"]
        r = client.post(f"{API}/review/{item['id']}/answer",
                        json={"response": exact})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["is_correct"] is True, (
            f"exact answer {exact!r} graded wrong -> Cyrillic stripped by _norm")

    def test_grade_all_correct_scores_100(self, client, lecture_with_test):
        """BUG surface: submitting every correct answer should score 100."""
        t = lecture_with_test["test"]
        answers = [{"question_id": q["id"], "response": q["answer"]}
                   for q in t["questions"]]
        r = client.post(f"{API}/tests/{t['id']}/grade",
                        json={"answers": answers}, timeout=60)
        assert r.status_code == 200, r.text
        att = r.json()
        wrong = [g for g in att["graded"] if not g["is_correct"]]
        assert att["score"] == 100, (
            f"score={att['score']}, wrongly-marked: "
            f"{[(w['response']) for w in wrong]}")

    def test_review_answer_404(self, client):
        r = client.post(f"{API}/review/does-not-exist/answer", json={"response": "x"})
        assert r.status_code == 404, r.text

    def test_review_answer_validation(self, client, lecture_with_test):
        item = lecture_with_test["review_items"][0]
        r = client.post(f"{API}/review/{item['id']}/answer", json={})
        assert r.status_code == 422, r.text


# ---- Whisper transcription ----
class TestTranscribeAudio:
    def test_get_not_allowed(self, client):
        r = client.get(f"{API}/transcribe-audio")
        assert r.status_code == 405, r.text

    def test_post_without_file(self, client):
        r = requests.post(f"{API}/transcribe-audio")
        assert r.status_code == 422, r.text

    def test_post_real_audio(self):
        if not _has_ffmpeg():
            pytest.skip("ffmpeg unavailable; cannot generate audio")
        path = "/tmp/test_tone.mp3"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             "sine=frequency=440:duration=2", "-c:a", "libmp3lame", path],
            check=True, capture_output=True)
        with open(path, "rb") as f:
            r = requests.post(f"{API}/transcribe-audio",
                              files={"file": ("test_tone.mp3", f, "audio/mpeg")},
                              timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "text" in d and isinstance(d["text"], str)


def _has_ffmpeg() -> bool:
    from shutil import which
    return which("ffmpeg") is not None


# ---- Answer normalization (unit level) ----
class TestNormalization:
    def test_norm_preserves_cyrillic(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from server import _norm
        # BUG: regex [^a-z0-9] deletes every Cyrillic char, so any Russian
        # short answer normalizes to "" and is always graded incorrect.
        assert _norm("Хлорофилл") == "хлорофилл", repr(_norm("Хлорофилл"))

    def test_cyrillic_short_answer_marked_correct(self):
        """End-to-end proof against live data: a due short-answer review item
        with a Cyrillic expected answer, answered exactly, must be correct."""
        requests.post(f"{API}/review/seed-now")
        due = requests.get(f"{API}/review/due").json()
        cyr_items = [i for i in due if i["question"]["type"] == "short"
                     and any("\u0400" <= c <= "\u04FF"
                             for c in i["question"]["answer"])]
        if not cyr_items:
            pytest.skip("no due short item with Cyrillic answer available")
        item = cyr_items[0]
        exact = item["question"]["answer"]
        r = requests.post(f"{API}/review/{item['id']}/answer",
                          json={"response": exact})
        assert r.status_code == 200, r.text
        assert r.json()["is_correct"] is True, (
            f"exact Cyrillic answer {exact!r} graded WRONG")
