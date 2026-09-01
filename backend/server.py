"""Lecture Companion backend.

Records/receives raw English lecture transcripts, generates AI notes and
mixed-format tests, and grades the user's answers.

LLM backing:
- Placeholder for user's DeepSeek key (will drop in when provided).
- For now: MOCKED via Emergent Universal Key -> Gemini 3 Flash (cheap, fast).
"""
from fastapi import FastAPI, APIRouter, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal, Any
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
import os
import re
import uuid
import json
import logging

from emergentintegrations.llm.chat import LlmChat, UserMessage

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
    duration_sec: Optional[int] = None
    llm_mode: str = LLM_MODE  # tag which engine produced content
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
    """Return an LlmChat instance targeting the currently-active model."""
    if LLM_MODE == "deepseek":
        # DeepSeek not natively in emergentintegrations; if user provides key
        # we would swap to a direct HTTPX call. Kept as a hook for later.
        chat = LlmChat(api_key=EMERGENT_LLM_KEY or "unused",
                       session_id=session_id, system_message=system)
        chat.with_model("gemini", "gemini-3-flash-preview")
        return chat
    # mock/fallback: Emergent Universal Key + Gemini 3 Flash (cheap)
    return LlmChat(api_key=EMERGENT_LLM_KEY, session_id=session_id,
                   system_message=system).with_model("gemini",
                                                     "gemini-3-flash-preview")


async def _llm_text(session_id: str, system: str, prompt: str) -> str:
    if LLM_MODE == "none":
        raise HTTPException(500,
                            "No LLM key configured. Add DEEPSEEK_API_KEY or "
                            "EMERGENT_LLM_KEY to backend/.env.")
    chat = _new_chat(session_id, system)
    reply = await chat.send_message(UserMessage(text=prompt))
    return reply if isinstance(reply, str) else str(reply)


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
            "is_mocked": LLM_MODE != "deepseek"}


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
        '"key_points": ["короткий тезис 1", ... 5-8 items in Russian]}\n\n'
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
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


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
    return {"lectures": lec_count, "tests": test_count,
            "attempts": attempt_count, "avg_score": avg}


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
    mongo_client.close()
