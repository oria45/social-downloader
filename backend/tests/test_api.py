from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api as api_module
from app.errors import ContentUnavailableError, DownloadTimeoutError, ToolNotInstalledError
from app.main import app

client = TestClient(app)


def test_download_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_download(url: str, platform: str, selection=None) -> list[Path]:
        return [Path("/tmp/downloads/tiktok/123.mp4")]

    monkeypatch.setattr(api_module, "run_download", fake_run_download)

    response = client.post("/api/download", json={"url": "https://www.tiktok.com/@u/video/123"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["platform"] == "tiktok"
    assert body["filenames"] == ["123.mp4"]
    assert body["preview_url"] == "/media/tiktok/123.mp4"


def test_download_success_youtube(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_download(url: str, platform: str, selection=None) -> list[Path]:
        return [Path("/tmp/downloads/youtube/dQw4w9WgXcQ.mp4")]

    monkeypatch.setattr(api_module, "run_download", fake_run_download)

    response = client.post(
        "/api/download", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "youtube"
    assert body["filenames"] == ["dQw4w9WgXcQ.mp4"]
    assert body["preview_url"] == "/media/youtube/dQw4w9WgXcQ.mp4"


def test_download_forwards_selection_to_run_download(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    async def fake_run_download(url: str, platform: str, selection=None) -> list[Path]:
        captured["selection"] = selection
        return [Path("/tmp/downloads/youtube/abc.mp3")]

    monkeypatch.setattr(api_module, "run_download", fake_run_download)

    response = client.post(
        "/api/download",
        json={
            "url": "https://www.youtube.com/watch?v=abc",
            "selection": {"type": "audio", "bitrate": 128},
        },
    )

    assert response.status_code == 200
    assert captured["selection"] == {"type": "audio", "bitrate": 128}


def test_download_selection_video_without_height_is_rejected() -> None:
    response = client.post(
        "/api/download",
        json={"url": "https://www.youtube.com/watch?v=abc", "selection": {"type": "video"}},
    )

    assert response.status_code == 422


def test_download_invalid_url() -> None:
    response = client.post("/api/download", json={"url": "not a url"})

    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "error"
    assert body["error_code"] == "invalid_url"


def test_download_unsupported_platform() -> None:
    response = client.post("/api/download", json={"url": "https://example.com/video"})

    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "error"
    assert body["error_code"] == "unsupported_platform"


def test_download_content_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_download(url: str, platform: str, selection=None):
        raise ContentUnavailableError("This content is private, deleted, or requires login.")

    monkeypatch.setattr(api_module, "run_download", fake_run_download)

    response = client.post("/api/download", json={"url": "https://instagram.com/p/private"})

    assert response.status_code == 502
    body = response.json()
    assert body["error_code"] == "content_unavailable"


def test_download_tool_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_download(url: str, platform: str, selection=None):
        raise ToolNotInstalledError("A required tool is missing.")

    monkeypatch.setattr(api_module, "run_download", fake_run_download)

    response = client.post("/api/download", json={"url": "https://www.tiktok.com/@u/video/1"})

    assert response.status_code == 500
    body = response.json()
    assert body["error_code"] == "tool_not_installed"


def test_download_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_download(url: str, platform: str, selection=None):
        raise DownloadTimeoutError("Download timed out.")

    monkeypatch.setattr(api_module, "run_download", fake_run_download)

    response = client.post("/api/download", json={"url": "https://fb.watch/xxx"})

    assert response.status_code == 504
    body = response.json()
    assert body["error_code"] == "download_timeout"


def test_analyze_returns_qualities_for_yt_dlp_backed_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_analyze_url(url: str):
        return {
            "supports_quality_selection": True,
            "title": "Me at the zoo",
            "thumbnail": "https://i.ytimg.com/vi/x/hqdefault.jpg",
            "video_heights": [720, 480, 360],
            "best_audio_abr": 129.796,
        }

    monkeypatch.setattr(api_module, "analyze_url", fake_analyze_url)

    response = client.post(
        "/api/analyze", json={"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["supports_quality_selection"] is True
    assert body["title"] == "Me at the zoo"
    assert [q["height"] for q in body["video_qualities"]] == [720, 480, 360]
    assert body["video_qualities"][0]["label"] == "720p"
    # best_audio_abr ~130 -> 128 and 192 qualify (<= 130*1.5), 320 does not
    assert [q["bitrate"] for q in body["audio_qualities"]] == [128, 192]


def test_analyze_returns_no_quality_selection_for_gallery_dl_backed_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_analyze_url(url: str):
        return {"supports_quality_selection": False}

    monkeypatch.setattr(api_module, "analyze_url", fake_analyze_url)

    response = client.post("/api/analyze", json={"url": "https://instagram.com/p/ABC"})

    assert response.status_code == 200
    body = response.json()
    assert body["supports_quality_selection"] is False
    assert body["video_qualities"] == []
    assert body["audio_qualities"] == []


def test_analyze_unsupported_platform() -> None:
    response = client.post("/api/analyze", json={"url": "https://example.com/video"})

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "unsupported_platform"
