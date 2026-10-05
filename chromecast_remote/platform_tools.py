from __future__ import annotations

import shutil
import hashlib
import json
from urllib.parse import urlparse
import urllib.request
import uuid
import zipfile
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from .config import config_dir, managed_adb_path
from . import __version__

PLATFORM_TOOLS_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
SDK_TERMS_URL = "https://developer.android.com/studio/terms"
MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024
REQUIRED_FILES = ("adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll")


def extract_platform_tools_archive(archive_path: Path, destination: Path) -> Path:
    """Extract only the Windows ADB runtime files from Google's archive."""
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > 5000:
            raise ValueError("Too many files in the Platform Tools archive.")
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
            info = archive.getinfo(member)
            if info.file_size > MAX_DOWNLOAD_BYTES or info.flag_bits & 1:
                raise ValueError("Invalid Platform Tools archive member.")
            if sum(i.file_size for i in members) > MAX_DOWNLOAD_BYTES:
                raise ValueError("Expanded Platform Tools archive exceeds the safety limit.")
            if archive.namelist().count(member) != 1:
                raise ValueError("Duplicate Platform Tools archive member.")
            target = destination / name
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    adb = destination / "adb.exe"
    if not adb.is_file():
        raise ValueError("ADB was not found after extracting Platform Tools.")
    return adb


def install_managed_platform_tools(force: bool = False) -> tuple[bool, str, str]:
    root = config_dir()
    destination = managed_adb_path().parent
    if not force and all((destination / name).is_file() for name in REQUIRED_FILES):
        return True, "Managed ADB is already installed.", str(managed_adb_path())

    token = uuid.uuid4().hex
    archive_path = root / f"platform-tools-{token}.zip"
    staging = root / f"platform-tools-{token}"
    backup = root / f"platform-tools-backup-{token}"
    try:
        root.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(PLATFORM_TOOLS_URL, headers={"User-Agent": f"ChromecastDesktopRemote/{__version__}"})
        with urllib.request.urlopen(request, timeout=45) as response, archive_path.open("wb") as output:
            final_url = urlparse(response.geturl())
            if urlparse(PLATFORM_TOOLS_URL).scheme != "file" and (final_url.scheme != "https" or final_url.hostname != "dl.google.com"):
                raise ValueError("Platform Tools must come from Google's official HTTPS host.")
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
        # This hash records downloaded bytes; it is not an independently verified checksum.
        digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        (staging / "install-info.json").write_text(json.dumps({"download_sha256": digest, "revision": installed_platform_version(staging)}), encoding="utf-8")
        if destination.exists():
            destination.replace(backup)
        try:
            staging.replace(destination)
        except OSError:
            if backup.exists():
                backup.replace(destination)
            raise
        if backup.exists():
            try:
                shutil.rmtree(backup)
            except OSError:
                pass  # A retained backup is safer than declaring a successful install failed.
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
    def __init__(self, force=False):
        super().__init__()
        self.force = force
        self.signals = PlatformToolsSignals()

    def run(self) -> None:
        self.signals.finished.emit(*install_managed_platform_tools(self.force))


def installed_platform_version(directory: Path | None = None) -> str:
    import re
    try:
        properties = ((directory or managed_adb_path().parent) / "source.properties").read_text(encoding="utf-8")
        match = re.search(r"^Pkg.Revision\s*=\s*(.+)$", properties, re.M)
        return match.group(1).strip() if match else "Unknown"
    except (OSError, UnicodeError):
        return "Unknown"
