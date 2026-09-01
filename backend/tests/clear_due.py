"""Helper: answer all currently-due review items correctly so the UI empty
state can be verified. Run with `restore` arg to put items back to due."""
import sys
import requests
from dotenv import dotenv_values

API = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"

if len(sys.argv) > 1 and sys.argv[1] == "restore":
    print(requests.post(f"{API}/review/seed-now").json())
else:
    due = requests.get(f"{API}/review/due").json()
    for item in due:
        r = requests.post(f"{API}/review/{item['id']}/answer",
                          json={"response": item["question"]["answer"]})
        print(item["question"]["type"], r.status_code, r.json().get("is_correct"),
              r.json().get("next_due_days"))
    print("stats:", requests.get(f"{API}/review/stats").json())
