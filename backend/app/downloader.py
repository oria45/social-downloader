import asyncio
import json
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlsplit

from app.config import ANALYZE_TIMEOUT_SECONDS, PLATFORM_DIRS, TIMEOUT_SECONDS
from app.errors import (
    DownloadFailedError,
    DownloadTimeoutError,
    ToolNotInstalledError,
    classify_stderr,
)

Platform = Literal["tiktok", "instagram", "facebook", "youtube"]


class Selection(TypedDict, total=False):
    type: Literal["video", "audio"]
    height: int
    bitrate: int


class AnalysisResult(TypedDict, total=False):
    supports_quality_selection: bool
    title: str | None
    thumbnail: str | None
    video_heights: list[int]
    best_audio_abr: float

TIKTOK_HOSTS = {"tiktok.com", "vm.tiktok.com", "vt.tiktok.com", "m.tiktok.com"}
INSTAGRAM_HOSTS = {"instagram.com"}
FACEBOOK_HOSTS = {"facebook.com", "m.facebook.com", "web.facebook.com", "fb.watch"}
YOUTUBE_HOSTS = {"youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}


def detect_platform(url: str) -> Platform | None:
    hostname = urlsplit(url).hostname
    if not hostname:
        return None
    hostname = hostname.lower()
    if hostname.startswith("www."):
        hostname = hostname[len("www.") :]

    if hostname in TIKTOK_HOSTS:
        return "tiktok"
    if hostname in INSTAGRAM_HOSTS:
        return "instagram"
    if hostname in FACEBOOK_HOSTS:
        return "facebook"
    if hostname in YOUTUBE_HOSTS:
        return "youtube"
    return None


def build_yt_dlp_args(url: str, out_dir: Path, selection: Selection | None = None) -> list[str]:
    args = ["yt-dlp", "--no-playlist", "--playlist-items", "1", "-P", str(out_dir)]

    if selection and selection["type"] == "audio":
        args += ["-x", "--audio-format", "mp3", "--audio-quality", f"{selection['bitrate']}K"]
    elif selection and selection["type"] == "video":
        height = selection["height"]
        args += [
            "-f",
            f"bestvideo[height<={height}]+bestaudio/best[height<={height}]",
            "--merge-output-format",
            "mp4",
        ]

    args += ["-o", "%(id)s.%(ext)s", "--print", "after_move:filepath", url]
    return args


def build_yt_dlp_analyze_args(url: str) -> list[str]:
    return ["yt-dlp", "-J", "--no-warnings", "--no-playlist", "--playlist-items", "1", url]


def build_gallery_dl_args(url: str, out_dir: Path) -> list[str]:
    return [
        "gallery-dl",
        "--range",
        "1",
        # -D (exact directory) rather than -d (base + site/user subfolders):
        # -d would nest output under out_dir/<site>/<user>/..., breaking the
        # flat before/after diff used to detect downloaded files below.
        "-D",
        str(out_dir),
        url,
    ]


async def _run_subprocess(args: list[str], timeout: int) -> tuple[int, bytes, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ToolNotInstalledError(
            "A required tool is missing. Re-run run.command to reinstall dependencies."
        ) from exc

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise DownloadTimeoutError(
            "Download timed out. The link may be invalid or the platform is blocking automated access."
        ) from exc

    return proc.returncode, stdout, stderr


async def _run_yt_dlp(url: str, out_dir: Path, selection: Selection | None = None) -> list[Path]:
    args = build_yt_dlp_args(url, out_dir, selection)
    returncode, stdout, stderr = await _run_subprocess(args, TIMEOUT_SECONDS)
    if returncode != 0:
        raise classify_stderr(stderr.decode(errors="replace"))

    lines = [line.strip() for line in stdout.decode(errors="replace").splitlines() if line.strip()]
    if not lines:
        raise classify_stderr(stderr.decode(errors="replace"))
    return [Path(lines[-1])]


async def analyze_url(url: str) -> AnalysisResult:
    args = build_yt_dlp_analyze_args(url)
    returncode, stdout, stderr = await _run_subprocess(args, ANALYZE_TIMEOUT_SECONDS)
    if returncode != 0:
        error = classify_stderr(stderr.decode(errors="replace"))
        if isinstance(error, DownloadFailedError):
            # yt-dlp can't extract this URL at all (e.g. an Instagram photo post,
            # which gallery-dl handles instead) — that's expected, not a real error.
            return {"supports_quality_selection": False}
        raise error

    try:
        info = json.loads(stdout.decode(errors="replace"))
    except json.JSONDecodeError as exc:
        raise DownloadFailedError("Couldn't read format information for this link.") from exc

    video_heights: set[int] = set()
    best_audio_abr = 0.0
    for fmt in info.get("formats", []):
        height = fmt.get("height")
        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")
        has_video = bool(vcodec) and vcodec != "none"
        has_audio = bool(acodec) and acodec != "none"

        if has_video and isinstance(height, int):
            video_heights.add(height)
        if has_audio and not has_video:
            best_audio_abr = max(best_audio_abr, fmt.get("abr") or 0)

    return {
        "supports_quality_selection": True,
        "title": info.get("title"),
        "thumbnail": info.get("thumbnail"),
        "video_heights": sorted(video_heights, reverse=True),
        "best_audio_abr": best_audio_abr,
    }


async def _run_gallery_dl(url: str, out_dir: Path) -> list[Path]:
    before = set(out_dir.iterdir()) if out_dir.exists() else set()
    args = build_gallery_dl_args(url, out_dir)
    returncode, stdout, stderr = await _run_subprocess(args, TIMEOUT_SECONDS)
    if returncode != 0:
        raise classify_stderr(stderr.decode(errors="replace"))

    after = set(out_dir.iterdir()) if out_dir.exists() else set()
    new_files = sorted(after - before)
    if not new_files:
        raise classify_stderr(stderr.decode(errors="replace"))
    return new_files


async def run_download(
    url: str, platform: Platform, selection: Selection | None = None
) -> list[Path]:
    out_dir = PLATFORM_DIRS[platform]

    if platform in ("tiktok", "youtube"):
        return await _run_yt_dlp(url, out_dir, selection)

    try:
        return await _run_yt_dlp(url, out_dir, selection)
    except ToolNotInstalledError:
        raise
    except Exception:
        return await _run_gallery_dl(url, out_dir)
