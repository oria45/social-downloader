from fastapi import APIRouter, Request

from app.config import MP3_BITRATE_CHOICES
from app.downloader import analyze_url, detect_platform, run_download
from app.errors import UnsupportedPlatformError
from app.limiter import limiter
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    AudioQuality,
    DownloadRequest,
    DownloadResponse,
    VideoQuality,
)

router = APIRouter()


@router.post("/download", response_model=DownloadResponse)
@limiter.limit("5/minute")
async def download(request: Request, payload: DownloadRequest) -> DownloadResponse:
    platform = detect_platform(payload.url)
    if platform is None:
        raise UnsupportedPlatformError(
            "Only TikTok, Instagram, Facebook, and YouTube links are supported."
        )

    selection = payload.selection.model_dump(exclude_none=True) if payload.selection else None
    files = await run_download(payload.url, platform, selection)
    filenames = [f.name for f in files]
    preview_url = f"/media/{platform}/{filenames[0]}" if filenames else None

    return DownloadResponse(
        platform=platform,
        filenames=filenames,
        preview_url=preview_url,
    )


@router.post("/analyze", response_model=AnalyzeResponse)
@limiter.limit("20/minute")
async def analyze(request: Request, payload: AnalyzeRequest) -> AnalyzeResponse:
    platform = detect_platform(payload.url)
    if platform is None:
        raise UnsupportedPlatformError(
            "Only TikTok, Instagram, Facebook, and YouTube links are supported."
        )

    result = await analyze_url(payload.url)
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
