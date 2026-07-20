from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import BATCH_MAX_ITEMS


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


class BatchDownloadRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=BATCH_MAX_ITEMS)

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, v: list[str]) -> list[str]:
        for url in v:
            parsed = urlsplit(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise ValueError("invalid_url")
        return v


class AnalyzeRequest(UrlRequest):
    pass


class ListRequest(UrlRequest):
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


class ProfileItem(BaseModel):
    id: str
    title: str | None
    thumbnail_url: str | None
    url: str


class ListResponse(BaseModel):
    status: str = "success"
    platform: str
    items: list[ProfileItem]
    truncated: bool


class ErrorResponse(BaseModel):
    status: str = "error"
    error_code: str
    message: str
