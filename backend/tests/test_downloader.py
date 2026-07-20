import asyncio
import json

import pytest

from app.downloader import (
    analyze_url,
    build_gallery_dl_args,
    build_yt_dlp_args,
    build_yt_dlp_list_args,
    detect_platform,
    is_profile_url,
    list_profile_items,
    run_batch_download,
    run_download,
)
from app.errors import ContentUnavailableError, DownloadFailedError, ToolNotInstalledError


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://vm.tiktok.com/xxx", "tiktok"),
        ("https://www.tiktok.com/@user/video/123", "tiktok"),
        ("https://m.tiktok.com/v/123", "tiktok"),
        ("https://instagram.com/reel/ABC", "instagram"),
        ("https://www.instagram.com/p/ABC", "instagram"),
        ("https://fb.watch/xxx", "facebook"),
        ("https://m.facebook.com/watch/?v=123", "facebook"),
        ("https://www.facebook.com/user/videos/123", "facebook"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
        ("https://music.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
        ("https://www.youtube.com/@somechannel", "youtube"),
    ],
)
def test_detect_platform_positive(url: str, expected: str) -> None:
    assert detect_platform(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/video",
        "https://notfacebook.com.evil.example/watch",
        "https://notyoutube.com.evil.example/watch",
        "not a url",
        "",
    ],
)
def test_detect_platform_negative(url: str) -> None:
    assert detect_platform(url) is None


def test_yt_dlp_args_are_a_list_with_url_as_own_element(tmp_path) -> None:
    args = build_yt_dlp_args("https://tiktok.com/@u/video/1", tmp_path)
    assert isinstance(args, list)
    assert all(isinstance(a, str) for a in args)
    assert args[-1] == "https://tiktok.com/@u/video/1"
    assert "yt-dlp" == args[0]


def test_yt_dlp_args_cap_downloads_to_one(tmp_path) -> None:
    # Regression guard: a profile/channel URL must not download the creator's
    # entire history. --no-playlist alone does not stop that (confirmed live: it
    # still paginated through 49+ pages of a real profile). --max-downloads 1 only
    # caps successful downloads, not enumeration, so a channel is still fully listed
    # before stopping. --playlist-items 1 stops enumeration itself and is verified
    # (against a real TikTok profile) to finish in seconds instead of minutes.
    args = build_yt_dlp_args("https://www.tiktok.com/@someuser", tmp_path)
    assert "--playlist-items" in args
    assert args[args.index("--playlist-items") + 1] == "1"


def test_gallery_dl_args_are_a_list_with_url_as_own_element(tmp_path) -> None:
    args = build_gallery_dl_args("https://instagram.com/p/ABC", tmp_path)
    assert isinstance(args, list)
    assert all(isinstance(a, str) for a in args)
    assert args[-1] == "https://instagram.com/p/ABC"
    assert "gallery-dl" == args[0]


def test_gallery_dl_args_cap_range_to_one(tmp_path) -> None:
    # Same regression guard as yt-dlp, for profile/hashtag pages hit via gallery-dl.
    args = build_gallery_dl_args("https://instagram.com/someuser", tmp_path)
    assert "--range" in args
    assert args[args.index("--range") + 1] == "1"


def test_gallery_dl_args_use_exact_directory_flag(tmp_path) -> None:
    # -d (--dest) still nests output under out_dir/<site>/<user>/..., which breaks
    # the flat before/after directory diff used to detect downloaded files.
    # -D (--directory) is the exact, non-nesting flag and must be used instead.
    args = build_gallery_dl_args("https://instagram.com/p/ABC", tmp_path)
    assert "-D" in args
    assert "-d" not in args


def test_youtube_routes_to_yt_dlp_only_no_gallery_dl_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # YouTube is yt-dlp's home turf; unlike Instagram/Facebook it must never fall
    # back to gallery-dl on failure (that fallback exists only for image/carousel
    # posts, which YouTube doesn't have).
    from app import downloader

    monkeypatch.setitem(downloader.PLATFORM_DIRS, "youtube", tmp_path)

    async def failing_yt_dlp(url: str, out_dir, selection=None):
        raise RuntimeError("yt-dlp failed")

    async def unexpected_gallery_dl(url: str, out_dir):
        raise AssertionError("gallery-dl should never be called for youtube")

    monkeypatch.setattr(downloader, "_run_yt_dlp", failing_yt_dlp)
    monkeypatch.setattr(downloader, "_run_gallery_dl", unexpected_gallery_dl)

    with pytest.raises(RuntimeError):
        asyncio.run(run_download("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"))


def test_yt_dlp_args_with_no_selection_have_no_format_flags(tmp_path) -> None:
    args = build_yt_dlp_args("https://tiktok.com/@u/video/1", tmp_path, selection=None)
    assert "-f" not in args
    assert "-x" not in args


def test_yt_dlp_args_with_video_selection(tmp_path) -> None:
    args = build_yt_dlp_args(
        "https://www.youtube.com/watch?v=abc", tmp_path, selection={"type": "video", "height": 720}
    )
    assert "-f" in args
    assert args[args.index("-f") + 1] == "bestvideo[height<=720]+bestaudio/best[height<=720]"
    assert "--merge-output-format" in args
    assert args[args.index("--merge-output-format") + 1] == "mp4"
    assert "-x" not in args


def test_yt_dlp_args_with_audio_selection(tmp_path) -> None:
    args = build_yt_dlp_args(
        "https://www.youtube.com/watch?v=abc", tmp_path, selection={"type": "audio", "bitrate": 128}
    )
    assert "-x" in args
    assert "--audio-format" in args
    assert args[args.index("--audio-format") + 1] == "mp3"
    assert "--audio-quality" in args
    assert args[args.index("--audio-quality") + 1] == "128K"
    assert "-f" not in args


def _fake_run_subprocess(returncode: int, stdout: bytes, stderr: bytes):
    async def _run(args, timeout):
        return returncode, stdout, stderr

    return _run


def test_analyze_url_parses_real_shaped_format_list(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import downloader

    info = {
        "title": "Me at the zoo",
        "thumbnail": "https://i.ytimg.com/vi/jNQXAC9IVRw/hqdefault.jpg",
        "formats": [
            {"format_id": "139", "ext": "m4a", "height": None, "vcodec": "none", "acodec": "mp4a.40.5", "abr": 49.14},
            {"format_id": "140", "ext": "m4a", "height": None, "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129.796},
            {"format_id": "160", "ext": "mp4", "height": 144, "vcodec": "avc1.4d400b", "acodec": "none", "abr": 0},
            {"format_id": "134", "ext": "mp4", "height": 240, "vcodec": "avc1.4d400c", "acodec": "none", "abr": 0},
            {"format_id": "18", "ext": "mp4", "height": 240, "vcodec": "avc1.42001E", "acodec": "mp4a.40.2", "abr": None},
        ],
    }
    monkeypatch.setattr(
        downloader, "_run_subprocess", _fake_run_subprocess(0, json.dumps(info).encode(), b"")
    )

    result = asyncio.run(analyze_url("https://www.youtube.com/watch?v=jNQXAC9IVRw"))

    assert result["supports_quality_selection"] is True
    assert result["title"] == "Me at the zoo"
    assert result["video_heights"] == [240, 144]
    assert result["best_audio_abr"] == pytest.approx(129.796)


def test_analyze_url_returns_no_quality_support_on_generic_extraction_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A generic yt-dlp failure (e.g. an Instagram photo post it can't extract at
    # all) must not be treated as an error - gallery-dl handles that case instead.
    from app import downloader

    monkeypatch.setattr(
        downloader,
        "_run_subprocess",
        _fake_run_subprocess(1, b"", b"ERROR: Unsupported URL"),
    )

    result = asyncio.run(analyze_url("https://instagram.com/p/ABC"))

    assert result == {"supports_quality_selection": False}


def test_analyze_url_raises_on_real_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # A private/deleted video is a genuine error and must still surface as one.
    from app import downloader

    monkeypatch.setattr(
        downloader,
        "_run_subprocess",
        _fake_run_subprocess(1, b"", b"ERROR: Private video. Sign in if you've been granted access."),
    )

    with pytest.raises(ContentUnavailableError):
        asyncio.run(analyze_url("https://www.youtube.com/watch?v=private123"))


@pytest.mark.parametrize(
    "url,platform,expected",
    [
        ("https://www.tiktok.com/@tiktok", "tiktok", True),
        ("https://www.tiktok.com/@tiktok/video/123", "tiktok", False),
        ("https://www.youtube.com/@YouTube", "youtube", True),
        ("https://www.youtube.com/@YouTube/videos", "youtube", True),
        ("https://www.youtube.com/@YouTube/shorts", "youtube", True),
        ("https://www.youtube.com/channel/UC123", "youtube", True),
        ("https://www.youtube.com/c/somechannel", "youtube", True),
        ("https://www.youtube.com/user/someuser", "youtube", True),
        ("https://www.youtube.com/watch?v=abc", "youtube", False),
        ("https://www.youtube.com/shorts/abc", "youtube", False),
        ("https://www.instagram.com/instagram/", "instagram", False),
        ("https://www.facebook.com/someuser", "facebook", False),
    ],
)
def test_is_profile_url(url: str, platform: str, expected: bool) -> None:
    assert is_profile_url(url, platform) == expected


def test_build_yt_dlp_list_args_caps_and_uses_flat_playlist(tmp_path) -> None:
    args = build_yt_dlp_list_args("https://www.tiktok.com/@user", 24)
    assert "--flat-playlist" in args
    assert "--dump-json" in args
    assert "--playlist-end" in args
    assert args[args.index("--playlist-end") + 1] == "24"
    assert args[-1] == "https://www.tiktok.com/@user"


def test_list_profile_items_parses_ndjson_and_flags_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import downloader

    entries = [
        {
            "id": str(i),
            "title": f"video {i}",
            "url": f"https://www.tiktok.com/@user/video/{i}",
            "thumbnails": [{"url": f"https://thumb/{i}.jpg", "preference": -1}],
        }
        for i in range(downloader.LIST_ITEM_CAP)
    ]
    stdout = "\n".join(json.dumps(e) for e in entries).encode()
    monkeypatch.setattr(downloader, "_run_subprocess", _fake_run_subprocess(0, stdout, b""))

    items, truncated = asyncio.run(list_profile_items("https://www.tiktok.com/@user", "tiktok"))

    assert len(items) == downloader.LIST_ITEM_CAP
    assert truncated is True
    assert items[0]["id"] == "0"
    assert items[0]["url"] == "https://www.tiktok.com/@user/video/0"
    assert items[0]["thumbnail_url"] == "https://thumb/0.jpg"


def test_list_profile_items_not_truncated_when_fewer_than_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import downloader

    entries = [
        {"id": "1", "title": "only one", "url": "https://www.tiktok.com/@user/video/1"},
    ]
    stdout = json.dumps(entries[0]).encode()
    monkeypatch.setattr(downloader, "_run_subprocess", _fake_run_subprocess(0, stdout, b""))

    items, truncated = asyncio.run(list_profile_items("https://www.tiktok.com/@user", "tiktok"))

    assert len(items) == 1
    assert truncated is False


def test_list_profile_items_raises_when_nothing_found(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import downloader

    monkeypatch.setattr(downloader, "_run_subprocess", _fake_run_subprocess(0, b"", b""))

    with pytest.raises(DownloadFailedError):
        asyncio.run(list_profile_items("https://www.tiktok.com/@user", "tiktok"))


def test_youtube_listing_url_appends_videos_tab() -> None:
    from app.downloader import _youtube_listing_url

    assert _youtube_listing_url("https://www.youtube.com/@YouTube") == (
        "https://www.youtube.com/@YouTube/videos"
    )
    assert _youtube_listing_url("https://www.youtube.com/@YouTube/videos") == (
        "https://www.youtube.com/@YouTube/videos"
    )
    assert _youtube_listing_url("https://www.youtube.com/@YouTube/shorts") == (
        "https://www.youtube.com/@YouTube/shorts"
    )


def test_run_batch_download_partial_success(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from app import downloader

    good_file = tmp_path / "good.mp4"
    good_file.write_bytes(b"data")

    async def fake_run_download(url: str, platform: str, selection=None):
        if "bad" in url:
            raise RuntimeError("boom")
        return [good_file]

    monkeypatch.setattr(downloader, "run_download", fake_run_download)

    results = asyncio.run(
        run_batch_download(
            ["https://tiktok.com/@u/video/good1", "https://tiktok.com/@u/video/bad1"], "tiktok"
        )
    )

    assert results == [good_file]


def test_run_batch_download_raises_when_all_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import downloader

    async def failing_run_download(url: str, platform: str, selection=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(downloader, "run_download", failing_run_download)

    with pytest.raises(DownloadFailedError):
        asyncio.run(run_batch_download(["https://tiktok.com/@u/video/1"], "tiktok"))


def test_run_batch_download_propagates_tool_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import downloader

    async def missing_tool(url: str, platform: str, selection=None):
        raise ToolNotInstalledError("missing")

    monkeypatch.setattr(downloader, "run_download", missing_tool)

    with pytest.raises(ToolNotInstalledError):
        asyncio.run(run_batch_download(["https://tiktok.com/@u/video/1"], "tiktok"))
