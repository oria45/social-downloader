import re


class DownloadError(Exception):
    error_code = "download_failed"
    http_status = 502

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class InvalidUrlError(DownloadError):
    error_code = "invalid_url"
    http_status = 422


class UnsupportedPlatformError(DownloadError):
    error_code = "unsupported_platform"
    http_status = 422


class ContentUnavailableError(DownloadError):
    error_code = "content_unavailable"
    http_status = 502


class RateLimitedError(DownloadError):
    error_code = "rate_limited"
    http_status = 429


class ToolNotInstalledError(DownloadError):
    error_code = "tool_not_installed"
    http_status = 500


class DownloadTimeoutError(DownloadError):
    error_code = "download_timeout"
    http_status = 504


class DownloadFailedError(DownloadError):
    error_code = "download_failed"
    http_status = 502


_PRIVATE_PATTERNS = re.compile(
    r"private|login required|requires? auth|not available|has been removed|"
    r"does not exist|no longer available|restricted",
    re.IGNORECASE,
)
_RATE_LIMIT_PATTERNS = re.compile(r"429|rate.?limit|too many requests", re.IGNORECASE)


def classify_stderr(stderr_text: str) -> DownloadError:
    if _RATE_LIMIT_PATTERNS.search(stderr_text):
        return RateLimitedError(
            "The platform is rate-limiting requests. Wait a few minutes and try again."
        )
    if _PRIVATE_PATTERNS.search(stderr_text):
        return ContentUnavailableError(
            "This content is private, deleted, or requires login — not supported in this tool yet."
        )
    return DownloadFailedError(
        "Couldn't download this — the link may be unsupported or the tool needs updating."
    )
