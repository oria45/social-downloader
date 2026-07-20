import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlsplit

from app.config import (
    ANALYZE_TIMEOUT_SECONDS,
    BATCH_CONCURRENCY,
    BATCH_ITEM_TIMEOUT_SECONDS,
    LIST_ITEM_CAP,
    LIST_TIMEOUT_SECONDS,
    PLATFORM_DIRS,
    TIMEOUT_SECONDS,
)
from app.errors import (
    DownloadFailedError,
    DownloadTimeoutError,
    ToolNotInstalledError,
    classify_stderr,
)

logger = logging.getLogger(__name__)

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


class ProfileItem(TypedDict):
    id: str
    title: str | None
    thumbnail_url: str | None
    url: str


# Platforms with a working flat-playlist listing (no login required). Instagram
# is deliberately excluded: gallery-dl's profile/post listing requires session
# cookies and silently returns nothing without them (confirmed empirically).
PROFILE_LISTING_PLATFORMS: set[Platform] = {"tiktok", "youtube"}

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


def is_profile_url(url: str, platform: Platform) -> bool:
    if platform not in PROFILE_LISTING_PLATFORMS:
        return False

    path = urlsplit(url).path.rstrip("/")

    if platform == "tiktok":
        return bool(re.fullmatch(r"/@[^/]+", path))

    if platform == "youtube":
        if re.search(r"/watch(/|$)", path) or re.fullmatch(r"/shorts/[^/]+", path):
            return False
        return bool(
            re.fullmatch(
                r"/(@[^/]+|channel/[^/]+|c/[^/]+|user/[^/]+)(/videos|/shorts|/streams)?", path
            )
        )

    return False


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


def _youtube_listing_url(url: str) -> str:
    # A bare YouTube channel URL (e.g. /@handle) enumerates ALL of its tabs
    # (Videos + Shorts + Live) as separate nested playlists, so --playlist-end
    # applies per-tab rather than as a global cap (confirmed empirically: a cap
    # of 3 returned 9 entries). Scoping to /videos explicitly fixes this.
    parsed = urlsplit(url)
    path = parsed.path.rstrip("/")
    if not re.search(r"/(videos|shorts|streams)$", path):
        path = f"{path}/videos"
    return parsed._replace(path=path).geturl()


def build_yt_dlp_list_args(url: str, limit: int) -> list[str]:
    return [
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        "--playlist-end",
        str(limit),
        "--no-warnings",
        url,
    ]


def _best_thumbnail_url(entry: dict) -> str | None:
    thumbnails = entry.get("thumbnails") or []
    if not thumbnails:
        return entry.get("thumbnail")
    best = max(thumbnails, key=lambda t: t.get("preference", t.get("height", 0)) or 0)
    return best.get("url")


async def list_profile_items(url: str, platform: Platform) -> tuple[list[ProfileItem], bool]:
    if platform == "youtube":
        url = _youtube_listing_url(url)

    args = build_yt_dlp_list_args(url, LIST_ITEM_CAP)
    returncode, stdout, stderr = await _run_subprocess(args, LIST_TIMEOUT_SECONDS)
    if returncode != 0:
        raise classify_stderr(stderr.decode(errors="replace"))

    items: list[ProfileItem] = []
    for line in stdout.decode(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        entry_url = entry.get("url") or entry.get("webpage_url")
        if not entry_url:
            continue
        items.append(
            {
                "id": str(entry.get("id", "")),
                "title": entry.get("title"),
                "thumbnail_url": _best_thumbnail_url(entry),
                "url": entry_url,
            }
        )

    if not items:
        raise DownloadFailedError("Couldn't find any videos for this profile.")

    truncated = len(items) >= LIST_ITEM_CAP
    return items[:LIST_ITEM_CAP], truncated


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

    if proc.returncode != 0:
        logger.warning(
            "Subprocess failed (exit %s): %s\nstderr: %s",
            proc.returncode,
            " ".join(args),
            stderr.decode(errors="replace")[-2000:],
        )

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


async def run_batch_download(urls: list[str], platform: Platform) -> list[Path]:
    semaphore = asyncio.Semaphore(BATCH_CONCURRENCY)

    async def _download_one(url: str) -> Path | None:
        async with semaphore:
            try:
                files = await asyncio.wait_for(
                    run_download(url, platform), timeout=BATCH_ITEM_TIMEOUT_SECONDS
                )
                return files[0] if files else None
            except ToolNotInstalledError:
                raise
            except Exception as exc:
                logger.warning("Batch item failed: %s (%s)", url, exc)
                return None

    results = await asyncio.gather(*(_download_one(u) for u in urls))
    successful = [p for p in results if p is not None]
    if not successful:
        raise DownloadFailedError("None of the selected items could be downloaded.")
    return successful
