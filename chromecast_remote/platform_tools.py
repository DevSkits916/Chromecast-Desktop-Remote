from __future__ import annotations

import shutil
import urllib.request
import uuid
import zipfile
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from .config import config_dir, managed_adb_path

PLATFORM_TOOLS_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
SDK_TERMS_URL = "https://developer.android.com/studio/terms"
MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024
REQUIRED_FILES = ("adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll")


def extract_platform_tools_archive(archive_path: Path, destination: Path) -> Path:
    """Extract only the Windows ADB runtime files from Google's archive."""
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        required_members = {f"platform-tools/{name}" for name in REQUIRED_FILES}
        missing = required_members - names
        if missing:
            raise ValueError("The downloaded Platform Tools archive is missing required ADB files.")
        allowed_names = set(REQUIRED_FILES) | {"NOTICE.txt", "source.properties", "mke2fs.conf"}
        for name in allowed_names:
            member = f"platform-tools/{name}"
            if member not in names:
                continue
            target = destination / name
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    adb = destination / "adb.exe"
    if not adb.is_file():
        raise ValueError("ADB was not found after extracting Platform Tools.")
    return adb


def install_managed_platform_tools() -> tuple[bool, str, str]:
    root = config_dir()
    root.mkdir(parents=True, exist_ok=True)
    destination = managed_adb_path().parent
    if all((destination / name).is_file() for name in REQUIRED_FILES):
        return True, "Managed ADB is already installed.", str(managed_adb_path())

    token = uuid.uuid4().hex
    archive_path = root / f"platform-tools-{token}.zip"
    staging = root / f"platform-tools-{token}"
    try:
        request = urllib.request.Request(PLATFORM_TOOLS_URL, headers={"User-Agent": "ChromecastDesktopRemote/1.2"})
        with urllib.request.urlopen(request, timeout=45) as response, archive_path.open("wb") as output:
            declared_size = int(response.headers.get("Content-Length", "0") or 0)
            if declared_size > MAX_DOWNLOAD_BYTES:
                raise ValueError("The Platform Tools download is unexpectedly large.")
            downloaded = 0
            while chunk := response.read(1024 * 1024):
                downloaded += len(chunk)
                if downloaded > MAX_DOWNLOAD_BYTES:
                    raise ValueError("The Platform Tools download exceeded the safety limit.")
                output.write(chunk)
        extract_platform_tools_archive(archive_path, staging)
        if destination.exists():
            shutil.rmtree(destination)
        staging.replace(destination)
        return True, "Android Platform Tools installed successfully.", str(managed_adb_path())
    except Exception as exc:
        return False, f"Could not install Android Platform Tools: {exc}", ""
    finally:
        try:
            archive_path.unlink(missing_ok=True)
        except OSError:
            pass
        if staging.exists():
            try:
                shutil.rmtree(staging)
            except OSError:
                pass


class PlatformToolsSignals(QObject):
    finished = Signal(bool, str, str)


class PlatformToolsTask(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = PlatformToolsSignals()

    def run(self) -> None:
        self.signals.finished.emit(*install_managed_platform_tools())
