import asyncio
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from app.api import router as api_router
from app.config import FILE_MAX_AGE_MINUTES, FRONTEND_DIST, PLATFORM_DIRS
from app.errors import DownloadError
from app.limiter import limiter
from app.schemas import ErrorResponse


async def _cleanup_old_downloads() -> None:
    while True:
        cutoff = time.time() - FILE_MAX_AGE_MINUTES * 60
        for platform_dir in PLATFORM_DIRS.values():
            for f in platform_dir.iterdir():
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink(missing_ok=True)
        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(_cleanup_old_downloads())
    yield
    cleanup_task.cancel()


app = FastAPI(title="social-downloader", lifespan=lifespan)
app.state.limiter = limiter

allowed_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    expose_headers=["Content-Disposition", "X-Platform"],
)

app.include_router(api_router, prefix="/api")


@app.exception_handler(DownloadError)
async def download_error_handler(request: Request, exc: DownloadError) -> JSONResponse:
    body = ErrorResponse(error_code=exc.error_code, message=exc.message)
    return JSONResponse(status_code=exc.http_status, content=body.model_dump())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    body = ErrorResponse(
        error_code="invalid_url", message="That doesn't look like a valid link."
    )
    return JSONResponse(status_code=422, content=body.model_dump())


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    body = ErrorResponse(
        error_code="rate_limited", message="Too many requests. Please slow down and try again."
    )
    return JSONResponse(status_code=429, content=body.model_dump())


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
