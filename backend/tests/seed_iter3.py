"""Seed a lecture with transcript + glossary for frontend testing."""
import os
import requests
from dotenv import dotenv_values

base = os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]
API = base.rstrip("/") + "/api"

TRANSCRIPT = (
    "Today we discuss photosynthesis in detail. Chlorophyll inside the chloroplast "
    "absorbs photons and drives the light-dependent reactions, producing ATP and NADPH. "
    "The Calvin cycle then fixes carbon dioxide into glucose using the enzyme RuBisCO. "
    "Stomata regulate gas exchange, and transpiration pulls water up the xylem. "
    "Cellular respiration in the mitochondria later oxidizes glucose to release energy."
)

r = requests.post(f"{API}/lectures", json={
    "title": "TEST_Glossary UI Seed",
    "source_type": "paste",
    "transcript": TRANSCRIPT,
}, timeout=60)
r.raise_for_status()
lid = r.json()["id"]
print("LECTURE_ID", lid)
g = requests.post(f"{API}/lectures/{lid}/glossary", timeout=180)
print("glossary status", g.status_code, len(g.json().get("terms", [])))
print("terms", [t["term"] for t in g.json().get("terms", [])])
