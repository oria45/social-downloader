import mimetypes
import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.config import MP3_BITRATE_CHOICES
from app.downloader import (
    analyze_url,
    detect_platform,
    is_profile_url,
    list_profile_items,
    run_batch_download,
    run_download,
)
from app.errors import NotAProfileUrlError, UnsupportedPlatformError
from app.limiter import limiter
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    AudioQuality,
    BatchDownloadRequest,
    DownloadRequest,
    ListRequest,
    ListResponse,
    ProfileItem,
    VideoQuality,
)

router = APIRouter()


def _cleanup_files(*paths: Path) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def _zip_files(files: list[Path]) -> Path:
    fd, zip_path_str = tempfile.mkstemp(suffix=".zip")
    zip_path = Path(zip_path_str)
    with zipfile.ZipFile(zip_path, "w") as archive:
        for f in files:
            archive.write(f, arcname=f.name)
    os.close(fd)
    return zip_path


def _build_file_response(files: list[Path], platform: str) -> FileResponse:
    if len(files) == 1:
        target = files[0]
        media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return FileResponse(
            target,
            filename=target.name,
            media_type=media_type,
            headers={"X-Platform": platform},
            background=BackgroundTask(_cleanup_files, target),
        )

    zip_path = _zip_files(files)
    return FileResponse(
        zip_path,
        filename=f"{platform}_{files[0].stem}.zip",
        media_type="application/zip",
        headers={"X-Platform": platform},
        background=BackgroundTask(_cleanup_files, zip_path, *files),
    )


@router.post("/download")
@limiter.limit("5/minute")
async def download(request: Request, payload: DownloadRequest) -> FileResponse:
    platform = detect_platform(payload.url)
    if platform is None:
        raise UnsupportedPlatformError(
            "Only TikTok, Instagram, Facebook, and YouTube links are supported."
        )

    selection = payload.selection.model_dump(exclude_none=True) if payload.selection else None
    files = await run_download(payload.url, platform, selection)
    return _build_file_response(files, platform)


@router.post("/analyze", response_model=AnalyzeResponse)
@limiter.limit("20/minute")
async def analyze(request: Request, payload: AnalyzeRequest) -> AnalyzeResponse:
    platform = detect_platform(payload.url)
    if platform is None:
        raise UnsupportedPlatformError(
            "Only TikTok, Instagram, Facebook, and YouTube links are supported."
        )

    result = await analyze_url(payload.url, platform)
    if not result.get("supports_quality_selection"):
        return AnalyzeResponse(platform=platform, supports_quality_selection=False)

    video_qualities = [
        VideoQuality(height=height, label=f"{height}p", ext="mp4")
        for height in result.get("video_heights", [])
    ]
    best_audio_abr = result.get("best_audio_abr", 0)
    audio_qualities = [
        AudioQuality(bitrate=bitrate, label=f"MP3 - {bitrate} kbps")
        for bitrate in MP3_BITRATE_CHOICES
        if best_audio_abr == 0 or bitrate <= best_audio_abr * 1.5
    ] or [AudioQuality(bitrate=MP3_BITRATE_CHOICES[0], label=f"MP3 - {MP3_BITRATE_CHOICES[0]} kbps")]

    return AnalyzeResponse(
        platform=platform,
        title=result.get("title"),
        thumbnail=result.get("thumbnail"),
        supports_quality_selection=True,
        video_qualities=video_qualities,
        audio_qualities=audio_qualities,
    )


@router.post("/list", response_model=ListResponse)
@limiter.limit("10/minute")
async def list_profile(request: Request, payload: ListRequest) -> ListResponse:
    platform = detect_platform(payload.url)
    if platform is None:
        raise UnsupportedPlatformError(
            "Only TikTok, Instagram, Facebook, and YouTube links are supported."
        )
    if not is_profile_url(payload.url, platform):
        raise NotAProfileUrlError(
            "That doesn't look like a profile/channel link. Paste a specific video's link instead."
        )

    items, truncated = await list_profile_items(payload.url, platform)
    return ListResponse(
        platform=platform,
        items=[ProfileItem(**item) for item in items],
        truncated=truncated,
    )


@router.post("/download-batch")
@limiter.limit("3/minute")
async def download_batch(request: Request, payload: BatchDownloadRequest) -> FileResponse:
    platform = detect_platform(payload.urls[0])
    if platform is None or any(detect_platform(u) != platform for u in payload.urls):
        raise UnsupportedPlatformError(
            "Only TikTok, Instagram, Facebook, and YouTube links are supported, and all "
            "selected items must be from the same platform."
        )

    files = await run_batch_download(payload.urls, platform)
    return _build_file_response(files, platform)
