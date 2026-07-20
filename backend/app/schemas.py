from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, field_validator, model_validator


class UrlRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def must_be_http(cls, v: str) -> str:
        parsed = urlsplit(v)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("invalid_url")
        return v


class DownloadSelection(BaseModel):
    type: Literal["video", "audio"]
    height: int | None = None
    bitrate: int | None = None

    @model_validator(mode="after")
    def check_required_field_for_type(self) -> "DownloadSelection":
        if self.type == "video" and self.height is None:
            raise ValueError("height is required when type is 'video'")
        if self.type == "audio" and self.bitrate is None:
            raise ValueError("bitrate is required when type is 'audio'")
        return self


class DownloadRequest(UrlRequest):
    selection: DownloadSelection | None = None


class AnalyzeRequest(UrlRequest):
    pass


class VideoQuality(BaseModel):
    height: int
    label: str
    ext: str


class AudioQuality(BaseModel):
    bitrate: int
    label: str


class AnalyzeResponse(BaseModel):
    status: str = "success"
    platform: str
    title: str | None = None
    thumbnail: str | None = None
    supports_quality_selection: bool
    video_qualities: list[VideoQuality] = []
    audio_qualities: list[AudioQuality] = []


class DownloadResponse(BaseModel):
    status: str = "success"
    platform: str
    filenames: list[str]
    preview_url: str | None = None


class ErrorResponse(BaseModel):
    status: str = "error"
    error_code: str
    message: str
