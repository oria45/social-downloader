import os
from pathlib import Path

from app import paths

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS_ROOT = paths.writable_data_dir()
FRONTEND_DIST = paths.frontend_dist_dir()

PORT = int(os.environ.get("PORT", 8765))
TIMEOUT_SECONDS = int(os.environ.get("TIMEOUT_SECONDS", 45))
# Separate, longer budget for the VP9->h264 transcode pass: CPU-bound video
# encoding is much slower than a network download/merge, especially on
# Render's free-tier CPU - confirmed empirically (an Instagram VP9 reel that
# downloads in seconds locally hit the 45s download timeout once transcoding
# was added, on Render specifically).
TRANSCODE_TIMEOUT_SECONDS = int(os.environ.get("TRANSCODE_TIMEOUT_SECONDS", 90))
ANALYZE_TIMEOUT_SECONDS = int(os.environ.get("ANALYZE_TIMEOUT_SECONDS", 30))
FILE_MAX_AGE_MINUTES = int(os.environ.get("FILE_MAX_AGE_MINUTES", 30))
MP3_BITRATE_CHOICES = (128, 192, 320)

LIST_ITEM_CAP = int(os.environ.get("LIST_ITEM_CAP", 24))
LIST_TIMEOUT_SECONDS = int(os.environ.get("LIST_TIMEOUT_SECONDS", 25))
BATCH_MAX_ITEMS = int(os.environ.get("BATCH_MAX_ITEMS", 8))
BATCH_CONCURRENCY = int(os.environ.get("BATCH_CONCURRENCY", 3))
BATCH_ITEM_TIMEOUT_SECONDS = int(os.environ.get("BATCH_ITEM_TIMEOUT_SECONDS", 30))

# PO token provider (script mode) used to bypass YouTube's bot-check on
# datacenter IPs (e.g. Render). Empty/missing in local dev is fine - yt-dlp
# just skips the token and YouTube usually still works from residential IPs.
YOUTUBE_POT_SERVER_HOME = os.environ.get(
    "YOUTUBE_POT_SERVER_HOME", "/opt/bgutil-ytdlp-pot-provider/server"
)

PLATFORM_DIRS = {
    "tiktok": DOWNLOADS_ROOT / "tiktok",
    "instagram": DOWNLOADS_ROOT / "instagram",
    "facebook": DOWNLOADS_ROOT / "facebook",
    "youtube": DOWNLOADS_ROOT / "youtube",
    "twitter": DOWNLOADS_ROOT / "twitter",
}

for _dir in PLATFORM_DIRS.values():
    _dir.mkdir(parents=True, exist_ok=True)
