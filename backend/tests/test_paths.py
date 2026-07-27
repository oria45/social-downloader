import sys

import pytest

from app import paths


def test_is_frozen_false_by_default() -> None:
    assert paths.is_frozen() is False


def test_is_frozen_true_when_sys_frozen_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert paths.is_frozen() is True


def test_tool_path_returns_bare_name_in_dev() -> None:
    assert paths.tool_path("yt-dlp") == "yt-dlp"


def test_tool_path_returns_bundled_exe_when_frozen(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert paths.tool_path("yt-dlp") == str(tmp_path / "tools" / "yt-dlp.exe")


def test_frontend_dist_dir_dev_path() -> None:
    assert paths.frontend_dist_dir() == paths.BACKEND_ROOT.parent / "frontend" / "dist"


def test_frontend_dist_dir_bundled_when_frozen(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert paths.frontend_dist_dir() == tmp_path / "frontend_dist"


def test_writable_data_dir_dev_path() -> None:
    assert paths.writable_data_dir() == paths.BACKEND_ROOT / "downloads"


def test_writable_data_dir_uses_local_app_data_when_frozen(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert paths.writable_data_dir() == tmp_path / "SocialDownloader" / "downloads"


def test_writable_data_dir_falls_back_to_home_when_no_local_app_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert paths.writable_data_dir() == paths.Path.home() / "SocialDownloader" / "downloads"
