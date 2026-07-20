import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS_ROOT = BACKEND_ROOT / "downloads"
FRONTEND_DIST = BACKEND_ROOT.parent / "frontend" / "dist"

PORT = int(os.environ.get("PORT", 8765))
TIMEOUT_SECONDS = int(os.environ.get("TIMEOUT_SECONDS", 45))
ANALYZE_TIMEOUT_SECONDS = int(os.environ.get("ANALYZE_TIMEOUT_SECONDS", 30))
FILE_MAX_AGE_MINUTES = int(os.environ.get("FILE_MAX_AGE_MINUTES", 30))
MP3_BITRATE_CHOICES = (128, 192, 320)

LIST_ITEM_CAP = int(os.environ.get("LIST_ITEM_CAP", 24))
LIST_TIMEOUT_SECONDS = int(os.environ.get("LIST_TIMEOUT_SECONDS", 25))
BATCH_MAX_ITEMS = int(os.environ.get("BATCH_MAX_ITEMS", 8))
BATCH_CONCURRENCY = int(os.environ.get("BATCH_CONCURRENCY", 3))
BATCH_ITEM_TIMEOUT_SECONDS = int(os.environ.get("BATCH_ITEM_TIMEOUT_SECONDS", 30))

PLATFORM_DIRS = {
    "tiktok": DOWNLOADS_ROOT / "tiktok",
    "instagram": DOWNLOADS_ROOT / "instagram",
    "facebook": DOWNLOADS_ROOT / "facebook",
    "youtube": DOWNLOADS_ROOT / "youtube",
}

for _dir in PLATFORM_DIRS.values():
    _dir.mkdir(parents=True, exist_ok=True)
