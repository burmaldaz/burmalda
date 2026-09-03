"""Iteration 6 backend tests: password reset (forgot/reset) + emergent Google session."""
import os
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
backend_env = dotenv_values("/app/backend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"
JWT_SECRET = backend_env["JWT_SECRET"]
ADMIN_EMAIL = "admin@upsidestudy.app"
ADMIN_PASSWORD = "admin1234"
LOG = "/var/log/supervisor/backend.err.log"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _tail_reset_token():
    """Grab the most recent reset link token from backend logs."""
    out = subprocess.run(["tail", "-n", "400", LOG], capture_output=True, text=True).stdout
    tokens = re.findall(r"\[reset\] link for [^:]+: \S*token=([A-Za-z0-9._\-]+)", out)
    return tokens[-1] if tokens else None


# ---- forgot-password ----

class TestForgotPassword:
    def test_forgot_known_email(self, client):
        r = client.post(f"{API}/auth/forgot-password", json={"email": ADMIN_EMAIL})
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}
        time.sleep(1)
        token = _tail_reset_token()
        assert token, "no reset link logged in backend logs"
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        assert payload["type"] == "reset"
        assert isinstance(payload["sub"], str)

    def test_forgot_unknown_email_no_leak(self, client):
        r = client.post(f"{API}/auth/forgot-password",
                        json={"email": "TEST_nobody_upside@example.com"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_forgot_invalid_email_422(self, client):
        r = client.post(f"{API}/auth/forgot-password", json={"email": "not-an-email"})
        assert r.status_code == 422

    def test_resend_delivery_attempt_logged(self, client):
        client.post(f"{API}/auth/forgot-password", json={"email": ADMIN_EMAIL})
        time.sleep(2)
        out = subprocess.run(["tail", "-n", "200", LOG], capture_output=True, text=True).stdout
        assert "[reset] mail sent to" in out or "[reset] send to" in out, \
            "no Resend delivery attempt logged"


# ---- reset-password ----

class TestResetPassword:
    def test_bad_token(self, client):
        r = client.post(f"{API}/auth/reset-password",
                        json={"token": "garbage.token.xxx", "password": "newpass123"})
        assert r.status_code == 400, r.text
        assert "токен" in r.json().get("detail", "").lower()

    def test_expired_token(self, client):
        expired = pyjwt.encode(
            {"sub": "whoever", "type": "reset",
             "exp": datetime.now(timezone.utc) - timedelta(minutes=5)},
            JWT_SECRET, algorithm="HS256")
        r = client.post(f"{API}/auth/reset-password",
                        json={"token": expired, "password": "newpass123"})
        assert r.status_code == 400, r.text
        assert "устарела" in r.json().get("detail", "")

    def test_wrong_token_type(self, client):
        access_like = pyjwt.encode(
            {"sub": "whoever", "type": "access",
             "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
            JWT_SECRET, algorithm="HS256")
        r = client.post(f"{API}/auth/reset-password",
                        json={"token": access_like, "password": "newpass123"})
        assert r.status_code == 400
        assert "тип" in r.json().get("detail", "").lower()

    def test_short_password_rejected(self, client):
        r = client.post(f"{API}/auth/reset-password",
                        json={"token": "x", "password": "123"})
        assert r.status_code == 422

    def test_valid_token_resets_and_autologin(self, client):
        s = requests.Session()
        s.post(f"{API}/auth/forgot-password", json={"email": ADMIN_EMAIL})
        time.sleep(1.5)
        token = _tail_reset_token()
        assert token
        new_pw = "TESTreset9876"
        r = s.post(f"{API}/auth/reset-password", json={"token": token, "password": new_pw})
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}
        # cookies set (auto-login)
        assert "access_token" in s.cookies, dict(s.cookies)
        assert "refresh_token" in s.cookies
        me = s.get(f"{API}/auth/me")
        assert me.status_code == 200, me.text
        assert me.json()["email"] == ADMIN_EMAIL

        # old password rejected
        fresh = requests.Session()
        old = fresh.post(f"{API}/auth/login",
                         json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert old.status_code == 401, f"old password still works: {old.status_code}"

        # new password works
        fresh2 = requests.Session()
        ok = fresh2.post(f"{API}/auth/login",
                         json={"email": ADMIN_EMAIL, "password": new_pw})
        assert ok.status_code == 200, ok.text
        assert ok.json()["user"]["email"] == ADMIN_EMAIL

        # restore original password via a fresh reset token
        fresh2.post(f"{API}/auth/forgot-password", json={"email": ADMIN_EMAIL})
        time.sleep(1.5)
        t2 = _tail_reset_token()
        rr = fresh2.post(f"{API}/auth/reset-password",
                         json={"token": t2, "password": ADMIN_PASSWORD})
        assert rr.status_code == 200
        back = requests.Session().post(f"{API}/auth/login",
                                       json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert back.status_code == 200, "failed to restore admin password"


# ---- emergent google session ----

class TestEmergentSession:
    def test_invalid_session_401(self, client):
        r = client.post(f"{API}/auth/emergent-session", json={"session_id": "invalid-xxx"})
        assert r.status_code == 401, r.text
        detail = r.json().get("detail", "")
        assert detail, "no error message returned"
        assert "Google" in detail or "сесси" in detail.lower()

    def test_missing_session_id_422(self, client):
        r = client.post(f"{API}/auth/emergent-session", json={})
        assert r.status_code == 422


# ---- regression: auth basics still fine ----

class TestAuthRegression:
    def test_login_and_me(self, client):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        assert "access_token" in s.cookies
        me = s.get(f"{API}/auth/me")
        assert me.status_code == 200
        body = me.json()
        assert body["email"] == ADMIN_EMAIL
        assert "_id" not in body and "password_hash" not in body

    def test_config_reports_email_enabled(self, client):
        r = client.get(f"{API}/config")
        assert r.status_code == 200
        data = r.json()
        assert data["email_enabled"] is True
        assert data["digest_email_fallback"]
