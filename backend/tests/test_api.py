from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api as api_module
from app.errors import ContentUnavailableError, DownloadTimeoutError, ToolNotInstalledError
from app.main import app

client = TestClient(app)


def test_download_success_streams_file_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    downloaded = tmp_path / "123.mp4"
    downloaded.write_bytes(b"fake video bytes")

    async def fake_run_download(url: str, platform: str, selection=None) -> list[Path]:
        return [downloaded]

    monkeypatch.setattr(api_module, "run_download", fake_run_download)

    response = client.post("/api/download", json={"url": "https://www.tiktok.com/@u/video/123"})

    assert response.status_code == 200
    assert response.content == b"fake video bytes"
    assert response.headers["x-platform"] == "tiktok"
    assert 'filename="123.mp4"' in response.headers["content-disposition"]
    assert response.headers["content-type"] == "video/mp4"
    # the source file must be deleted once it's been streamed to the client -
    # nothing should persist server-side after a successful download
    assert not downloaded.exists()


def test_download_success_youtube_audio(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    downloaded = tmp_path / "dQw4w9WgXcQ.mp3"
    downloaded.write_bytes(b"fake audio bytes")

    async def fake_run_download(url: str, platform: str, selection=None) -> list[Path]:
        return [downloaded]

    monkeypatch.setattr(api_module, "run_download", fake_run_download)

    response = client.post(
        "/api/download", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    )

    assert response.status_code == 200
    assert response.headers["x-platform"] == "youtube"
    assert 'filename="dQw4w9WgXcQ.mp3"' in response.headers["content-disposition"]
    assert not downloaded.exists()


def test_download_multiple_files_are_zipped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    file_a = tmp_path / "1.jpg"
    file_b = tmp_path / "2.jpg"
    file_a.write_bytes(b"image a")
    file_b.write_bytes(b"image b")

    async def fake_run_download(url: str, platform: str, selection=None) -> list[Path]:
        return [file_a, file_b]

    monkeypatch.setattr(api_module, "run_download", fake_run_download)

    response = client.post("/api/download", json={"url": "https://instagram.com/p/ABC"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["x-platform"] == "instagram"
    assert not file_a.exists()
    assert not file_b.exists()


def test_download_forwards_selection_to_run_download(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = {}
    downloaded = tmp_path / "abc.mp3"
    downloaded.write_bytes(b"fake audio bytes")

    async def fake_run_download(url: str, platform: str, selection=None) -> list[Path]:
        captured["selection"] = selection
        return [downloaded]

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


def test_list_profile_returns_items(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list_profile_items(url: str, platform: str):
        return (
            [
                {
                    "id": "1",
                    "title": "video one",
                    "thumbnail_url": "https://thumb/1.jpg",
                    "url": "https://www.tiktok.com/@user/video/1",
                }
            ],
            False,
        )

    monkeypatch.setattr(api_module, "list_profile_items", fake_list_profile_items)

    response = client.post("/api/list", json={"url": "https://www.tiktok.com/@user"})

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "tiktok"
    assert body["truncated"] is False
    assert body["items"] == [
        {
            "id": "1",
            "title": "video one",
            "thumbnail_url": "https://thumb/1.jpg",
            "url": "https://www.tiktok.com/@user/video/1",
        }
    ]


def test_list_profile_rejects_non_profile_url() -> None:
    response = client.post(
        "/api/list", json={"url": "https://www.tiktok.com/@user/video/123"}
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "not_a_profile_url"


def test_list_profile_unsupported_platform() -> None:
    response = client.post("/api/list", json={"url": "https://example.com/someone"})

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "unsupported_platform"


def test_download_batch_streams_zip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    file_a = tmp_path / "1.mp4"
    file_b = tmp_path / "2.mp4"
    file_a.write_bytes(b"video a")
    file_b.write_bytes(b"video b")

    async def fake_run_batch_download(urls: list[str], platform: str) -> list[Path]:
        return [file_a, file_b]

    monkeypatch.setattr(api_module, "run_batch_download", fake_run_batch_download)

    response = client.post(
        "/api/download-batch",
        json={
            "urls": [
                "https://www.tiktok.com/@user/video/1",
                "https://www.tiktok.com/@user/video/2",
            ]
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["x-platform"] == "tiktok"
    assert not file_a.exists()
    assert not file_b.exists()


def test_download_batch_rejects_more_than_max_items() -> None:
    urls = [f"https://www.tiktok.com/@user/video/{i}" for i in range(9)]

    response = client.post("/api/download-batch", json={"urls": urls})

    assert response.status_code == 422


def test_download_batch_rejects_empty_list() -> None:
    response = client.post("/api/download-batch", json={"urls": []})

    assert response.status_code == 422


def test_download_batch_rejects_mixed_platforms() -> None:
    response = client.post(
        "/api/download-batch",
        json={
            "urls": [
                "https://www.tiktok.com/@user/video/1",
                "https://www.youtube.com/watch?v=abc",
            ]
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "unsupported_platform"
