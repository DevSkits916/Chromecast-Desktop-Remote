import zipfile

import pytest

import chromecast_remote.platform_tools as platform_tools
from chromecast_remote.platform_tools import REQUIRED_FILES, extract_platform_tools_archive


def make_archive(path, names):
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(f"platform-tools/{name}", f"contents of {name}")
        archive.writestr("platform-tools/../../../outside.txt", "must not be extracted")


def test_extracts_only_managed_adb_runtime(tmp_path):
    archive = tmp_path / "platform-tools.zip"
    destination = tmp_path / "managed"
    make_archive(archive, [*REQUIRED_FILES, "source.properties", "fastboot.exe"])
    adb = extract_platform_tools_archive(archive, destination)
    assert adb == destination / "adb.exe"
    assert all((destination / name).is_file() for name in REQUIRED_FILES)
    assert (destination / "source.properties").is_file()
    assert not (destination / "fastboot.exe").exists()
    assert not (tmp_path / "outside.txt").exists()


def test_rejects_incomplete_platform_tools_archive(tmp_path):
    archive = tmp_path / "incomplete.zip"
    make_archive(archive, ["adb.exe"])
    with pytest.raises(ValueError, match="missing required"):
        extract_platform_tools_archive(archive, tmp_path / "managed")


def test_managed_install_downloads_and_places_runtime(tmp_path, monkeypatch):
    archive = tmp_path / "official-platform-tools.zip"
    make_archive(archive, [*REQUIRED_FILES, "source.properties"])
    app_data = tmp_path / "app-data"
    managed_adb = app_data / "platform-tools" / "adb.exe"
    monkeypatch.setattr(platform_tools, "PLATFORM_TOOLS_URL", archive.as_uri())
    monkeypatch.setattr(platform_tools, "config_dir", lambda: app_data)
    monkeypatch.setattr(platform_tools, "managed_adb_path", lambda: managed_adb)
    ok, message, path = platform_tools.install_managed_platform_tools()
    assert ok, message
    assert path == str(managed_adb)
    assert all((managed_adb.parent / name).is_file() for name in REQUIRED_FILES)
    assert not list(app_data.glob("*.zip"))
