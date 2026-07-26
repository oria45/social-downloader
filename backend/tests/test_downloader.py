import asyncio
import json

import pytest

from app.downloader import (
    analyze_url,
    build_gallery_dl_args,
    build_yt_dlp_analyze_args,
    build_yt_dlp_args,
    build_yt_dlp_list_args,
    detect_platform,
    is_profile_url,
    list_profile_items,
    run_batch_download,
    run_download,
)
from app.errors import (
    ContentUnavailableError,
    DownloadFailedError,
    RateLimitedError,
    ToolNotInstalledError,
    classify_stderr,
)


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
        ("https://twitter.com/user/status/123", "twitter"),
        ("https://x.com/user/status/123", "twitter"),
        ("https://mobile.twitter.com/user/status/123", "twitter"),
        ("https://mobile.x.com/user/status/123", "twitter"),
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
        "https://notx.com.evil.example/status/1",
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

    async def failing_yt_dlp(url: str, out_dir, selection=None, platform=None):
        raise RuntimeError("yt-dlp failed")

    async def unexpected_gallery_dl(url: str, out_dir):
        raise AssertionError("gallery-dl should never be called for youtube")

    monkeypatch.setattr(downloader, "_run_yt_dlp", failing_yt_dlp)
    monkeypatch.setattr(downloader, "_run_gallery_dl", unexpected_gallery_dl)

    with pytest.raises(RuntimeError):
        asyncio.run(run_download("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"))


def test_instagram_with_selection_does_not_fall_back_to_gallery_dl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # gallery-dl ignores quality selection entirely and just grabs whatever is
    # first in the post (--range 1) - for a carousel that can be a photo, not
    # the requested video. A transient yt-dlp failure here must surface as a
    # real error instead of silently swapping in unrelated content.
    from app import downloader

    async def failing_yt_dlp(url: str, out_dir, selection=None, platform=None):
        raise RuntimeError("yt-dlp failed")

    async def unexpected_gallery_dl(url: str, out_dir):
        raise AssertionError("gallery-dl should never be called when a selection was requested")

    monkeypatch.setattr(downloader, "_run_yt_dlp", failing_yt_dlp)
    monkeypatch.setattr(downloader, "_run_gallery_dl", unexpected_gallery_dl)

    with pytest.raises(RuntimeError):
        asyncio.run(
            run_download(
                "https://www.instagram.com/reel/ABC",
                "instagram",
                selection={"type": "video", "height": 720},
            )
        )


def test_instagram_without_selection_still_falls_back_to_gallery_dl(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # No selection means the caller just wants "whatever this post has" (e.g.
    # an image-only post yt-dlp can't extract at all) - gallery-dl fallback
    # is still correct and expected in that case.
    from app import downloader

    fallback_file = tmp_path / "ABC.jpg"
    fallback_file.write_bytes(b"data")

    async def failing_yt_dlp(url: str, out_dir, selection=None, platform=None):
        raise RuntimeError("yt-dlp failed")

    async def fake_gallery_dl(url: str, out_dir):
        return [fallback_file]

    monkeypatch.setattr(downloader, "_run_yt_dlp", failing_yt_dlp)
    monkeypatch.setattr(downloader, "_run_gallery_dl", fake_gallery_dl)

    result = asyncio.run(run_download("https://www.instagram.com/p/ABC", "instagram"))

    assert result == [fallback_file]


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
        ("https://twitter.com/someuser", "twitter", False),
    ],
)
def test_is_profile_url(url: str, platform: str, expected: bool) -> None:
    assert is_profile_url(url, platform) == expected


def test_youtube_pot_args_included_when_server_home_exists_for_download(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from app import downloader

    monkeypatch.setattr(downloader, "YOUTUBE_POT_SERVER_HOME", str(tmp_path))
    args = build_yt_dlp_args("https://www.youtube.com/watch?v=abc", tmp_path, platform="youtube")

    assert f"youtubepot-bgutilscript:server_home={tmp_path}" in args
    assert "youtube:player_client=android,web" in args


def test_youtube_pot_args_included_for_analyze_and_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from app import downloader

    monkeypatch.setattr(downloader, "YOUTUBE_POT_SERVER_HOME", str(tmp_path))

    analyze_args = build_yt_dlp_analyze_args("https://www.youtube.com/watch?v=abc", "youtube")
    list_args = build_yt_dlp_list_args("https://www.youtube.com/@chan/videos", 24, "youtube")

    assert "--extractor-args" in analyze_args
    assert "--extractor-args" in list_args


def test_youtube_pot_args_absent_for_non_youtube_platform(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from app import downloader

    monkeypatch.setattr(downloader, "YOUTUBE_POT_SERVER_HOME", str(tmp_path))
    args = build_yt_dlp_args("https://www.tiktok.com/@u/video/1", tmp_path, platform="tiktok")

    assert "--extractor-args" not in args


def test_youtube_pot_args_absent_when_server_home_missing(tmp_path) -> None:
    # Local dev without the pot-provider cloned in: must not error, just skip
    # the pot server_home extractor-args (the player-client one still applies).
    from app import downloader

    missing_dir = tmp_path / "does-not-exist"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(downloader, "YOUTUBE_POT_SERVER_HOME", str(missing_dir))
        args = build_yt_dlp_args(
            "https://www.youtube.com/watch?v=abc", tmp_path, platform="youtube"
        )

    assert not any("server_home" in a for a in args)


def test_classify_stderr_detects_youtube_bot_check() -> None:
    error = classify_stderr(
        "ERROR: [youtube] abc123: Sign in to confirm you're not a bot. "
        "This helps protect our community."
    )

    assert isinstance(error, ContentUnavailableError)


def test_classify_stderr_still_detects_rate_limit() -> None:
    # Regression guard: the new bot-check pattern must not shadow this one.
    error = classify_stderr("ERROR: HTTP Error 429: Too Many Requests")

    assert isinstance(error, RateLimitedError)


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
            "view_count": i * 1000,
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
    assert items[0]["view_count"] == 0
    assert items[1]["view_count"] == 1000


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
    # view_count is absent from this entry - must degrade to None, not raise
    assert items[0]["view_count"] is None
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


def test_build_tiktok_audio_retry_args_forces_download_format_and_overwrite(tmp_path) -> None:
    from app.downloader import _build_tiktok_audio_retry_args

    args = _build_tiktok_audio_retry_args("https://www.tiktok.com/@u/video/1", tmp_path)

    assert "-f" in args
    assert args[args.index("-f") + 1] == "download/best"
    assert "--force-overwrites" in args
    # --force-overwrites is required: yt-dlp skips re-downloading an existing
    # filename by default, which would silently keep the audio-less file.
    assert args[-1] == "https://www.tiktok.com/@u/video/1"


def test_run_yt_dlp_retries_when_tiktok_download_has_no_audio(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from app import downloader

    silent_file = tmp_path / "123.mp4"
    silent_file.write_bytes(b"video only")
    fixed_file = tmp_path / "123.mp4"  # same filename - retry overwrites in place

    call_count = {"n": 0}

    async def fake_run_subprocess(args, timeout):
        call_count["n"] += 1
        if "-f" in args and args[args.index("-f") + 1] == "download/best":
            fixed_file.write_bytes(b"video with audio")
            return 0, str(fixed_file).encode(), b""
        return 0, str(silent_file).encode(), b""

    async def fake_has_audio(path):
        return False  # first (and only distinct) file always reports no audio

    monkeypatch.setattr(downloader, "_run_subprocess", fake_run_subprocess)
    monkeypatch.setattr(downloader, "_file_has_audio", fake_has_audio)

    result = asyncio.run(
        downloader._run_yt_dlp(
            "https://www.tiktok.com/@u/video/123", tmp_path, selection=None, platform="tiktok"
        )
    )

    assert call_count["n"] == 2  # initial attempt + one retry
    assert result == [fixed_file]


def test_run_yt_dlp_does_not_retry_when_audio_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from app import downloader

    good_file = tmp_path / "123.mp4"
    good_file.write_bytes(b"video with audio")

    call_count = {"n": 0}

    async def fake_run_subprocess(args, timeout):
        call_count["n"] += 1
        return 0, str(good_file).encode(), b""

    async def fake_has_audio(path):
        return True

    monkeypatch.setattr(downloader, "_run_subprocess", fake_run_subprocess)
    monkeypatch.setattr(downloader, "_file_has_audio", fake_has_audio)

    result = asyncio.run(
        downloader._run_yt_dlp(
            "https://www.tiktok.com/@u/video/123", tmp_path, selection=None, platform="tiktok"
        )
    )

    assert call_count["n"] == 1  # no retry needed
    assert result == [good_file]


def test_run_yt_dlp_skips_audio_check_for_non_tiktok_platform(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from app import downloader

    silent_file = tmp_path / "abc.mp4"
    silent_file.write_bytes(b"video only")

    async def fake_run_subprocess(args, timeout):
        return 0, str(silent_file).encode(), b""

    async def unexpected_has_audio(path):
        raise AssertionError("audio check should be scoped to tiktok only")

    monkeypatch.setattr(downloader, "_run_subprocess", fake_run_subprocess)
    monkeypatch.setattr(downloader, "_file_has_audio", unexpected_has_audio)

    result = asyncio.run(
        downloader._run_yt_dlp(
            "https://www.youtube.com/watch?v=abc", tmp_path, selection=None, platform="youtube"
        )
    )

    assert result == [silent_file]


def test_run_yt_dlp_skips_audio_check_for_audio_only_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from app import downloader

    audio_file = tmp_path / "123.mp3"
    audio_file.write_bytes(b"audio only, no video stream - expected for -x extraction")

    async def fake_run_subprocess(args, timeout):
        return 0, str(audio_file).encode(), b""

    async def unexpected_has_audio(path):
        raise AssertionError("audio check is for video downloads, not audio extraction")

    monkeypatch.setattr(downloader, "_run_subprocess", fake_run_subprocess)
    monkeypatch.setattr(downloader, "_file_has_audio", unexpected_has_audio)

    result = asyncio.run(
        downloader._run_yt_dlp(
            "https://www.tiktok.com/@u/video/123",
            tmp_path,
            selection={"type": "audio", "bitrate": 128},
            platform="tiktok",
        )
    )

    assert result == [audio_file]


def test_file_has_audio_true_when_ffprobe_reports_audio_stream(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from app import downloader

    class FakeProc:
        async def communicate(self):
            return b"audio\n", b""

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    assert asyncio.run(downloader._file_has_audio(tmp_path / "some.mp4")) is True


def test_file_has_audio_false_when_ffprobe_reports_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from app import downloader

    class FakeProc:
        async def communicate(self):
            return b"", b""

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    assert asyncio.run(downloader._file_has_audio(tmp_path / "some.mp4")) is False


def test_file_has_audio_fails_open_when_ffprobe_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from app import downloader

    async def fake_create_subprocess_exec(*args, **kwargs):
        raise FileNotFoundError("ffprobe not found")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    # ffprobe missing shouldn't block downloads - fail open (assume audio ok)
    assert asyncio.run(downloader._file_has_audio(tmp_path / "some.mp4")) is True
