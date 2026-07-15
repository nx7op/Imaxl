"""
config.py — All configuration for the VC Music Bot.
"""

import os
import sys

IS_RAILWAY = bool(
    os.environ.get("RAILWAY_ENVIRONMENT")
    or os.environ.get("RAILWAY_PROJECT_ID")
    or os.environ.get("RAILWAY_SERVICE_ID")
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _required(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        sys.exit(
            f"❌ Missing required environment variable: {name}\n"
            f"   Set it in Railway -> your service -> Variables tab."
        )
    return val


API_ID = int(_required("API_ID"))
API_HASH = _required("API_HASH")
BOT_TOKEN = _required("BOT_TOKEN")
SESSION_STRING = _required("SESSION_STRING")

SAAVN_API_BASE = os.environ.get("SAAVN_API_BASE", "https://saavn.sumit.co").rstrip("/")
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "@stillrahul")
OWNER_ID = _env_int("OWNER_ID", 0)
SUDO_USERS = {
    int(x) for x in os.environ.get("SUDO_USERS", "").replace(" ", "").split(",") if x.isdigit()
}
if OWNER_ID:
    SUDO_USERS.add(OWNER_ID)

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "./downloads")
MAX_QUEUE_SIZE = _env_int("MAX_QUEUE_SIZE", 50)
AUTO_LEAVE_SECONDS = _env_int("AUTO_LEAVE_SECONDS", 180)
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "15"))
AI_SUGGEST_BASE = os.environ.get("AI_SUGGEST_BASE", "https://text.pollinations.ai").rstrip("/")
AI_SUGGEST_TIMEOUT = float(os.environ.get("AI_SUGGEST_TIMEOUT", "8"))
BOT_TAGLINE = "FastTrack VC Music"
