from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from app.database import Base, engine
from app.routes import (
    auth as auth_router, courses, departments, employees, uploads,
    enrollments, quizzes, assignments, certificates, messages, doubts,
    live_classes, activity, notifications, leaderboard, settings as settings_router
)
import os
import time
from collections import defaultdict
import threading

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Company LMS API",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": True},
    redirect_slashes=False,
)

# ── In-memory rate limiter (fixed window, no external deps) ───────────────────
_rate_store: dict = defaultdict(list)
_rate_lock = threading.Lock()

# (max_requests, window_seconds) per path prefix
RATE_RULES: dict = {
    "/auth/login":           (5,  60),   # 5 attempts / minute per IP
    "/auth/register":        (10, 60),   # 10 registrations / minute
    "/auth/forgot-password": (3,  60),   # 3 reset requests / minute
    "/auth/reset-password":  (5,  60),   # 5 resets / minute
}
_DEFAULT_RATE = (200, 60)  # 200 req / minute globally per IP

def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return (request.client.host if request.client else "unknown")

def _is_rate_limited(ip: str, path: str) -> bool:
    """Return True if the request should be blocked (rate limit exceeded)."""
    max_req, window = RATE_RULES.get(path, _DEFAULT_RATE)
    key = f"{ip}:{path}"
    now = time.monotonic()
    with _rate_lock:
        times = _rate_store[key]
        # Slide window
        _rate_store[key] = [t for t in times if now - t < window]
        if len(_rate_store[key]) >= max_req:
            return True
        _rate_store[key].append(now)
        return False

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Skip rate-limiting for WebSocket upgrades (handled at connect time)
    if request.headers.get("upgrade", "").lower() == "websocket":
        return await call_next(request)
    ip = _client_ip(request)
    if _is_rate_limited(ip, request.url.path):
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down and retry."},
        )
    return await call_next(request)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Set ALLOWED_ORIGINS in .env for production, e.g.:
#   ALLOWED_ORIGINS=https://app.yourcompany.com,https://yourcompany.com
_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000"
)
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router.router)
app.include_router(employees.router)
app.include_router(departments.router)
app.include_router(courses.router)
app.include_router(uploads.router)
app.include_router(uploads.course_thumb_router)
app.include_router(enrollments.router)
app.include_router(quizzes.router)
app.include_router(assignments.router)
app.include_router(certificates.router)
app.include_router(messages.router)
app.include_router(doubts.router)
app.include_router(live_classes.router)
app.include_router(activity.router)
app.include_router(notifications.router)
app.include_router(leaderboard.router)
app.include_router(settings_router.router)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    ico_path = os.path.join(os.path.dirname(__file__), "static", "favicon.ico")
    if not os.path.isfile(ico_path):
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    return FileResponse(ico_path)


@app.get("/")
def root():
    return {"message": "Company LMS API is running"}
