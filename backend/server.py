"""upsidestudy backend — lecture companion with per-user auth.

Features:
- Email/password auth (JWT httpOnly cookies + Authorization: Bearer fallback).
- Every stored document scoped by user_id.
- DeepSeek (fallback to Emergent/Gemini) for text.
- Whisper via Emergent LLM Key for audio.
- Weekly digest via Resend, scheduled with APScheduler.
- Spaced-repetition with freeze support (1 freeze/week, covers 2 missed days).
"""
from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from fastapi import (
    FastAPI, APIRouter, HTTPException, UploadFile, File, Request, Response,
    Depends, status,
)
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Literal, Any
from datetime import datetime, timezone, timedelta, date
import os
import re
import uuid
import json
import io
import logging
import asyncio

import httpx
import bcrypt
import jwt as pyjwt
import resend
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ---- Storage folder for raw transcripts ----
TRANSCRIPTS_DIR = ROOT_DIR / "lecture_transcripts"
TRANSCRIPTS_DIR.mkdir(exist_ok=True)

# ---- MongoDB ----
mongo_url = os.environ["MONGO_URL"]
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ["DB_NAME"]]

# ---- Config from env ----
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "").strip()
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev").strip()
DIGEST_EMAIL = os.environ.get("DIGEST_EMAIL", "").strip()
DIGEST_CRON_DAY = os.environ.get("DIGEST_CRON_DAY", "sun").strip()
DIGEST_CRON_HOUR = int(os.environ.get("DIGEST_CRON_HOUR", "20"))
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGO = "HS256"
ACCESS_TTL_MIN = 60 * 24  # 24h access token — student app, session-friendly
REFRESH_TTL_DAYS = 30
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@upsidestudy.app").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin1234")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "").strip()

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

LLM_MODE = "deepseek" if DEEPSEEK_API_KEY else ("mock" if EMERGENT_LLM_KEY else "none")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
logger.info(f"LLM_MODE={LLM_MODE}")


# ============================================================================
# Helpers
# ============================================================================

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email, "type": "access",
               "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TTL_MIN)}
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def create_refresh_token(user_id: str) -> str:
    payload = {"sub": user_id, "type": "refresh",
               "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TTL_DAYS)}
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def create_record_token(lecture_id: str) -> str:
    """Short-lived token to authorize the phone /m page to append transcript."""
    payload = {"sub": lecture_id, "type": "record",
               "exp": datetime.now(timezone.utc) + timedelta(hours=24)}
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def create_reset_token(user_id: str) -> str:
    payload = {"sub": user_id, "type": "reset",
               "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def _set_auth_cookies(resp: Response, access: str, refresh: str):
    resp.set_cookie("access_token", access, httponly=True, secure=True,
                    samesite="none", max_age=ACCESS_TTL_MIN * 60, path="/")
    resp.set_cookie("refresh_token", refresh, httponly=True, secure=True,
                    samesite="none", max_age=REFRESH_TTL_DAYS * 86400, path="/")


def _clear_auth_cookies(resp: Response):
    resp.delete_cookie("access_token", path="/")
    resp.delete_cookie("refresh_token", path="/")


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except pyjwt.PyJWTError:
        raise HTTPException(401, "Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(401, "Invalid token type")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(401, "User not found")
    return user


def _extract_json(text: str) -> Any:
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    candidate = fence.group(1) if fence else text
    for opener, closer in (("{", "}"), ("[", "]")):
        start = candidate.find(opener)
        end = candidate.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start:end + 1])
            except json.JSONDecodeError:
                continue
    return json.loads(candidate)


# ============================================================================
# Pydantic models
# ============================================================================

class User(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    role: str = "user"
    created_at: str
    freeze_dates: List[str] = Field(default_factory=list)


class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=200)
    name: Optional[str] = Field(default=None, max_length=100)


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class Lecture(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str
    source_type: Literal["mic", "upload", "paste"] = "mic"
    transcript: str = ""
    summary: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    glossary: List[dict] = Field(default_factory=list)
    duration_sec: Optional[int] = None
    llm_mode: str = LLM_MODE
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class LectureCreate(BaseModel):
    title: str
    source_type: Literal["mic", "upload", "paste"] = "mic"
    transcript: str = ""


class TranscriptUpdate(BaseModel):
    transcript: str
    duration_sec: Optional[int] = None
    append: bool = False


class Question(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: Literal["mcq", "tf", "short"]
    prompt: str
    options: Optional[List[str]] = None
    answer: str
    explanation: Optional[str] = None


class Test(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    lecture_id: str
    user_id: str
    questions: List[Question]
    llm_mode: str = LLM_MODE
    created_at: str = Field(default_factory=_now)


class Answer(BaseModel):
    question_id: str
    response: str


class GradedAnswer(BaseModel):
    question_id: str
    response: str
    correct_answer: str
    is_correct: bool
    explanation: Optional[str] = None


class TestAttempt(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    test_id: str
    lecture_id: str
    user_id: str
    graded: List[GradedAnswer]
    score: int
    total: int
    correct: int
    created_at: str = Field(default_factory=_now)


# ============================================================================
# LLM helpers
# ============================================================================

SUMMARY_SYSTEM = (
    "You are an academic study assistant. You transform raw English lecture "
    "transcripts into clear, well-structured study notes for a "
    "Russian-speaking student. Preserve technical vocabulary, definitions, "
    "formulas, and examples. WRITE THE NOTES IN RUSSIAN, but keep original "
    "English terms in parentheses on first mention. Use markdown."
)

TEST_SYSTEM = (
    "You are an academic exam writer. Given lecture study notes (in Russian), "
    "you write high-quality knowledge-check questions in Russian that test "
    "real understanding. Questions must be answerable from the notes."
)

GLOSSARY_SYSTEM = (
    "You are a bilingual English↔Russian academic assistant. From a raw "
    "university lecture transcript in English, extract the ~10–15 most "
    "important domain-specific terms. Return strict JSON only."
)


def _new_chat(session_id: str, system: str) -> LlmChat:
    return LlmChat(api_key=EMERGENT_LLM_KEY, session_id=session_id,
                   system_message=system).with_model("gemini",
                                                     "gemini-3-flash-preview")


async def _deepseek_text(system: str, prompt: str) -> str:
    payload = {"model": "deepseek-chat",
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": prompt}],
               "temperature": 0.3}
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                     "Content-Type": "application/json"},
            json=payload,
        )
        if r.status_code != 200:
            try:
                msg = r.json().get("error", {}).get("message", r.text)
            except Exception:
                msg = r.text
            raise HTTPException(502, f"DeepSeek error: {msg}")
        data = r.json()
        return data["choices"][0]["message"]["content"]


async def _llm_text(session_id: str, system: str, prompt: str) -> str:
    if LLM_MODE == "deepseek":
        try:
            return await _deepseek_text(system, prompt)
        except HTTPException as e:
            if EMERGENT_LLM_KEY:
                logger.warning(f"DeepSeek failed ({e.detail}); falling back to Gemini.")
                chat = _new_chat(session_id, system)
                reply = await chat.send_message(UserMessage(text=prompt))
                return reply if isinstance(reply, str) else str(reply)
            raise
    if LLM_MODE == "mock":
        chat = _new_chat(session_id, system)
        reply = await chat.send_message(UserMessage(text=prompt))
        return reply if isinstance(reply, str) else str(reply)
    raise HTTPException(500, "No LLM key configured.")


async def _build_glossary(transcript: str) -> list:
    if not transcript.strip():
        return []
    prompt = (
        "Extract a glossary from the following English lecture transcript. "
        "Return JSON exactly like:\n"
        "{\"terms\":[{\"term\":\"<English term>\","
        "\"translation\":\"<Russian translation>\","
        "\"definition\":\"<1-2 sentence definition in Russian>\"}]}\n"
        "Rules: 8-15 items ordered by importance. Term = exact English form. "
        "Definition in Russian. Skip common words.\n\n"
        "TRANSCRIPT:\n\"\"\"\n" + transcript[:15000] + "\n\"\"\""
    )
    raw = await _llm_text("glossary-auto", GLOSSARY_SYSTEM, prompt)
    data = _extract_json(raw)
    terms = data.get("terms", [])[:20]
    clean = []
    for t in terms:
        if not isinstance(t, dict):
            continue
        term = str(t.get("term", "")).strip()
        translation = str(t.get("translation", "")).strip()
        definition = str(t.get("definition", "")).strip()
        if term and translation:
            clean.append({"term": term, "translation": translation,
                          "definition": definition})
    return clean


def _norm(s: str) -> str:
    return re.sub(r"[^\w\s]+", " ", (s or "").lower(), flags=re.UNICODE).strip()


# ============================================================================
# App
# ============================================================================

app = FastAPI(title="upsidestudy")
api = APIRouter(prefix="/api")


# ---- Auth endpoints ----

@api.post("/auth/register")
async def register(body: RegisterBody, response: Response):
    email = body.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(409, "Пользователь с такой почтой уже зарегистрирован.")
    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "name": (body.name or email.split("@")[0]).strip(),
        "password_hash": hash_password(body.password),
        "role": "user",
        "created_at": _now(),
        "freeze_dates": [],
    }
    await db.users.insert_one(user)
    access = create_access_token(user["id"], email)
    refresh = create_refresh_token(user["id"])
    _set_auth_cookies(response, access, refresh)
    public = {k: v for k, v in user.items() if k not in ("_id", "password_hash")}
    return {"user": public}


@api.post("/auth/login")
async def login(body: LoginBody, response: Response):
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(401, "Неверная почта или пароль.")
    access = create_access_token(user["id"], email)
    refresh = create_refresh_token(user["id"])
    _set_auth_cookies(response, access, refresh)
    public = {k: v for k, v in user.items() if k not in ("_id", "password_hash")}
    return {"user": public}


@api.post("/auth/logout")
async def logout(response: Response, _user: dict = Depends(get_current_user)):
    _clear_auth_cookies(response)
    return {"ok": True}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    user.pop("_id", None)
    return user


@api.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(401, "No refresh token")
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except pyjwt.PyJWTError:
        raise HTTPException(401, "Invalid refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(401, "Wrong token type")
    user = await db.users.find_one({"id": payload["sub"]})
    if not user:
        raise HTTPException(401, "User not found")
    access = create_access_token(user["id"], user["email"])
    response.set_cookie("access_token", access, httponly=True, secure=True,
                        samesite="none", max_age=ACCESS_TTL_MIN * 60, path="/")
    return {"ok": True}


# ---- Password reset ----

class ForgotBody(BaseModel):
    email: EmailStr


class ResetBody(BaseModel):
    token: str
    password: str = Field(min_length=6, max_length=200)


def _reset_email_html(name: str, link: str) -> str:
    return f"""
<!doctype html><html><body style="margin:0;padding:0;background:#f4f1eb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1c201f;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f1eb;padding:32px 16px;"><tr><td align="center">
  <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#fcfbf9;border:1px solid #1c201f;box-shadow:3px 3px 0 0 #1c201f;">
    <tr><td style="padding:32px 40px 8px;">
      <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#8c9690;">— upsidestudy · восстановление пароля</div>
      <h1 style="font-family:Georgia,serif;font-size:28px;font-weight:600;margin:12px 0 8px;color:#1c201f;">Привет, {name or 'друг'}.</h1>
      <p style="font-size:15px;color:#4a524d;line-height:1.5;">Кто-то попросил сбросить пароль для этого аккаунта. Ссылка действует один час. Если это были не вы — просто удалите письмо.</p>
    </td></tr>
    <tr><td style="padding:16px 40px 32px;">
      <a href="{link}" style="display:inline-block;background:#d86e53;color:#fff;padding:14px 28px;text-decoration:none;border:1px solid #1c201f;box-shadow:3px 3px 0 0 #1c201f;font-family:Georgia,serif;font-size:16px;">Сбросить пароль</a>
      <div style="font-size:11px;color:#8c9690;margin-top:16px;">Не работает кнопка? Скопируйте адрес:</div>
      <div style="font-size:11px;color:#4a524d;margin-top:4px;word-break:break-all;font-family:'Courier New',monospace;">{link}</div>
    </td></tr>
    <tr><td style="padding:0 40px 32px;font-size:11px;color:#8c9690;text-align:center;">upsidestudy — ваш помощник по лекциям.</td></tr>
  </table>
</td></tr></table></body></html>"""


@api.post("/auth/forgot-password")
async def forgot_password(body: ForgotBody):
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    # Always answer OK to avoid revealing which emails exist.
    if not user:
        logger.info(f"[reset] user for {email} not found; no email sent.")
        return {"ok": True}
    token = create_reset_token(user["id"])
    link = f"{FRONTEND_URL}/reset-password?token={token}"
    logger.info(f"[reset] link for {email}: {link}")
    if RESEND_API_KEY:
        # Resend test mode only delivers to the account holder. Attempt
        # delivery to the user's real email; if Resend rejects, fall back
        # to DIGEST_EMAIL so at least you receive the link during dev.
        recipients_to_try = [email]
        if DIGEST_EMAIL and DIGEST_EMAIL != email:
            recipients_to_try.append(DIGEST_EMAIL)
        for recipient in recipients_to_try:
            try:
                await asyncio.to_thread(
                    resend.Emails.send,
                    {"from": SENDER_EMAIL, "to": [recipient],
                     "subject": "upsidestudy · восстановление пароля",
                     "html": _reset_email_html(user.get("name", ""), link)})
                logger.info(f"[reset] mail sent to {recipient}")
                break
            except Exception as e:
                logger.warning(f"[reset] send to {recipient} failed: {e}")
    return {"ok": True}


@api.post("/auth/reset-password")
async def reset_password(body: ResetBody, response: Response):
    try:
        payload = pyjwt.decode(body.token, JWT_SECRET, algorithms=[JWT_ALGO])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(400, "Ссылка устарела. Запросите новую.")
    except pyjwt.PyJWTError:
        raise HTTPException(400, "Неверный токен восстановления.")
    if payload.get("type") != "reset":
        raise HTTPException(400, "Неверный тип токена.")
    user = await db.users.find_one({"id": payload["sub"]})
    if not user:
        raise HTTPException(404, "Пользователь не найден.")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": hash_password(body.password)}})
    # Auto-login after reset
    access = create_access_token(user["id"], user["email"])
    refresh = create_refresh_token(user["id"])
    _set_auth_cookies(response, access, refresh)
    return {"ok": True}


# ---- Emergent-managed Google Auth ----

class EmergentSessionBody(BaseModel):
    session_id: str


@api.post("/auth/emergent-session")
async def emergent_session(body: EmergentSessionBody, response: Response):
    """Exchange an Emergent Auth session_id for our own JWT session."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": body.session_id},
        )
    if r.status_code != 200:
        raise HTTPException(401, "Не удалось подтвердить сессию Google.")
    data = r.json()
    email = (data.get("email") or "").lower().strip()
    name = data.get("name") or (email.split("@")[0] if email else "user")
    if not email:
        raise HTTPException(400, "Google не вернул почту.")
    user = await db.users.find_one({"email": email})
    if user is None:
        # Create user without a usable password (random hash) — user can set
        # one later via forgot-password.
        user = {
            "id": str(uuid.uuid4()),
            "email": email,
            "name": name,
            "password_hash": hash_password(uuid.uuid4().hex),
            "role": "user",
            "created_at": _now(),
            "freeze_dates": [],
            "picture": data.get("picture"),
            "auth_provider": "google",
        }
        await db.users.insert_one(user)
    else:
        # Update profile picture / name if Google has fresher data.
        updates = {}
        if data.get("picture") and user.get("picture") != data["picture"]:
            updates["picture"] = data["picture"]
        if name and not user.get("name"):
            updates["name"] = name
        if updates:
            await db.users.update_one({"id": user["id"]}, {"$set": updates})
            user.update(updates)
    access = create_access_token(user["id"], email)
    refresh = create_refresh_token(user["id"])
    _set_auth_cookies(response, access, refresh)
    public = {k: v for k, v in user.items() if k not in ("_id", "password_hash")}
    return {"user": public}


# ---- Config (public) ----

@api.get("/")
async def root():
    return {"service": "upsidestudy", "llm_mode": LLM_MODE}


@api.get("/config")
async def get_config():
    return {"llm_mode": LLM_MODE,
            "is_mocked": LLM_MODE != "deepseek",
            "email_enabled": bool(RESEND_API_KEY),
            "digest_email_fallback": DIGEST_EMAIL,
            "digest_schedule": f"{DIGEST_CRON_DAY} {DIGEST_CRON_HOUR:02d}:00 UTC"}


# ---- Lectures CRUD (per-user) ----

def _write_transcript_file(lecture_id: str, title: str, transcript: str):
    safe_title = re.sub(r"[^\w\s-]", "", title)[:60].strip().replace(" ", "_")
    for old in TRANSCRIPTS_DIR.glob(f"{lecture_id}_*.txt"):
        old.unlink()
    (TRANSCRIPTS_DIR / f"{lecture_id}_{safe_title}.txt").write_text(
        transcript, encoding="utf-8")


@api.post("/lectures", response_model=Lecture)
async def create_lecture(body: LectureCreate, user: dict = Depends(get_current_user)):
    lec = Lecture(user_id=user["id"], **body.model_dump())
    await db.lectures.insert_one(lec.model_dump())
    if lec.transcript:
        _write_transcript_file(lec.id, lec.title, lec.transcript)
    return lec


@api.get("/lectures", response_model=List[Lecture])
async def list_lectures(user: dict = Depends(get_current_user)):
    docs = await db.lectures.find({"user_id": user["id"]},
                                  {"_id": 0}).sort("created_at", -1).to_list(500)
    return [Lecture(**d) for d in docs]


async def _load_owned_lecture(lecture_id: str, user_id: str) -> Lecture:
    doc = await db.lectures.find_one({"id": lecture_id, "user_id": user_id},
                                     {"_id": 0})
    if not doc:
        raise HTTPException(404, "Lecture not found")
    return Lecture(**doc)


@api.get("/lectures/{lecture_id}", response_model=Lecture)
async def get_lecture(lecture_id: str, user: dict = Depends(get_current_user)):
    return await _load_owned_lecture(lecture_id, user["id"])


@api.delete("/lectures/{lecture_id}")
async def delete_lecture(lecture_id: str, user: dict = Depends(get_current_user)):
    r = await db.lectures.delete_one({"id": lecture_id, "user_id": user["id"]})
    if r.deleted_count == 0:
        raise HTTPException(404, "Lecture not found")
    await db.tests.delete_many({"lecture_id": lecture_id, "user_id": user["id"]})
    await db.attempts.delete_many({"lecture_id": lecture_id, "user_id": user["id"]})
    await db.review_items.delete_many({"lecture_id": lecture_id, "user_id": user["id"]})
    for old in TRANSCRIPTS_DIR.glob(f"{lecture_id}_*.txt"):
        old.unlink()
    return {"ok": True}


@api.patch("/lectures/{lecture_id}/transcript", response_model=Lecture)
async def update_transcript(
    lecture_id: str, body: TranscriptUpdate, request: Request,
):
    """Accepts either a user access token OR a record-scoped token from /m/{id}."""
    doc = await db.lectures.find_one({"id": lecture_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Lecture not found")
    lec = Lecture(**doc)
    # Auth: user cookie/header OR record token
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except pyjwt.PyJWTError:
        raise HTTPException(401, "Invalid token")
    ttype = payload.get("type")
    if ttype == "record":
        if payload.get("sub") != lecture_id:
            raise HTTPException(403, "Wrong lecture for record token")
    elif ttype == "access":
        if payload.get("sub") != lec.user_id:
            raise HTTPException(403, "Not your lecture")
    else:
        raise HTTPException(401, "Bad token type")

    lec.transcript = (lec.transcript + " " + body.transcript).strip() \
        if body.append and lec.transcript else body.transcript
    if body.duration_sec is not None:
        lec.duration_sec = body.duration_sec
    lec.updated_at = _now()
    await db.lectures.update_one({"id": lecture_id},
                                 {"$set": lec.model_dump()})
    _write_transcript_file(lec.id, lec.title, lec.transcript)
    return lec


# Public: mobile page loads lecture title (needs record token)
@api.get("/lectures/{lecture_id}/mobile")
async def mobile_get(lecture_id: str, request: Request):
    token_qs = request.query_params.get("t", "")
    token_hdr = request.headers.get("Authorization", "")
    if token_hdr.startswith("Bearer "):
        token_qs = token_qs or token_hdr[7:]
    if not token_qs:
        raise HTTPException(401, "Missing record token")
    try:
        payload = pyjwt.decode(token_qs, JWT_SECRET, algorithms=[JWT_ALGO])
    except pyjwt.PyJWTError:
        raise HTTPException(401, "Invalid record token")
    if payload.get("type") != "record" or payload.get("sub") != lecture_id:
        raise HTTPException(403, "Wrong token")
    doc = await db.lectures.find_one({"id": lecture_id},
                                     {"_id": 0, "id": 1, "title": 1, "transcript": 1})
    if not doc:
        raise HTTPException(404, "Lecture not found")
    return doc


@api.post("/lectures/{lecture_id}/record-token")
async def create_lecture_record_token(lecture_id: str,
                                      user: dict = Depends(get_current_user)):
    await _load_owned_lecture(lecture_id, user["id"])
    return {"token": create_record_token(lecture_id),
            "url": f"{FRONTEND_URL}/m/{lecture_id}"}


# ---- Summary / test / glossary ----

@api.post("/lectures/{lecture_id}/summary", response_model=Lecture)
async def generate_summary(lecture_id: str,
                           user: dict = Depends(get_current_user)):
    lec = await _load_owned_lecture(lecture_id, user["id"])
    if not lec.transcript.strip():
        raise HTTPException(400, "Lecture has no transcript yet.")

    prompt = (
        "Below is the raw transcript of a university lecture (English). "
        "Produce study notes in RUSSIAN as a JSON object with this shape: "
        '{"summary": "<markdown notes in Russian, 400-800 words, ## headings, '
        'bullet lists, **Определения** block>", "key_points": ["тезис 1", ...]}\n'
        "IMPORTANT: no LaTeX, plain text formulas.\n\n"
        "TRANSCRIPT:\n\"\"\"\n" + lec.transcript[:15000] + "\n\"\"\""
    )
    raw = await _llm_text(f"summary-{lecture_id}", SUMMARY_SYSTEM, prompt)
    try:
        data = _extract_json(raw)
        lec.summary = data.get("summary", "").strip()
        lec.key_points = data.get("key_points", [])[:12]
    except Exception as e:
        logger.warning(f"JSON parse failed: {e}")
        lec.summary = raw.strip()
        lec.key_points = []

    lec.updated_at = _now()
    lec.llm_mode = LLM_MODE
    await db.lectures.update_one({"id": lecture_id},
                                 {"$set": lec.model_dump()})

    # Auto-generate glossary
    try:
        terms = await _build_glossary(lec.transcript)
        if terms:
            lec.glossary = terms
            await db.lectures.update_one(
                {"id": lecture_id},
                {"$set": {"glossary": terms, "updated_at": _now()}},
            )
    except Exception as e:
        logger.warning(f"Auto-glossary failed: {e}")

    return lec


@api.post("/lectures/{lecture_id}/glossary")
async def generate_glossary(lecture_id: str,
                            user: dict = Depends(get_current_user)):
    lec = await _load_owned_lecture(lecture_id, user["id"])
    if not lec.transcript.strip():
        raise HTTPException(400, "Lecture has no transcript yet.")
    try:
        clean = await _build_glossary(lec.transcript)
    except Exception as e:
        raise HTTPException(500, f"Failed to parse glossary JSON: {e}")
    await db.lectures.update_one(
        {"id": lecture_id},
        {"$set": {"glossary": clean, "updated_at": _now()}},
    )
    return {"terms": clean}


@api.get("/glossary/all")
async def glossary_all(user: dict = Depends(get_current_user)):
    lectures = await db.lectures.find(
        {"user_id": user["id"], "glossary": {"$ne": []}},
        {"_id": 0, "id": 1, "title": 1, "glossary": 1},
    ).to_list(1000)
    seen: dict = {}
    for l in lectures:
        for t in l.get("glossary", []):
            key = t["term"].lower()
            if key in seen:
                continue
            seen[key] = {**t, "lecture_id": l["id"],
                         "lecture_title": l["title"]}
    return {"terms": sorted(seen.values(), key=lambda x: x["term"].lower())}


@api.post("/lectures/{lecture_id}/test", response_model=Test)
async def generate_test(lecture_id: str,
                        user: dict = Depends(get_current_user)):
    lec = await _load_owned_lecture(lecture_id, user["id"])
    if not lec.summary:
        raise HTTPException(400, "Generate the summary before creating a test.")
    prompt = (
        "From these Russian lecture notes, write a knowledge test IN RUSSIAN "
        "as strict JSON:\n"
        "{\"questions\":[{\"type\":\"mcq\",\"prompt\":\"...\","
        "\"options\":[\"A) ...\",\"B) ...\",\"C) ...\",\"D) ...\"],"
        "\"answer\":\"B\",\"explanation\":\"...\"},"
        "{\"type\":\"tf\",\"prompt\":\"...\",\"answer\":\"True\",\"explanation\":\"...\"},"
        "{\"type\":\"short\",\"prompt\":\"...\",\"answer\":\"фраза\",\"explanation\":\"...\"}]}\n"
        "Rules: 8 questions total = 4 MCQ + 2 T/F + 2 short. MCQ answer = "
        "single letter A|B|C|D. TF answer = 'True'|'False' (UI localizes). "
        "Return ONLY JSON.\n\nNOTES:\n\"\"\"\n" + (lec.summary or "")[:12000] + "\n\"\"\""
    )
    raw = await _llm_text(f"test-{lecture_id}", TEST_SYSTEM, prompt)
    try:
        data = _extract_json(raw)
        raw_qs = data.get("questions", [])
    except Exception as e:
        raise HTTPException(500, f"Failed to parse test JSON: {e}")
    questions: List[Question] = []
    for q in raw_qs:
        try:
            questions.append(Question(**q))
        except Exception as ex:
            logger.warning(f"Bad question skipped: {ex}")
    if not questions:
        raise HTTPException(500, "LLM returned no usable questions.")
    test = Test(lecture_id=lecture_id, user_id=user["id"], questions=questions)
    await db.tests.insert_one(test.model_dump())
    return test


@api.get("/lectures/{lecture_id}/tests", response_model=List[Test])
async def list_tests(lecture_id: str, user: dict = Depends(get_current_user)):
    await _load_owned_lecture(lecture_id, user["id"])
    docs = await db.tests.find({"lecture_id": lecture_id, "user_id": user["id"]},
                               {"_id": 0}).sort("created_at", -1).to_list(50)
    return [Test(**d) for d in docs]


@api.get("/tests/{test_id}", response_model=Test)
async def get_test(test_id: str, user: dict = Depends(get_current_user)):
    doc = await db.tests.find_one({"id": test_id, "user_id": user["id"]},
                                  {"_id": 0})
    if not doc:
        raise HTTPException(404, "Test not found")
    return Test(**doc)


class GradeBody(BaseModel):
    answers: List[Answer]


@api.post("/tests/{test_id}/grade", response_model=TestAttempt)
async def grade(test_id: str, body: GradeBody,
                user: dict = Depends(get_current_user)):
    doc = await db.tests.find_one({"id": test_id, "user_id": user["id"]},
                                  {"_id": 0})
    if not doc:
        raise HTTPException(404, "Test not found")
    test = Test(**doc)
    user_map = {a.question_id: a.response for a in body.answers}
    graded: List[GradedAnswer] = []
    correct_count = 0
    for q in test.questions:
        resp = user_map.get(q.id, "")
        if q.type == "mcq":
            is_ok = _norm(resp)[:1] == _norm(q.answer)[:1] and bool(resp)
        elif q.type == "tf":
            is_ok = _norm(resp) == _norm(q.answer)
        else:
            expected = set(_norm(q.answer).split())
            got = set(_norm(resp).split())
            is_ok = bool(expected) and len(expected & got) / len(expected) >= 0.6
        if is_ok:
            correct_count += 1
        graded.append(GradedAnswer(question_id=q.id, response=resp,
                                   correct_answer=q.answer, is_correct=is_ok,
                                   explanation=q.explanation))
    total = len(test.questions)
    score = int(round((correct_count / total) * 100)) if total else 0
    attempt = TestAttempt(test_id=test_id, lecture_id=test.lecture_id,
                          user_id=user["id"], graded=graded, score=score,
                          total=total, correct=correct_count)
    await db.attempts.insert_one(attempt.model_dump())

    # SR scheduling
    now = datetime.now(timezone.utc)
    for q, g in zip(test.questions, graded):
        existing = await db.review_items.find_one(
            {"lecture_id": test.lecture_id, "question_id": q.id,
             "user_id": user["id"]}, {"_id": 0})
        if g.is_correct:
            if not existing:
                continue
            new_interval = min(30, max(1, existing.get("interval_days", 1) * 2))
            await db.review_items.update_one(
                {"id": existing["id"]},
                {"$set": {"interval_days": new_interval,
                          "due_at": (now + timedelta(days=new_interval)).isoformat(),
                          "streak": existing.get("streak", 0) + 1,
                          "last_result": "correct"}})
        else:
            if existing:
                await db.review_items.update_one(
                    {"id": existing["id"]},
                    {"$set": {"interval_days": 1,
                              "due_at": (now + timedelta(days=1)).isoformat(),
                              "streak": 0,
                              "misses": existing.get("misses", 0) + 1,
                              "last_result": "wrong"}})
            else:
                await db.review_items.insert_one({
                    "id": str(uuid.uuid4()),
                    "user_id": user["id"],
                    "lecture_id": test.lecture_id,
                    "question_id": q.id,
                    "question": q.model_dump(),
                    "interval_days": 1,
                    "due_at": (now + timedelta(days=1)).isoformat(),
                    "misses": 1, "streak": 0, "last_result": "wrong",
                    "created_at": _now(),
                })
    return attempt


@api.get("/lectures/{lecture_id}/attempts", response_model=List[TestAttempt])
async def list_attempts(lecture_id: str, user: dict = Depends(get_current_user)):
    await _load_owned_lecture(lecture_id, user["id"])
    docs = await db.attempts.find({"lecture_id": lecture_id, "user_id": user["id"]},
                                  {"_id": 0}).sort("created_at", -1).to_list(100)
    return [TestAttempt(**d) for d in docs]


# ---- Review ----

class ReviewItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    lecture_id: str
    question_id: str
    question: Question
    interval_days: int
    due_at: str
    misses: int
    streak: int
    last_result: str
    created_at: str


class ReviewAnswer(BaseModel):
    response: str


@api.get("/review/due", response_model=List[ReviewItem])
async def review_due(user: dict = Depends(get_current_user)):
    now_iso = _now()
    docs = await db.review_items.find(
        {"user_id": user["id"], "due_at": {"$lte": now_iso}}, {"_id": 0}
    ).sort("due_at", 1).to_list(500)
    return [ReviewItem(**d) for d in docs]


@api.get("/review/stats")
async def review_stats(user: dict = Depends(get_current_user)):
    now_iso = _now()
    total = await db.review_items.count_documents({"user_id": user["id"]})
    due = await db.review_items.count_documents(
        {"user_id": user["id"], "due_at": {"$lte": now_iso}})
    return {"total": total, "due": due}


@api.post("/review/{item_id}/answer")
async def review_answer(item_id: str, body: ReviewAnswer,
                        user: dict = Depends(get_current_user)):
    doc = await db.review_items.find_one({"id": item_id, "user_id": user["id"]},
                                         {"_id": 0})
    if not doc:
        raise HTTPException(404, "Review item not found")
    q = Question(**doc["question"])
    resp = body.response
    if q.type == "mcq":
        is_ok = _norm(resp)[:1] == _norm(q.answer)[:1] and bool(resp)
    elif q.type == "tf":
        is_ok = _norm(resp) == _norm(q.answer)
    else:
        expected = set(_norm(q.answer).split())
        got = set(_norm(resp).split())
        is_ok = bool(expected) and len(expected & got) / len(expected) >= 0.6

    now = datetime.now(timezone.utc)
    if is_ok:
        new_interval = min(30, max(2, doc.get("interval_days", 1) * 2))
        await db.review_items.update_one(
            {"id": item_id},
            {"$set": {"interval_days": new_interval,
                      "due_at": (now + timedelta(days=new_interval)).isoformat(),
                      "streak": doc.get("streak", 0) + 1,
                      "last_result": "correct"}})
        next_days = new_interval
    else:
        await db.review_items.update_one(
            {"id": item_id},
            {"$set": {"interval_days": 1,
                      "due_at": (now + timedelta(days=1)).isoformat(),
                      "streak": 0,
                      "misses": doc.get("misses", 0) + 1,
                      "last_result": "wrong"}})
        next_days = 1

    today = now.strftime("%Y-%m-%d")
    await db.review_days.update_one(
        {"user_id": user["id"], "day": today},
        {"$set": {"user_id": user["id"], "day": today}}, upsert=True)

    return {"is_correct": is_ok, "correct_answer": q.answer,
            "explanation": q.explanation, "next_due_days": next_days}


@api.post("/review/seed-now")
async def review_seed_now(user: dict = Depends(get_current_user)):
    now_iso = _now()
    r = await db.review_items.update_many(
        {"user_id": user["id"], "due_at": {"$gt": now_iso}},
        {"$set": {"due_at": now_iso}})
    return {"updated": r.modified_count}


# ---- Streak & freeze ----

def _compute_streak(day_set: set, freeze_set: set) -> tuple:
    today = datetime.now(timezone.utc).date()
    streak = 0
    reviewed_today = today.isoformat() in day_set
    # Determine starting day: today if reviewed OR yesterday if reviewed
    cursor = today if reviewed_today else (
        today - timedelta(days=1) if (today - timedelta(days=1)).isoformat() in day_set
        else None)
    # If no direct entry today/yesterday, check if a freeze covers the miss
    if cursor is None:
        # A freeze on today/yesterday can carry the streak until it dies of natural causes
        for fdays in (0, 1, 2):
            check_day = today - timedelta(days=fdays)
            if check_day.isoformat() in freeze_set:
                cursor = check_day - timedelta(days=1)  # go before freeze
                break
    # Walk backwards
    while cursor is not None:
        if cursor.isoformat() in day_set:
            streak += 1
            cursor = cursor - timedelta(days=1)
        elif cursor.isoformat() in freeze_set:
            # Freeze covers this day — streak continues but doesn't increment
            cursor = cursor - timedelta(days=1)
        else:
            break
    return streak, reviewed_today


@api.get("/stats")
async def stats(user: dict = Depends(get_current_user)):
    uid = user["id"]
    lec_count = await db.lectures.count_documents({"user_id": uid})
    test_count = await db.tests.count_documents({"user_id": uid})
    attempt_count = await db.attempts.count_documents({"user_id": uid})
    attempts = await db.attempts.find({"user_id": uid},
                                      {"_id": 0, "score": 1}).to_list(1000)
    avg = int(round(sum(a["score"] for a in attempts) / len(attempts))) \
        if attempts else 0

    days = await db.review_days.find({"user_id": uid},
                                     {"_id": 0, "day": 1}).to_list(1000)
    day_set = {d["day"] for d in days}
    freeze_set = set(user.get("freeze_dates", []))
    streak, reviewed_today = _compute_streak(day_set, freeze_set)

    # Can we freeze? (Once per rolling 7 days)
    today = datetime.now(timezone.utc).date()
    week_ago = (today - timedelta(days=7)).isoformat()
    last_freeze = max(freeze_set) if freeze_set else None
    can_freeze = (last_freeze is None) or (last_freeze < week_ago)
    next_freeze_in = 0
    if not can_freeze and last_freeze:
        # Days until next allowed freeze
        try:
            lf = datetime.strptime(last_freeze, "%Y-%m-%d").date()
            next_freeze_in = max(0, 7 - (today - lf).days)
        except Exception:
            pass

    return {"lectures": lec_count, "tests": test_count,
            "attempts": attempt_count, "avg_score": avg,
            "streak": streak, "reviewed_today": reviewed_today,
            "can_freeze": can_freeze, "next_freeze_in_days": next_freeze_in,
            "freeze_dates": sorted(freeze_set, reverse=True)[:8]}


@api.post("/streak/freeze")
async def streak_freeze(user: dict = Depends(get_current_user)):
    today = datetime.now(timezone.utc).date()
    freeze_dates = list(user.get("freeze_dates", []))
    week_ago = (today - timedelta(days=7)).isoformat()
    if any(d >= week_ago for d in freeze_dates):
        raise HTTPException(400, "Заморозка уже использована на этой неделе.")
    freeze_dates.append(today.isoformat())
    await db.users.update_one({"id": user["id"]},
                              {"$set": {"freeze_dates": freeze_dates}})
    return {"ok": True, "frozen_on": today.isoformat(),
            "covers_days": 2}


# ---- Digest ----

def _digest_html(new_lectures: list, due_count: int, avg_score: int) -> str:
    rows = "".join([
        f"<tr><td style='padding:8px 0;border-bottom:1px solid #e6e0d5;'>"
        f"<div style='font-family:Georgia,serif;font-size:18px;color:#1c201f;'>{l['title']}</div>"
        f"<div style='font-size:12px;color:#8c9690;letter-spacing:1px;text-transform:uppercase;margin-top:4px;'>"
        f"{l.get('duration_sec',0)//60 if l.get('duration_sec') else 0} мин · "
        f"{len((l.get('transcript') or '').split())} слов · "
        f"{'конспект готов' if l.get('summary') else 'без конспекта'}"
        f"</div></td></tr>"
        for l in new_lectures[:10]
    ]) or "<tr><td style='padding:16px 0;color:#8c9690;'>За эту неделю новых лекций не появилось.</td></tr>"
    return f"""
<!doctype html><html><body style="margin:0;padding:0;background:#f4f1eb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1c201f;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f1eb;padding:32px 16px;">
<tr><td align="center">
  <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:#fcfbf9;border:1px solid #1c201f;box-shadow:3px 3px 0 0 #1c201f;">
    <tr><td style="padding:32px 40px 8px;">
      <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#8c9690;">— upsidestudy · еженедельная сводка</div>
      <h1 style="font-family:Georgia,serif;font-size:32px;font-weight:600;margin:12px 0 4px;color:#1c201f;">Что произошло на этой неделе</h1>
      <div style="font-size:14px;color:#4a524d;">Новых лекций: <strong>{len(new_lectures)}</strong> · Карточек к повторению: <strong>{due_count}</strong> · Средний балл тестов: <strong>{avg_score}%</strong></div>
    </td></tr>
    <tr><td style="padding:8px 40px 24px;">
      <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#8c9690;margin-bottom:8px;">Новые лекции</div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>
    </td></tr>
    <tr><td style="padding:16px 40px 32px;">
      <div style="background:#d86e53;color:#fff;border:1px solid #1c201f;padding:16px 20px;box-shadow:2px 2px 0 0 #b75640;">
        <div style="font-family:Georgia,serif;font-size:20px;">Пора повторить</div>
        <div style="font-size:13px;margin-top:4px;">{due_count} карточек готовы к повторению прямо сейчас.</div>
      </div>
    </td></tr>
    <tr><td style="padding:0 40px 32px;font-size:11px;color:#8c9690;text-align:center;">
      upsidestudy — ваш помощник по лекциям.
    </td></tr>
  </table>
</td></tr></table></body></html>"""


async def _build_digest_for(user_id: str, user_email: str):
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    new_lectures = await db.lectures.find(
        {"user_id": user_id, "created_at": {"$gte": week_ago}}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    due_count = await db.review_items.count_documents(
        {"user_id": user_id, "due_at": {"$lte": _now()}})
    attempts = await db.attempts.find(
        {"user_id": user_id, "created_at": {"$gte": week_ago}},
        {"_id": 0, "score": 1}).to_list(500)
    avg_score = int(round(sum(a["score"] for a in attempts) / len(attempts))) \
        if attempts else 0
    subject = f"upsidestudy · {len(new_lectures)} лекций, {due_count} к повторению"
    html = _digest_html(new_lectures, due_count, avg_score)
    return {"subject": subject, "html": html, "to": user_email,
            "new_lectures": len(new_lectures), "due_count": due_count,
            "avg_score": avg_score}


@api.get("/digest/preview")
async def digest_preview(user: dict = Depends(get_current_user)):
    return await _build_digest_for(user["id"], user["email"])


@api.post("/digest/send")
async def digest_send(user: dict = Depends(get_current_user)):
    if not RESEND_API_KEY:
        raise HTTPException(400, "Resend не настроен.")
    # Resend test mode only lets us send to the account holder's email.
    # If DIGEST_EMAIL is configured, always send there so the flow works
    # regardless of which user is logged in.
    recipient = DIGEST_EMAIL or user["email"]
    digest = await _build_digest_for(user["id"], recipient)
    params = {"from": SENDER_EMAIL, "to": [digest["to"]],
              "subject": digest["subject"], "html": digest["html"]}
    try:
        result = await asyncio.to_thread(resend.Emails.send, params)
    except Exception as e:
        raise HTTPException(502, f"Resend error: {e}")
    email_id = getattr(result, "id", None) or (
        result.get("id") if isinstance(result, dict) else None)
    return {"ok": True, "email_id": email_id, "to": digest["to"]}


# ---- Audio transcription ----

@api.post("/transcribe-audio")
async def transcribe_audio(file: UploadFile = File(...),
                           user: dict = Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY missing.")
    contents = await file.read()
    if len(contents) > 25 * 1024 * 1024:
        raise HTTPException(413, "File too large. Max 25 MB.")
    buf = io.BytesIO(contents)
    buf.name = file.filename or "audio.mp3"
    stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
    try:
        resp = await stt.transcribe(file=buf, model="whisper-1",
                                    response_format="json", language="en")
        text = getattr(resp, "text", None) or (
            resp.get("text") if isinstance(resp, dict) else str(resp))
        return {"text": text or ""}
    except Exception as e:
        raise HTTPException(502, f"Transcription failed: {e}")


# ---- Scheduler ----

scheduler: Optional[AsyncIOScheduler] = None


async def _scheduled_weekly_digest():
    if not RESEND_API_KEY:
        return
    users = await db.users.find({}, {"_id": 0, "id": 1, "email": 1}).to_list(1000)
    for u in users:
        try:
            digest = await _build_digest_for(u["id"], u["email"])
            params = {"from": SENDER_EMAIL, "to": [digest["to"]],
                      "subject": digest["subject"], "html": digest["html"]}
            await asyncio.to_thread(resend.Emails.send, params)
            logger.info(f"Weekly digest sent to {u['email']}")
        except Exception as e:
            logger.warning(f"Digest to {u['email']} failed: {e}")


async def _seed_admin_and_migrate():
    """Seed admin + migrate legacy documents without user_id to admin."""
    existing = await db.users.find_one({"email": ADMIN_EMAIL})
    if existing is None:
        admin_id = str(uuid.uuid4())
        await db.users.insert_one({
            "id": admin_id, "email": ADMIN_EMAIL,
            "password_hash": hash_password(ADMIN_PASSWORD),
            "name": "Admin", "role": "admin", "created_at": _now(),
            "freeze_dates": [],
        })
        logger.info(f"Seeded admin {ADMIN_EMAIL}")
    else:
        admin_id = existing["id"]
        if not verify_password(ADMIN_PASSWORD, existing["password_hash"]):
            await db.users.update_one(
                {"id": admin_id},
                {"$set": {"password_hash": hash_password(ADMIN_PASSWORD)}})
            logger.info(f"Admin password updated for {ADMIN_EMAIL}")

    # Migrate legacy docs (no user_id)
    for coll in ("lectures", "tests", "attempts", "review_items"):
        r = await db[coll].update_many({"user_id": {"$exists": False}},
                                        {"$set": {"user_id": admin_id}})
        if r.modified_count:
            logger.info(f"Migrated {r.modified_count} docs in {coll} to admin.")
    # review_days legacy — migrate too
    r = await db.review_days.update_many({"user_id": {"$exists": False}},
                                          {"$set": {"user_id": admin_id}})
    if r.modified_count:
        logger.info(f"Migrated {r.modified_count} review_days to admin.")


@app.on_event("startup")
async def _startup():
    global scheduler
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.lectures.create_index("user_id")
    await db.review_items.create_index([("user_id", 1), ("due_at", 1)])
    await _seed_admin_and_migrate()

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(_scheduled_weekly_digest,
                      CronTrigger(day_of_week=DIGEST_CRON_DAY,
                                  hour=DIGEST_CRON_HOUR, minute=0),
                      id="weekly-digest", replace_existing=True)
    scheduler.start()
    logger.info(f"Scheduler started · weekly digest on {DIGEST_CRON_DAY} {DIGEST_CRON_HOUR:02d}:00 UTC")


@app.on_event("shutdown")
async def _shutdown():
    if scheduler:
        scheduler.shutdown(wait=False)
    mongo_client.close()


app.include_router(api)

# CORS: explicit origins for cookie-auth to work.
_origins = [o for o in [FRONTEND_URL, "http://localhost:3000"] if o]
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
