import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlsplit

from app import paths
from app.config import (
    ANALYZE_TIMEOUT_SECONDS,
    BATCH_CONCURRENCY,
    BATCH_ITEM_TIMEOUT_SECONDS,
    LIST_ITEM_CAP,
    LIST_TIMEOUT_SECONDS,
    PLATFORM_DIRS,
    TIMEOUT_SECONDS,
    YOUTUBE_POT_SERVER_HOME,
)
from app.errors import (
    DownloadFailedError,
    DownloadTimeoutError,
    ToolNotInstalledError,
    classify_stderr,
)

logger = logging.getLogger(__name__)

Platform = Literal["tiktok", "instagram", "facebook", "youtube", "twitter"]


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
    view_count: int | None


# Platforms with a working flat-playlist listing (no login required). Instagram
# is deliberately excluded: gallery-dl's profile/post listing requires session
# cookies and silently returns nothing without them (confirmed empirically).
PROFILE_LISTING_PLATFORMS: set[Platform] = {"tiktok", "youtube"}

TIKTOK_HOSTS = {"tiktok.com", "vm.tiktok.com", "vt.tiktok.com", "m.tiktok.com"}
INSTAGRAM_HOSTS = {"instagram.com"}
FACEBOOK_HOSTS = {"facebook.com", "m.facebook.com", "web.facebook.com", "fb.watch"}
YOUTUBE_HOSTS = {"youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
TWITTER_HOSTS = {"twitter.com", "mobile.twitter.com", "x.com", "mobile.x.com"}


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
    if hostname in TWITTER_HOSTS:
        return "twitter"
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


def _youtube_pot_args(platform: Platform | None) -> list[str]:
    if platform != "youtube":
        return []

    # Forcing player_client=android,web was tried as a Render bot-check
    # workaround, but it never actually fixed that (confirmed - Render still
    # got blocked) and it does have a real cost: those two clients are
    # SABR-restricted without a JS runtime/PO token, which silently drops
    # every format above 360p (confirmed: 27 formats incl. 1080p normally,
    # only 5 formats capped at 360p with the override). Not worth keeping.

    # Only applies when the pot-provider server dir was actually baked into
    # the image (see backend/Dockerfile) - absent in local dev, yt-dlp just
    # runs without a token, which is fine since only Render's IP is blocked.
    if Path(YOUTUBE_POT_SERVER_HOME).exists():
        return ["--extractor-args", f"youtubepot-bgutilscript:server_home={YOUTUBE_POT_SERVER_HOME}"]
    return []


def _ffmpeg_location_args() -> list[str]:
    # Frozen desktop build: yt-dlp needs to be told where the bundled ffmpeg
    # lives, since it isn't on PATH like in dev/Docker.
    if not paths.is_frozen():
        return []
    ffmpeg_dir = str(Path(paths.tool_path("ffmpeg")).parent)
    return ["--ffmpeg-location", ffmpeg_dir]


def build_yt_dlp_args(
    url: str,
    out_dir: Path,
    selection: Selection | None = None,
    platform: Platform | None = None,
) -> list[str]:
    args = [paths.tool_path("yt-dlp"), "--no-playlist", "--playlist-items", "1", "-P", str(out_dir)]

    if selection and selection["type"] == "audio":
        args += ["-x", "--audio-format", "mp3", "--audio-quality", f"{selection['bitrate']}K"]
    elif selection and selection["type"] == "video":
        height = selection["height"]
        # Prefer an h264/avc video stream first: some sources (e.g. Instagram
        # reels) only offer VP9 DASH streams, and VP9-in-mp4 (as opposed to
        # VP9-in-webm) fails to decode on plenty of devices/players (notably
        # iOS) even though the file itself is valid - confirmed empirically.
        # Falls through to any codec, then yt-dlp's own single-format "best",
        # if no h264 alternative exists - _maybe_transcode_to_h264 below
        # catches that remaining case with an actual re-encode.
        args += [
            "-f",
            f"bestvideo[vcodec^=avc][height<={height}]+bestaudio/"
            f"bestvideo[height<={height}]+bestaudio/best[height<={height}]",
            "--merge-output-format",
            "mp4",
        ]

    args += _youtube_pot_args(platform)
    args += _ffmpeg_location_args()
    args += ["-o", "%(id)s.%(ext)s", "--print", "after_move:filepath", url]
    return args


def build_yt_dlp_analyze_args(url: str, platform: Platform | None = None) -> list[str]:
    return [
        paths.tool_path("yt-dlp"),
        "-J",
        "--no-warnings",
        "--no-playlist",
        "--playlist-items",
        "1",
        *_youtube_pot_args(platform),
        *_ffmpeg_location_args(),
        url,
    ]


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


def build_yt_dlp_list_args(url: str, limit: int, platform: Platform | None = None) -> list[str]:
    return [
        paths.tool_path("yt-dlp"),
        "--flat-playlist",
        "--dump-json",
        "--playlist-end",
        str(limit),
        "--no-warnings",
        *_youtube_pot_args(platform),
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

    args = build_yt_dlp_list_args(url, LIST_ITEM_CAP, platform)
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
                "view_count": entry.get("view_count"),
            }
        )

    if not items:
        raise DownloadFailedError("Couldn't find any videos for this profile.")

    truncated = len(items) >= LIST_ITEM_CAP
    return items[:LIST_ITEM_CAP], truncated


def build_gallery_dl_args(url: str, out_dir: Path) -> list[str]:
    return [
        paths.tool_path("gallery-dl"),
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
            "A required tool is missing. Re-run the launcher script "
            "(social-downloader.command / social-downloader.bat) to reinstall dependencies."
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


async def _file_has_audio(path: Path) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            paths.tool_path("ffprobe"),
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
    except Exception:
        # ffprobe missing or failed to run - fail open (assume audio is fine)
        # rather than blocking downloads on what is just a diagnostic check.
        return True
    return bool(stdout.strip())


async def _video_codec(path: Path) -> str | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            paths.tool_path("ffprobe"),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "csv=p=0",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
    except Exception:
        # ffprobe missing or failed to run - skip the compatibility check
        # rather than blocking downloads on what is just a diagnostic step.
        return None
    return stdout.decode(errors="replace").strip() or None


async def _transcode_to_h264(path: Path) -> Path:
    # VP9 (and other non-h264 codecs) inside an mp4 container fails to decode
    # on plenty of devices/players (notably iOS) even though the file itself
    # is valid - confirmed empirically against a real Instagram reel served
    # only as VP9 DASH streams. Re-encoding is the only real fix when no
    # h264 source stream exists at all (the format selector already prefers
    # h264 when available - see build_yt_dlp_args).
    transcoded_path = path.with_stem(f"{path.stem}_h264")
    args = [
        paths.tool_path("ffmpeg"),
        "-y",
        "-i",
        str(path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "copy",
        str(transcoded_path),
    ]
    returncode, _, stderr = await _run_subprocess(args, TIMEOUT_SECONDS)
    if returncode != 0:
        logger.warning(
            "H.264 transcode failed, keeping original codec: %s",
            stderr.decode(errors="replace")[-500:],
        )
        return path
    path.unlink(missing_ok=True)
    return transcoded_path


def _build_tiktok_audio_retry_args(url: str, out_dir: Path) -> list[str]:
    # TikTok's per-resolution formats (bytevc1_*/h264_*) sometimes report
    # acodec: aac in their metadata but actually serve a video-only stream in
    # practice (confirmed empirically - affects both the default "best" pick
    # and explicit height-based selection). TikTok's own "download" format
    # (the literal save-video endpoint) is reliably audio+video, so this is
    # the corrective retry when the first attempt turns out silent.
    return [
        paths.tool_path("yt-dlp"),
        "--no-playlist",
        "--playlist-items",
        "1",
        "-f",
        "download/best",
        "--force-overwrites",
        "-P",
        str(out_dir),
        "-o",
        "%(id)s.%(ext)s",
        *_ffmpeg_location_args(),
        "--print",
        "after_move:filepath",
        url,
    ]


async def _run_yt_dlp(
    url: str,
    out_dir: Path,
    selection: Selection | None = None,
    platform: Platform | None = None,
) -> list[Path]:
    args = build_yt_dlp_args(url, out_dir, selection, platform)
    returncode, stdout, stderr = await _run_subprocess(args, TIMEOUT_SECONDS)
    if returncode != 0:
        raise classify_stderr(stderr.decode(errors="replace"))

    lines = [line.strip() for line in stdout.decode(errors="replace").splitlines() if line.strip()]
    if not lines:
        raise classify_stderr(stderr.decode(errors="replace"))
    result_path = Path(lines[-1])

    is_audio_extraction = bool(selection) and selection.get("type") == "audio"
    if platform == "tiktok" and not is_audio_extraction and not await _file_has_audio(result_path):
        logger.warning("TikTok download has no audio, retrying with 'download' format: %s", url)
        retry_args = _build_tiktok_audio_retry_args(url, out_dir)
        retry_returncode, retry_stdout, _ = await _run_subprocess(retry_args, TIMEOUT_SECONDS)
        if retry_returncode == 0:
            retry_lines = [
                line.strip() for line in retry_stdout.decode(errors="replace").splitlines() if line.strip()
            ]
            if retry_lines:
                retry_path = Path(retry_lines[-1])
                if retry_path != result_path:
                    result_path.unlink(missing_ok=True)
                return [retry_path]
        # Retry failed for some reason - fall back to the original file rather
        # than erroring out; a silent video is still better than none at all.

    if not is_audio_extraction:
        codec = await _video_codec(result_path)
        if codec and codec != "h264":
            logger.info(
                "Transcoding non-h264 video (%s) to h264 for playback compatibility: %s",
                codec,
                url,
            )
            result_path = await _transcode_to_h264(result_path)

    return [result_path]


async def analyze_url(url: str, platform: Platform | None = None) -> AnalysisResult:
    args = build_yt_dlp_analyze_args(url, platform)
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

    if platform in ("tiktok", "youtube") or selection is not None:
        # gallery-dl has no concept of quality selection and always grabs
        # whichever media is first in the post (--range 1). Falling back to
        # it after an explicit video/audio selection would silently ignore
        # that selection and can return the wrong item entirely (e.g. a
        # carousel's cover image instead of the requested video) - a real
        # yt-dlp failure here must surface as an error, not swap content.
        return await _run_yt_dlp(url, out_dir, selection, platform)

    try:
        return await _run_yt_dlp(url, out_dir, selection, platform)
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
