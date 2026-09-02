"""Lecture Companion backend.

Records/receives raw English lecture transcripts, generates AI notes and
mixed-format tests, and grades the user's answers.

LLM backing:
- Placeholder for user's DeepSeek key (will drop in when provided).
- For now: MOCKED via Emergent Universal Key -> Gemini 3 Flash (cheap, fast).
"""
from fastapi import FastAPI, APIRouter, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal, Any
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv
import os
import re
import uuid
import json
import io
import logging
import httpx

from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.llm.openai import OpenAISpeechToText
import resend
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# ---- Storage folder for raw transcripts (as user requested) ----
TRANSCRIPTS_DIR = ROOT_DIR / "lecture_transcripts"
TRANSCRIPTS_DIR.mkdir(exist_ok=True)

# ---- MongoDB ----
mongo_url = os.environ["MONGO_URL"]
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ["DB_NAME"]]

# ---- LLM config: DeepSeek (real) if key present, else fallback ----
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "").strip()
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev").strip()
DIGEST_EMAIL = os.environ.get("DIGEST_EMAIL", "").strip()
DIGEST_CRON_DAY = os.environ.get("DIGEST_CRON_DAY", "sun").strip()
DIGEST_CRON_HOUR = int(os.environ.get("DIGEST_CRON_HOUR", "20"))

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

LLM_MODE = "deepseek" if DEEPSEEK_API_KEY else ("mock" if EMERGENT_LLM_KEY else "none")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
logger.info(f"LLM_MODE={LLM_MODE}")


# ============================================================================
# Models
# ============================================================================

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Lecture(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    source_type: Literal["mic", "upload", "paste"] = "mic"
    transcript: str = ""
    summary: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    glossary: List[dict] = Field(default_factory=list)  # [{term, translation, definition}]
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
    append: bool = False  # if True, append (used during live recording chunks)


class Question(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: Literal["mcq", "tf", "short"]
    prompt: str
    options: Optional[List[str]] = None  # mcq only
    answer: str  # letter (A/B/C/D) for mcq, "True"/"False" for tf, phrase for short
    explanation: Optional[str] = None


class Test(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    lecture_id: str
    questions: List[Question]
    llm_mode: str = LLM_MODE
    created_at: str = Field(default_factory=_now)


class Answer(BaseModel):
    question_id: str
    response: str  # user's answer


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
    graded: List[GradedAnswer]
    score: int  # 0..100
    total: int
    correct: int
    created_at: str = Field(default_factory=_now)


# ============================================================================
# LLM helpers
# ============================================================================

SUMMARY_SYSTEM = (
    "You are an academic study assistant. You transform raw English lecture "
    "transcripts (possibly noisy, from automatic speech recognition) into "
    "clear, well-structured study notes for a Russian-speaking university "
    "student. Preserve technical vocabulary, definitions, formulas, and "
    "examples. WRITE THE NOTES IN RUSSIAN, but keep original English terms "
    "in parentheses on first mention. Use markdown."
)

TEST_SYSTEM = (
    "You are an academic exam writer. Given lecture study notes (in Russian), "
    "you write high-quality knowledge-check questions in Russian that test "
    "real understanding. Questions must be answerable from the notes."
)


def _new_chat(session_id: str, system: str) -> LlmChat:
    """Emergent LlmChat fallback (Gemini 3 Flash) — used when no DeepSeek key."""
    return LlmChat(api_key=EMERGENT_LLM_KEY, session_id=session_id,
                   system_message=system).with_model("gemini",
                                                     "gemini-3-flash-preview")


async def _deepseek_text(system: str, prompt: str) -> str:
    """Call DeepSeek chat completions (OpenAI-compatible)."""
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }
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
            # Graceful fallback: if DeepSeek fails (e.g. Insufficient Balance)
            # and Emergent LLM key is available, use Gemini Flash so the app
            # keeps working. Surface a warning header in the log.
            if EMERGENT_LLM_KEY:
                logger.warning(f"DeepSeek failed ({e.detail}); falling back to Gemini Flash.")
                chat = _new_chat(session_id, system)
                reply = await chat.send_message(UserMessage(text=prompt))
                return reply if isinstance(reply, str) else str(reply)
            raise
    if LLM_MODE == "mock":
        chat = _new_chat(session_id, system)
        reply = await chat.send_message(UserMessage(text=prompt))
        return reply if isinstance(reply, str) else str(reply)
    raise HTTPException(500,
                        "No LLM key configured. Add DEEPSEEK_API_KEY or "
                        "EMERGENT_LLM_KEY to backend/.env.")


def _extract_json(text: str) -> Any:
    """Robustly pull JSON out of an LLM reply that may include prose or fences."""
    # Strip markdown fences
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    candidate = fence.group(1) if fence else text
    # Find outermost {...} or [...]
    for opener, closer in (("{", "}"), ("[", "]")):
        start = candidate.find(opener)
        end = candidate.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start:end + 1])
            except json.JSONDecodeError:
                continue
    return json.loads(candidate)  # last-ditch, will raise if bad


# ============================================================================
# App
# ============================================================================

app = FastAPI(title="Lecture Companion")
api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"service": "Lecture Companion", "llm_mode": LLM_MODE}


@api.get("/config")
async def get_config():
    return {"llm_mode": LLM_MODE,
            "is_mocked": LLM_MODE != "deepseek",
            "email_enabled": bool(RESEND_API_KEY),
            "digest_email": DIGEST_EMAIL,
            "digest_schedule": f"{DIGEST_CRON_DAY} {DIGEST_CRON_HOUR:02d}:00 UTC"}


# ---- Lectures CRUD ----

@api.post("/lectures", response_model=Lecture)
async def create_lecture(body: LectureCreate):
    lec = Lecture(**body.model_dump())
    await db.lectures.insert_one(lec.model_dump())
    if lec.transcript:
        _write_transcript_file(lec.id, lec.title, lec.transcript)
    return lec


@api.get("/lectures", response_model=List[Lecture])
async def list_lectures():
    cursor = db.lectures.find({}, {"_id": 0}).sort("created_at", -1)
    docs = await cursor.to_list(500)
    return [Lecture(**d) for d in docs]


@api.get("/lectures/{lecture_id}", response_model=Lecture)
async def get_lecture(lecture_id: str):
    doc = await db.lectures.find_one({"id": lecture_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Lecture not found")
    return Lecture(**doc)


@api.delete("/lectures/{lecture_id}")
async def delete_lecture(lecture_id: str):
    await db.lectures.delete_one({"id": lecture_id})
    await db.tests.delete_many({"lecture_id": lecture_id})
    await db.attempts.delete_many({"lecture_id": lecture_id})
    await db.review_items.delete_many({"lecture_id": lecture_id})
    p = TRANSCRIPTS_DIR / f"{lecture_id}.txt"
    if p.exists():
        p.unlink()
    return {"ok": True}


@api.patch("/lectures/{lecture_id}/transcript", response_model=Lecture)
async def update_transcript(lecture_id: str, body: TranscriptUpdate):
    doc = await db.lectures.find_one({"id": lecture_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Lecture not found")
    lec = Lecture(**doc)
    lec.transcript = (lec.transcript + " " + body.transcript).strip() \
        if body.append and lec.transcript else body.transcript
    if body.duration_sec is not None:
        lec.duration_sec = body.duration_sec
    lec.updated_at = _now()
    await db.lectures.update_one({"id": lecture_id},
                                 {"$set": lec.model_dump()})
    _write_transcript_file(lec.id, lec.title, lec.transcript)
    return lec


def _write_transcript_file(lecture_id: str, title: str, transcript: str):
    safe_title = re.sub(r"[^\w\s-]", "", title)[:60].strip().replace(" ", "_")
    path = TRANSCRIPTS_DIR / f"{lecture_id}_{safe_title}.txt"
    # Overwrite existing per-lecture file
    for old in TRANSCRIPTS_DIR.glob(f"{lecture_id}_*.txt"):
        old.unlink()
    path.write_text(transcript, encoding="utf-8")


# ---- AI: summary ----

@api.post("/lectures/{lecture_id}/summary", response_model=Lecture)
async def generate_summary(lecture_id: str):
    doc = await db.lectures.find_one({"id": lecture_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Lecture not found")
    lec = Lecture(**doc)
    if not lec.transcript.strip():
        raise HTTPException(400, "Lecture has no transcript yet.")

    prompt = (
        "Below is the raw transcript of a university lecture (English). "
        "Produce study notes in RUSSIAN as a JSON object with this shape: "
        '{"summary": "<markdown notes in Russian, 400-800 words, with ## '
        'headings, bullet lists, and a **Определения** block>", '
        '"key_points": ["короткий тезис 1", ... 5-8 items in Russian]}\n'
        "IMPORTANT: Do NOT use LaTeX (\\[ \\], $$, \\frac). Write formulas "
        "as plain text (например: v = s / t; ΔH = -285 кДж/моль).\n\n"
        "TRANSCRIPT:\n\"\"\"\n" + lec.transcript[:15000] + "\n\"\"\""
    )
    raw = await _llm_text(f"summary-{lecture_id}", SUMMARY_SYSTEM, prompt)
    try:
        data = _extract_json(raw)
        lec.summary = data.get("summary", "").strip()
        lec.key_points = data.get("key_points", [])[:12]
    except Exception as e:
        logger.warning(f"JSON parse failed, using raw text. {e}")
        lec.summary = raw.strip()
        lec.key_points = []

    lec.updated_at = _now()
    lec.llm_mode = LLM_MODE
    await db.lectures.update_one({"id": lecture_id},
                                 {"$set": lec.model_dump()})
    return lec


# ---- AI: test generation ----

@api.post("/lectures/{lecture_id}/test", response_model=Test)
async def generate_test(lecture_id: str):
    doc = await db.lectures.find_one({"id": lecture_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Lecture not found")
    lec = Lecture(**doc)
    if not lec.summary:
        raise HTTPException(400,
                            "Generate the summary before creating a test.")

    prompt = (
        "From the following lecture study notes (in Russian), write a "
        "knowledge test IN RUSSIAN as strict JSON with this shape:\n"
        "{\n  \"questions\": [\n"
        "    {\"type\":\"mcq\", \"prompt\":\"...\", \"options\":[\"A) ...\",\"B) ...\",\"C) ...\",\"D) ...\"], \"answer\":\"B\", \"explanation\":\"...\"},\n"
        "    {\"type\":\"tf\",  \"prompt\":\"...\", \"answer\":\"True\", \"explanation\":\"...\"},\n"
        "    {\"type\":\"short\", \"prompt\":\"...\", \"answer\":\"ожидаемая короткая фраза\", \"explanation\":\"...\"}\n"
        "  ]\n}\n"
        "Rules: produce exactly 8 questions -> 4 MCQ, 2 True/False, 2 short answer. "
        "MCQ answer field MUST be a single letter A|B|C|D matching the correct option. "
        "TF answer MUST be exactly 'True' or 'False' (English, the UI localizes it). "
        "Prompts, options, explanations MUST BE IN RUSSIAN. "
        "Short answers must be 1-6 words in Russian. "
        "Return ONLY the JSON, no prose.\n\n"
        "NOTES:\n\"\"\"\n" + (lec.summary or "")[:12000] + "\n\"\"\""
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
            logger.warning(f"Skipping bad question: {ex} {q}")
    if not questions:
        raise HTTPException(500, "LLM returned no usable questions.")

    test = Test(lecture_id=lecture_id, questions=questions)
    await db.tests.insert_one(test.model_dump())
    return test


@api.get("/lectures/{lecture_id}/tests", response_model=List[Test])
async def list_tests(lecture_id: str):
    docs = await db.tests.find({"lecture_id": lecture_id},
                               {"_id": 0}).sort("created_at", -1).to_list(50)
    return [Test(**d) for d in docs]


@api.get("/tests/{test_id}", response_model=Test)
async def get_test(test_id: str):
    doc = await db.tests.find_one({"id": test_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Test not found")
    return Test(**doc)


# ---- Grading ----

class GradeBody(BaseModel):
    answers: List[Answer]


def _norm(s: str) -> str:
    return re.sub(r"[^\w\s]+", " ", (s or "").lower(), flags=re.UNICODE).strip()


@api.post("/tests/{test_id}/grade", response_model=TestAttempt)
async def grade(test_id: str, body: GradeBody):
    doc = await db.tests.find_one({"id": test_id}, {"_id": 0})
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
        else:  # short answer -> lenient token overlap
            expected = set(_norm(q.answer).split())
            got = set(_norm(resp).split())
            if not expected:
                is_ok = False
            else:
                overlap = len(expected & got) / len(expected)
                is_ok = overlap >= 0.6
        if is_ok:
            correct_count += 1
        graded.append(GradedAnswer(question_id=q.id, response=resp,
                                   correct_answer=q.answer, is_correct=is_ok,
                                   explanation=q.explanation))

    total = len(test.questions)
    score = int(round((correct_count / total) * 100)) if total else 0
    attempt = TestAttempt(test_id=test_id, lecture_id=test.lecture_id,
                          graded=graded, score=score, total=total,
                          correct=correct_count)
    await db.attempts.insert_one(attempt.model_dump())

    # ---- Spaced Repetition scheduling ----
    now = datetime.now(timezone.utc)
    for q, g in zip(test.questions, graded):
        existing = await db.review_items.find_one(
            {"lecture_id": test.lecture_id, "question_id": q.id},
            {"_id": 0},
        )
        if g.is_correct:
            if not existing:
                continue  # never missed -> nothing to schedule
            new_interval = min(30, max(1, existing.get("interval_days", 1) * 2))
            due = now + timedelta(days=new_interval)
            await db.review_items.update_one(
                {"id": existing["id"]},
                {"$set": {"interval_days": new_interval,
                          "due_at": due.isoformat(),
                          "streak": existing.get("streak", 0) + 1,
                          "last_result": "correct"}},
            )
        else:
            if existing:
                await db.review_items.update_one(
                    {"id": existing["id"]},
                    {"$set": {"interval_days": 1,
                              "due_at": (now + timedelta(days=1)).isoformat(),
                              "streak": 0,
                              "misses": existing.get("misses", 0) + 1,
                              "last_result": "wrong"}},
                )
            else:
                item = {
                    "id": str(uuid.uuid4()),
                    "lecture_id": test.lecture_id,
                    "question_id": q.id,
                    "question": q.model_dump(),
                    "interval_days": 1,
                    "due_at": (now + timedelta(days=1)).isoformat(),
                    "misses": 1,
                    "streak": 0,
                    "last_result": "wrong",
                    "created_at": _now(),
                }
                await db.review_items.insert_one(item)
    return attempt


@api.get("/lectures/{lecture_id}/attempts", response_model=List[TestAttempt])
async def list_attempts(lecture_id: str):
    docs = await db.attempts.find({"lecture_id": lecture_id},
                                  {"_id": 0}).sort("created_at",
                                                   -1).to_list(100)
    return [TestAttempt(**d) for d in docs]


# ---- Aggregate stats for dashboard ----

@api.get("/stats")
async def stats():
    lec_count = await db.lectures.count_documents({})
    test_count = await db.tests.count_documents({})
    attempt_count = await db.attempts.count_documents({})
    attempts = await db.attempts.find({}, {"_id": 0,
                                           "score": 1}).to_list(1000)
    avg = int(round(sum(a["score"] for a in attempts) / len(attempts))) \
        if attempts else 0

    # Streak: consecutive days (including today or yesterday) with review activity.
    days = await db.review_days.find({}, {"_id": 0, "day": 1}).to_list(1000)
    day_set = {d["day"] for d in days}
    today = datetime.now(timezone.utc).date()
    streak = 0
    # Grace: if reviewed today OR yesterday, streak is unbroken.
    cursor_day = today if today.isoformat() in day_set else (
        today - timedelta(days=1) if (today - timedelta(days=1)).isoformat() in day_set else None)
    while cursor_day and cursor_day.isoformat() in day_set:
        streak += 1
        cursor_day = cursor_day - timedelta(days=1)
    reviewed_today = today.isoformat() in day_set

    return {"lectures": lec_count, "tests": test_count,
            "attempts": attempt_count, "avg_score": avg,
            "streak": streak, "reviewed_today": reviewed_today}


@api.post("/transcribe-audio")
async def transcribe_audio(file: UploadFile = File(...)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY missing.")
    if not file.filename:
        raise HTTPException(400, "Empty upload")
    contents = await file.read()
    if len(contents) > 25 * 1024 * 1024:
        raise HTTPException(413, "File too large. Max 25 MB.")
    buf = io.BytesIO(contents)
    buf.name = file.filename  # Whisper client uses extension for format
    stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
    try:
        resp = await stt.transcribe(file=buf, model="whisper-1",
                                    response_format="json", language="en")
        text = getattr(resp, "text", None) or (
            resp.get("text") if isinstance(resp, dict) else str(resp))
        return {"text": text or ""}
    except Exception as e:
        logger.exception("whisper failed")
        raise HTTPException(502, f"Transcription failed: {e}")


# ============================================================================
# Spaced Repetition
# ============================================================================

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
async def review_due():
    now_iso = datetime.now(timezone.utc).isoformat()
    docs = await db.review_items.find(
        {"due_at": {"$lte": now_iso}}, {"_id": 0}
    ).sort("due_at", 1).to_list(500)
    return [ReviewItem(**d) for d in docs]


@api.get("/review/stats")
async def review_stats():
    now_iso = datetime.now(timezone.utc).isoformat()
    total = await db.review_items.count_documents({})
    due = await db.review_items.count_documents({"due_at": {"$lte": now_iso}})
    return {"total": total, "due": due}


@api.post("/review/{item_id}/answer")
async def review_answer(item_id: str, body: ReviewAnswer):
    doc = await db.review_items.find_one({"id": item_id}, {"_id": 0})
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
        due = now + timedelta(days=new_interval)
        await db.review_items.update_one(
            {"id": item_id},
            {"$set": {"interval_days": new_interval,
                      "due_at": due.isoformat(),
                      "streak": doc.get("streak", 0) + 1,
                      "last_result": "correct"}},
        )
        next_days = new_interval
    else:
        await db.review_items.update_one(
            {"id": item_id},
            {"$set": {"interval_days": 1,
                      "due_at": (now + timedelta(days=1)).isoformat(),
                      "streak": 0,
                      "misses": doc.get("misses", 0) + 1,
                      "last_result": "wrong"}},
        )
        next_days = 1

    # Track this day for the streak counter.
    today = now.strftime("%Y-%m-%d")
    await db.review_days.update_one(
        {"day": today}, {"$set": {"day": today}}, upsert=True,
    )

    return {"is_correct": is_ok,
            "correct_answer": q.answer,
            "explanation": q.explanation,
            "next_due_days": next_days}


@api.post("/review/seed-now")
async def review_seed_now():
    """Debug helper: mark all future review items as due right now."""
    now_iso = datetime.now(timezone.utc).isoformat()
    r = await db.review_items.update_many(
        {"due_at": {"$gt": now_iso}}, {"$set": {"due_at": now_iso}}
    )
    return {"updated": r.modified_count}


# ============================================================================
# Glossary
# ============================================================================

GLOSSARY_SYSTEM = (
    "You are a bilingual English↔Russian academic assistant. From a raw "
    "university lecture transcript in English, extract the ~10–15 most "
    "important domain-specific terms (nouns and short phrases) that a "
    "Russian-speaking student would want in a study glossary. Skip common "
    "words. Return strict JSON only."
)


@api.post("/lectures/{lecture_id}/glossary")
async def generate_glossary(lecture_id: str):
    doc = await db.lectures.find_one({"id": lecture_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Lecture not found")
    lec = Lecture(**doc)
    if not lec.transcript.strip():
        raise HTTPException(400, "Lecture has no transcript yet.")

    prompt = (
        "Extract a glossary from the following English lecture transcript. "
        "Return JSON exactly like:\n"
        "{\"terms\":[{\"term\":\"<English term>\","
        "\"translation\":\"<Russian translation>\","
        "\"definition\":\"<1-2 sentence definition in Russian>\"}]}\n"
        "Rules:\n"
        "- 8 to 15 items, ordered by importance.\n"
        "- Term must be the exact English form as used in the transcript "
        "(lowercase unless proper noun).\n"
        "- Definition in Russian, one or two sentences.\n"
        "- Skip common words (e.g. 'system', 'process' alone).\n\n"
        "TRANSCRIPT:\n\"\"\"\n" + lec.transcript[:15000] + "\n\"\"\""
    )
    raw = await _llm_text(f"glossary-{lecture_id}", GLOSSARY_SYSTEM, prompt)
    try:
        data = _extract_json(raw)
        terms = data.get("terms", [])[:20]
    except Exception as e:
        raise HTTPException(500, f"Failed to parse glossary JSON: {e}")

    # Sanitize entries
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

    await db.lectures.update_one(
        {"id": lecture_id},
        {"$set": {"glossary": clean, "updated_at": _now()}},
    )
    return {"terms": clean}


@api.get("/glossary/all")
async def glossary_all():
    """Aggregate every term across all lectures, deduped by lowercase term."""
    lectures = await db.lectures.find(
        {"glossary": {"$ne": []}},
        {"_id": 0, "id": 1, "title": 1, "glossary": 1, "created_at": 1},
    ).to_list(1000)
    seen: dict = {}
    for l in lectures:
        for t in l.get("glossary", []):
            key = t["term"].lower()
            if key in seen:
                continue
            seen[key] = {**t,
                         "lecture_id": l["id"],
                         "lecture_title": l["title"]}
    return {"terms": sorted(seen.values(), key=lambda x: x["term"].lower())}


# ============================================================================
# Weekly Digest (Resend)
# ============================================================================

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
<!doctype html>
<html><body style="margin:0;padding:0;background:#f4f1eb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1c201f;">
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
        <div style="font-size:13px;margin-top:4px;">{due_count} карточ{'ка' if due_count%10==1 and due_count%100!=11 else 'ки' if 2<=due_count%10<=4 and not 12<=due_count%100<=14 else 'ек'} готов{'а' if due_count%10==1 and due_count%100!=11 else 'ы'} к повторению прямо сейчас.</div>
      </div>
    </td></tr>
    <tr><td style="padding:0 40px 32px;font-size:11px;color:#8c9690;text-align:center;">
      upsidestudy — ваш помощник по лекциям.
    </td></tr>
  </table>
</td></tr></table></body></html>"""


async def _build_digest():
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    new_lectures = await db.lectures.find(
        {"created_at": {"$gte": week_ago}}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    now_iso = datetime.now(timezone.utc).isoformat()
    due_count = await db.review_items.count_documents({"due_at": {"$lte": now_iso}})
    attempts = await db.attempts.find(
        {"created_at": {"$gte": week_ago}}, {"_id": 0, "score": 1}
    ).to_list(500)
    avg_score = int(round(sum(a["score"] for a in attempts) / len(attempts))) if attempts else 0
    subject = f"upsidestudy · {len(new_lectures)} лекций, {due_count} к повторению"
    html = _digest_html(new_lectures, due_count, avg_score)
    return {"subject": subject, "html": html,
            "new_lectures": len(new_lectures),
            "due_count": due_count, "avg_score": avg_score}


@api.get("/digest/preview")
async def digest_preview():
    return await _build_digest()


class DigestSend(BaseModel):
    to: Optional[str] = None


@api.post("/digest/send")
async def digest_send(body: DigestSend = DigestSend()):
    if not RESEND_API_KEY:
        raise HTTPException(400, "Resend не настроен (нет RESEND_API_KEY).")
    recipient = (body.to or DIGEST_EMAIL or "").strip()
    if not recipient:
        raise HTTPException(400, "Не указан адрес получателя.")
    digest = await _build_digest()
    params = {"from": SENDER_EMAIL, "to": [recipient],
              "subject": digest["subject"], "html": digest["html"]}
    try:
        result = await asyncio.to_thread(resend.Emails.send, params)
    except Exception as e:
        logger.exception("Resend failed")
        raise HTTPException(502, f"Resend error: {e}")
    return {"ok": True, "email_id": getattr(result, "id", None) or (
        result.get("id") if isinstance(result, dict) else None),
            "to": recipient}


# ============================================================================
# Scheduler — weekly digest cron
# ============================================================================

scheduler: Optional[AsyncIOScheduler] = None


async def _scheduled_digest():
    if not (RESEND_API_KEY and DIGEST_EMAIL):
        logger.info("Weekly digest skipped: Resend not configured.")
        return
    try:
        await digest_send(DigestSend(to=DIGEST_EMAIL))  # type: ignore[arg-type]
        logger.info(f"Weekly digest sent to {DIGEST_EMAIL}")
    except Exception as e:
        logger.exception(f"Weekly digest failed: {e}")


@app.on_event("startup")
async def _startup():
    global scheduler
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(_scheduled_digest,
                      CronTrigger(day_of_week=DIGEST_CRON_DAY,
                                  hour=DIGEST_CRON_HOUR, minute=0),
                      id="weekly-digest", replace_existing=True)
    scheduler.start()
    logger.info(f"Scheduler started · digest on {DIGEST_CRON_DAY} {DIGEST_CRON_HOUR:02d}:00 UTC")


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def _shutdown():
    if scheduler:
        scheduler.shutdown(wait=False)
    mongo_client.close()
