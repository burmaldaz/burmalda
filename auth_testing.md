# Auth Testing Playbook (upsidestudy)

## Endpoints
- POST /api/auth/register {email, password, name?}
- POST /api/auth/login {email, password}
- POST /api/auth/logout
- GET  /api/auth/me
- POST /api/auth/refresh
- POST /api/streak/freeze  (auth)  — consume one weekly streak freeze

## Cookie-based auth
- On login/register the server sets **httpOnly** `access_token` (15 min) and `refresh_token` (7 days).
- Frontend uses `axios.defaults.withCredentials = true`; do not read tokens from JS.

## Test credentials
See /app/memory/test_credentials.md — seeded admin user credentials are written there.

## Manual verification
```bash
curl -c /tmp/c.txt -X POST $BASE/api/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"student@example.com","password":"student123","name":"Student"}'
curl -b /tmp/c.txt $BASE/api/auth/me
curl -b /tmp/c.txt $BASE/api/stats  # user-scoped stats
```

## Per-user data isolation
- Every document in `lectures`, `tests`, `attempts`, `review_items`, `review_days` has `user_id`.
- Endpoints filter by `user_id = current_user.id`.
- `/api/glossary/all`, `/api/digest/preview`, `/api/stats` all respect user scope.

## Phone recording (QR flow)
- Desktop creates a lecture → returns `record_token` (24-hour JWT with `{lecture_id, type:"record"}`).
- QR encodes `/m/{lecture_id}?t={token}`. Mobile page sends token as `Authorization: Bearer {token}` for the transcript PATCH.
- The PATCH endpoint accepts either a user's access token OR a valid record token that matches `lecture_id`.

## Streak Freeze rules
- One freeze per rolling 7-day window.
- A freeze covers the next 2 missing days when computing streak, so you can miss up to 2 days without losing the chain.
