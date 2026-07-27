import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _bundle_dir() -> Path:
    # sys._MEIPASS is the correct bundled-data base in both PyInstaller
    # onefile and onedir modes - do not use sys.executable's directory,
    # its layout differs across PyInstaller versions (e.g. _internal/).
    return Path(getattr(sys, "_MEIPASS", BACKEND_ROOT))


def tool_path(name: str) -> str:
    if not is_frozen():
        return name  # dev/Docker: resolved via PATH, unchanged from today
    return str(_bundle_dir() / "tools" / f"{name}.exe")


def frontend_dist_dir() -> Path:
    if not is_frozen():
        return BACKEND_ROOT.parent / "frontend" / "dist"
    return _bundle_dir() / "frontend_dist"


def writable_data_dir() -> Path:
    if not is_frozen():
        return BACKEND_ROOT / "downloads"
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "SocialDownloader" / "downloads"
    return Path.home() / "SocialDownloader" / "downloads"
