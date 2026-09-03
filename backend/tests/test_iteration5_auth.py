"""Iteration 5 — JWT cookie auth, per-user isolation, streak freeze, record-token flow."""
import os
import re
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base_url.rstrip("/") + "/api"


def _creds():
    p = Path("/app/memory/test_credentials.md")
    c = p.read_text(encoding="utf-8")
    e = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?email(?:\*\*)?\s*:\s*`?([^`\s]+)', c)
    pw = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?password(?:\*\*)?\s*:\s*`?([^`\s]+)', c)
    assert e and pw, "credentials file unreadable"
    return e.group(1), pw.group(1)


ADMIN_EMAIL, ADMIN_PASSWORD = _creds()


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    return s


def _register(email=None, password="testpass123", name="TEST_User"):
    s = requests.Session()
    email = email or f"test-{uuid.uuid4().hex[:10]}@example.com"
    r = s.post(f"{BASE}/auth/register", json={"email": email, "password": password, "name": name})
    return s, email, r


@pytest.fixture(scope="module")
def user_a():
    s, email, r = _register()
    assert r.status_code == 200, r.text[:300]
    return {"s": s, "email": email, "user": r.json()["user"], "token": r.json().get("access_token")}


@pytest.fixture(scope="module")
def user_b():
    s, email, r = _register()
    assert r.status_code == 200, r.text[:300]
    return {"s": s, "email": email, "user": r.json()["user"], "token": r.json().get("access_token")}


# ---------------- Auth basics ----------------
class TestAuth:
    def test_register_sets_cookies_and_returns_user(self):
        s, email, r = _register()
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["user"]["email"] == email
        assert data["user"]["role"] == "user"
        assert "password_hash" not in data["user"]
        assert "_id" not in data["user"]
        assert "access_token" in s.cookies and "refresh_token" in s.cookies
        # httpOnly + secure flags
        for c in s.cookies:
            if c.name in ("access_token", "refresh_token"):
                assert c.has_nonstandard_attr("HttpOnly") or c.has_nonstandard_attr("httponly"), f"{c.name} not httpOnly"
                assert c.secure, f"{c.name} not secure"
        me = s.get(f"{BASE}/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == email

    def test_register_duplicate_409(self, user_a):
        _, _, r = _register(email=user_a["email"])
        assert r.status_code == 409, r.text[:200]

    def test_register_short_password_422(self):
        _, _, r = _register(password="123")
        assert r.status_code == 422

    def test_register_bad_email_422(self):
        _, _, r = _register(email="not-an-email")
        assert r.status_code == 422

    def test_login_success(self):
        s = requests.Session()
        r = s.post(f"{BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        assert r.json()["user"]["email"] == ADMIN_EMAIL
        assert r.json()["user"]["role"] == "admin"
        assert "access_token" in s.cookies

    def test_login_wrong_password_401(self):
        r = requests.post(f"{BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-pass"})
        assert r.status_code == 401

    def test_login_unknown_email_401(self):
        r = requests.post(f"{BASE}/auth/login", json={"email": "nobody-xyz@example.com", "password": "whatever"})
        assert r.status_code == 401

    def test_me_without_cookie_401(self):
        r = requests.get(f"{BASE}/auth/me")
        assert r.status_code == 401

    def test_me_bearer_fallback(self, user_a):
        r = requests.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {user_a['token']}"})
        assert r.status_code == 200
        assert r.json()["email"] == user_a["email"]

    def test_me_invalid_token_401(self):
        r = requests.get(f"{BASE}/auth/me", headers={"Authorization": "Bearer garbage.token.value"})
        assert r.status_code == 401

    def test_refresh_issues_new_access_token(self):
        s, _, r = _register()
        assert r.status_code == 200
        old = s.cookies.get("access_token")
        # drop access token, keep refresh
        s.cookies.clear(domain=list(s.cookies.list_domains())[0], path="/", name="access_token")
        assert s.get(f"{BASE}/auth/me").status_code == 401
        rr = s.post(f"{BASE}/auth/refresh")
        assert rr.status_code == 200, rr.text[:200]
        assert s.cookies.get("access_token")
        assert s.get(f"{BASE}/auth/me").status_code == 200
        assert old is not None

    def test_refresh_without_cookie_401(self):
        r = requests.post(f"{BASE}/auth/refresh")
        assert r.status_code == 401

    def test_access_token_not_accepted_as_refresh(self, user_a):
        s = requests.Session()
        s.cookies.set("refresh_token", user_a["token"], domain=base_url.split("//")[1])
        r = s.post(f"{BASE}/auth/refresh")
        assert r.status_code == 401

    def test_logout_clears_cookies(self):
        s, _, r = _register()
        assert s.get(f"{BASE}/auth/me").status_code == 200
        lo = s.post(f"{BASE}/auth/logout")
        assert lo.status_code == 200 and lo.json()["ok"] is True
        assert not s.cookies.get("access_token")
        assert s.get(f"{BASE}/auth/me").status_code == 401

    def test_bcrypt_hash_format(self):
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import dotenv_values as dv
        env = dv("/app/backend/.env")

        async def _get():
            cli = AsyncIOMotorClient(env["MONGO_URL"])
            u = await cli[env["DB_NAME"]].users.find_one({"email": ADMIN_EMAIL})
            cli.close()
            return u
        u = asyncio.get_event_loop().run_until_complete(_get()) if False else asyncio.run(_get())
        assert u is not None, "admin user not seeded"
        assert u["password_hash"].startswith("$2b$"), u["password_hash"][:8]

    def test_brute_force_lockout(self):
        """Playbook requirement: lockout after 5 failed attempts."""
        s, email, r = _register(password="bfpass12345")
        assert r.status_code == 200
        codes = []
        for _ in range(6):
            rr = requests.post(f"{BASE}/auth/login", json={"email": email, "password": "definitely-wrong"})
            codes.append(rr.status_code)
        assert 423 in codes or 429 in codes, f"no lockout after 6 failures, codes={codes}"


# ---------------- No unauthenticated data leaks ----------------
class TestNoPublicLeak:
    @pytest.mark.parametrize("method,path", [
        ("GET", "/lectures"),
        ("POST", "/lectures"),
        ("GET", "/stats"),
        ("GET", "/glossary/all"),
        ("GET", "/review/due"),
        ("GET", "/review/stats"),
        ("POST", "/review/seed-now"),
        ("GET", "/digest/preview"),
        ("POST", "/digest/send"),
        ("POST", "/streak/freeze"),
        ("POST", "/auth/logout"),
    ])
    def test_requires_auth(self, method, path):
        r = requests.request(method, f"{BASE}{path}", json={})
        assert r.status_code == 401, f"{method} {path} -> {r.status_code} (leak?)"


# ---------------- Per-user isolation ----------------
class TestIsolation:
    def test_new_user_has_no_lectures(self, user_b):
        r = user_b["s"].get(f"{BASE}/lectures")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_lectures_scoped_and_cross_access_404(self, user_a, user_b):
        r = user_a["s"].post(f"{BASE}/lectures", json={
            "title": "TEST_Isolation Lecture", "source_type": "paste",
            "transcript": "Photosynthesis converts light energy into chemical energy."})
        assert r.status_code == 200, r.text[:300]
        lec = r.json()
        assert lec["user_id"] == user_a["user"]["id"]

        ids_a = [x["id"] for x in user_a["s"].get(f"{BASE}/lectures").json()]
        ids_b = [x["id"] for x in user_b["s"].get(f"{BASE}/lectures").json()]
        assert lec["id"] in ids_a
        assert lec["id"] not in ids_b

        # user_b cannot read / summarize / delete
        assert user_b["s"].get(f"{BASE}/lectures/{lec['id']}").status_code == 404
        assert user_b["s"].post(f"{BASE}/lectures/{lec['id']}/summary").status_code == 404
        assert user_b["s"].post(f"{BASE}/lectures/{lec['id']}/record-token").status_code == 404
        assert user_b["s"].delete(f"{BASE}/lectures/{lec['id']}").status_code == 404
        # patch transcript with other user's access token -> 403
        pr = requests.patch(f"{BASE}/lectures/{lec['id']}/transcript",
                            json={"transcript": "hack"},
                            headers={"Authorization": f"Bearer {user_b['token']}"})
        assert pr.status_code == 403, pr.status_code
        # owner still sees original transcript
        assert "Photosynthesis" in user_a["s"].get(f"{BASE}/lectures/{lec['id']}").json()["transcript"]
        # cleanup
        assert user_a["s"].delete(f"{BASE}/lectures/{lec['id']}").status_code == 200
        assert user_a["s"].get(f"{BASE}/lectures/{lec['id']}").status_code == 404

    def test_admin_sees_migrated_legacy_lectures(self, admin):
        r = admin.get(f"{BASE}/lectures")
        assert r.status_code == 200
        titles = [x["title"] for x in r.json()]
        for expected in ("Test SR flow", "Supply and Demand E2E", "Photosynthesis Basics"):
            assert expected in titles, f"missing legacy lecture '{expected}' — titles={titles}"


# ---------------- Stats & streak freeze ----------------
class TestStreakFreeze:
    def test_stats_shape(self, admin):
        r = admin.get(f"{BASE}/stats")
        assert r.status_code == 200
        d = r.json()
        for k in ("streak", "reviewed_today", "can_freeze", "next_freeze_in_days", "freeze_dates",
                  "lectures", "tests", "attempts", "avg_score"):
            assert k in d, f"missing {k}"
        assert isinstance(d["streak"], int)
        assert isinstance(d["can_freeze"], bool)
        assert isinstance(d["freeze_dates"], list)

    def test_freeze_once_per_week(self):
        s, _, r = _register()
        assert r.status_code == 200
        st = s.get(f"{BASE}/stats").json()
        assert st["can_freeze"] is True
        assert st["freeze_dates"] == []

        f1 = s.post(f"{BASE}/streak/freeze")
        assert f1.status_code == 200, f1.text[:200]
        d = f1.json()
        assert d["ok"] is True and d["covers_days"] == 2
        from datetime import datetime, timezone
        assert d["frozen_on"] == datetime.now(timezone.utc).date().isoformat()

        f2 = s.post(f"{BASE}/streak/freeze")
        assert f2.status_code == 400, f2.status_code
        assert "уже использована на этой неделе" in f2.json().get("detail", "")

        st2 = s.get(f"{BASE}/stats").json()
        assert st2["can_freeze"] is False
        assert st2["next_freeze_in_days"] == 7
        assert d["frozen_on"] in st2["freeze_dates"]


# ---------------- Record token flow ----------------
class TestRecordToken:
    def test_record_token_and_mobile_flow(self, user_a):
        s = user_a["s"]
        lec = s.post(f"{BASE}/lectures", json={
            "title": "TEST_Record Token Flow", "source_type": "mic", "transcript": ""}).json()
        lid = lec["id"]
        try:
            rt = s.post(f"{BASE}/lectures/{lid}/record-token")
            assert rt.status_code == 200, rt.text[:200]
            body = rt.json()
            assert body["token"] and f"/m/{lid}" in body["url"]
            token = body["token"]

            # mobile GET with valid token (no cookies)
            m = requests.get(f"{BASE}/lectures/{lid}/mobile", params={"t": token})
            assert m.status_code == 200, m.text[:200]
            assert m.json()["title"] == "TEST_Record Token Flow"
            assert "_id" not in m.json()

            # missing / invalid token
            assert requests.get(f"{BASE}/lectures/{lid}/mobile").status_code == 401
            assert requests.get(f"{BASE}/lectures/{lid}/mobile", params={"t": "bad"}).status_code == 401
            # user access token is not a record token
            assert requests.get(f"{BASE}/lectures/{lid}/mobile",
                                params={"t": user_a["token"]}).status_code == 403

            # PATCH transcript with record token only
            p1 = requests.patch(f"{BASE}/lectures/{lid}/transcript",
                                json={"transcript": "chunk one.", "append": True, "duration_sec": 12},
                                headers={"Authorization": f"Bearer {token}"})
            assert p1.status_code == 200, p1.text[:200]
            p2 = requests.patch(f"{BASE}/lectures/{lid}/transcript",
                                json={"transcript": "chunk two.", "append": True, "duration_sec": 24},
                                headers={"Authorization": f"Bearer {token}"})
            assert p2.status_code == 200
            got = s.get(f"{BASE}/lectures/{lid}").json()
            assert got["transcript"] == "chunk one. chunk two."
            assert got["duration_sec"] == 24

            # record token for lecture X cannot patch lecture Y
            other = s.post(f"{BASE}/lectures", json={"title": "TEST_Other", "transcript": "x"}).json()
            pr = requests.patch(f"{BASE}/lectures/{other['id']}/transcript",
                                json={"transcript": "nope"},
                                headers={"Authorization": f"Bearer {token}"})
            assert pr.status_code == 403, pr.status_code
            s.delete(f"{BASE}/lectures/{other['id']}")

            # unauthenticated patch
            assert requests.patch(f"{BASE}/lectures/{lid}/transcript",
                                  json={"transcript": "nope"}).status_code == 401
        finally:
            s.delete(f"{BASE}/lectures/{lid}")


# ---------------- Public endpoints still public ----------------
class TestPublicConfig:
    def test_config_public(self):
        r = requests.get(f"{BASE}/config")
        assert r.status_code == 200
        assert "llm_mode" in r.json()

    def test_root_public(self):
        r = requests.get(f"{BASE}/")
        assert r.status_code == 200
        assert r.json()["service"] == "upsidestudy"
