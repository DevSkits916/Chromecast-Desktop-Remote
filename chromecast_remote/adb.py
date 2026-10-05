from __future__ import annotations

import re
import ipaddress
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

KEYCODES = {
    "up": 19,
    "down": 20,
    "left": 21,
    "right": 22,
    "ok": 23,
    "back": 4,
    "home": 3,
    "power": 26,
    "volume_up": 24,
    "volume_down": 25,
    "mute": 164,
    "play_pause": 85,
    "previous": 88,
    "next": 87,
    "stop": 86,
    "rewind": 89,
    "fast_forward": 90,
}


@dataclass(slots=True)
class AdbResult:
    action: str
    ok: bool
    output: str
    return_code: int = -1
    generation: int = -1


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    name: str
    service: str
    ip: str
    port: int


def parse_mdns_services(output: str, service: str = "_adb-tls-connect._tcp") -> list[DiscoveredDevice]:
    devices: list[DiscoveredDevice] = []
    for raw_line in output.splitlines():
        parts = raw_line.split()
        if len(parts) < 3 or parts[-2] != service:
            continue
        address = parts[-1]
        if ":" not in address:
            continue
        ip, port_text = address.rsplit(":", 1)
        try:
            port = int(port_text)
        except ValueError:
            continue
        try:
            ipaddress.ip_address(ip.strip("[]"))
        except ValueError:
            continue
        if ip and 1 <= port <= 65535:
            device = DiscoveredDevice(parts[0], parts[-2], ip, port)
            if not any(d.ip == ip and d.port == port for d in devices):
                devices.append(device)
    return devices


def device_serial(ip: str, port: int | str) -> str:
    address = ipaddress.ip_address(ip.strip().strip("[]"))
    if not 1 <= int(port) <= 65535:
        raise ValueError("Connection port must be between 1 and 65535.")
    host = f"[{address}]" if address.version == 6 else str(address)
    return f"{host}:{int(port)}"


def escape_android_text(text: str) -> str:
    """Escape text for Android's `input text` command (ADB shell syntax)."""
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    if "\x00" in text:
        raise ValueError("Text cannot contain NUL characters.")
    escaped = re.sub(r"([&|;<>*()'\"`$\\])", r"\\\1", text)
    return escaped.replace("%", "\\%").replace(" ", "%s")


def friendly_error(output: str, timed_out: bool = False) -> str:
    low = output.lower()
    if timed_out:
        return "ADB did not respond in time. Check the TV address and wireless debugging."
    if "unauthorized" in low:
        return "The TV has not authorized this computer. Pair it again and accept any TV prompt."
    if "offline" in low:
        return "The TV is offline. Wake it, confirm Wi-Fi, then reconnect."
    if "cannot connect" in low or "failed to connect" in low or "connection refused" in low:
        return "Could not reach the TV. Confirm its IP, connection port, and Wireless debugging screen."
    if "more than one device" in low:
        return "Multiple ADB devices were found. This remote will target the saved TV address."
    if "no devices" in low or "device not found" in low:
        return "The TV is disconnected. Connect or pair it first."
    if "install_failed_version_downgrade" in low:
        return "A newer version of this app is already installed on the TV. Use a newer APK or uninstall the existing app first."
    if "install_failed_update_incompatible" in low:
        return "The installed app has a different signature. Uninstalling it first may fix this, but that can erase the app's data."
    if "install_failed_insufficient_storage" in low:
        return "The TV does not have enough free storage for this APK."
    if "install_failed_user_restricted" in low:
        return "The TV blocked the installation. Check its developer and app-verification settings, then accept any TV prompt."
    if "install_failed_invalid_apk" in low or "failed to parse" in low:
        return "The selected file is not a valid APK or is incompatible with this TV."
    return output.strip() or "ADB command failed without an explanation."


def run_adb(adb_path: str, args: list[str], action: str, timeout: float = 12.0) -> AdbResult:
    try:
        completed = subprocess.run(
            [adb_path, *args],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
        ok = completed.returncode == 0 and not any(
            phrase in output.lower()
            for phrase in ("failed to", "cannot connect", "error:", "unauthorized", "offline", "failure [")
        )
        return AdbResult(action, ok, output if ok else friendly_error(output), completed.returncode)
    except subprocess.TimeoutExpired:
        return AdbResult(action, False, friendly_error("", timed_out=True))
    except FileNotFoundError:
        return AdbResult(action, False, "ADB was not found. Choose adb.exe in Settings.")
    except OSError as exc:
        return AdbResult(action, False, f"ADB could not start: {exc}")


class WorkerSignals(QObject):
    finished = Signal(object)


class AdbTask(QRunnable):
    def __init__(self, adb_path: str, args: list[str], action: str, timeout: float):
        super().__init__()
        self.adb_path = adb_path
        self.args = args
        self.action = action
        self.timeout = timeout
        self.signals = WorkerSignals()

    def run(self) -> None:
        if not getattr(self, "is_current", lambda: True)():
            result = AdbResult(self.action, False, "Canceled after switching devices.")
        else:
            try:
                if self.action.startswith("install:"):
                    validate_apk(Path(self.args[-1]))
                result = run_adb(self.adb_path, self.args, self.action, self.timeout)
            except (ValueError, OSError) as exc:
                result = AdbResult(self.action, False, str(exc))
        result.generation = getattr(self, "generation", -1)
        self.args = []  # Do not retain pairing codes after execution.
        self.signals.finished.emit(result)


class AdbController(QObject):
    result = Signal(object)
    busy_changed = Signal(bool)

    def __init__(self, adb_path: str | None = None):
        super().__init__()
        self.adb_path = adb_path or ""
        self.serial = ""
        self.pool = QThreadPool.globalInstance()
        self._command_id = 0
        self._running = 0
        self.generation = 0
        self._pending = set()
        self._tasks = {}
        self.command_pool = QThreadPool(self)
        self.command_pool.setMaxThreadCount(1)

    @property
    def available(self) -> bool:
        return bool(self.adb_path and Path(self.adb_path).is_file())

    def set_adb_path(self, path: str | None) -> None:
        self.adb_path = path or ""

    def execute(self, args: list[str], action: str, timeout: float = 12.0) -> bool:
        if not self.available:
            self.result.emit(AdbResult(action, False, "ADB was not found. Open Settings and choose adb.exe."))
            return False
        if args == ["mdns", "services"] and any(generation == self.generation and pending.startswith("discover") for generation, pending in self._pending):
            return False
        token = (self.generation, action)
        if token in self._pending or (action.startswith("key:") and self._running >= 4):
            return False
        task = AdbTask(self.adb_path, args, action, timeout)
        task.generation = self.generation
        task.is_current = lambda generation=self.generation: generation == self.generation
        self._tasks[token] = task
        self._pending.add(token)
        self._running += 1
        self.busy_changed.emit(True)
        task.signals.finished.connect(self._on_finished)
        (self.command_pool if action.startswith("key:") or action == "text" else self.pool).start(task)
        return True

    def _on_finished(self, result: AdbResult) -> None:
        self._running = max(0, self._running - 1)
        self.busy_changed.emit(self._running > 0)
        self._pending.discard((result.generation, result.action))
        self._tasks.pop((result.generation, result.action), None)
        if result.generation == self.generation:
            if result.action.startswith("key:"):
                result.action = ":".join(result.action.split(":")[:2])
            self.result.emit(result)

    def invalidate(self):
        self.generation += 1
        self.serial = ""
        # Queued tasks check their generation before executing.

    def connect_device(self, ip: str, port: int | str) -> bool:
        self.serial = device_serial(ip, port)
        return self.execute(["connect", self.serial], "connect", 15)

    def disconnect_device(self) -> bool:
        if not self.serial:
            return False
        args = ["disconnect", self.serial]
        return self.execute(args, "disconnect")

    def pair_device(self, ip: str, port: int | str, code: str) -> bool:
        return self.execute(["pair", device_serial(ip, port), code.strip()], "pair", 20)

    def discover_devices(self, action: str = "discover") -> bool:
        return self.execute(["mdns", "services"], action, 15)

    def target_args(self, command: list[str]) -> list[str]:
        if not self.serial:
            raise ValueError("Select and connect a TV first.")
        return ["-s", self.serial] + command

    def key(self, name: str) -> bool:
        if not self.serial:
            return False
        self._command_id += 1
        return self.execute(self.target_args(["shell", "input", "keyevent", str(KEYCODES[name])]), f"key:{name}:{self._command_id}")

    def send_text(self, text: str) -> bool:
        if not self.serial:
            return False
        return self.execute(self.target_args(["shell", "input", "text", escape_android_text(text)]), "text")

    def launch_package(self, package: str) -> bool:
        if not self.serial or not valid_package(package):
            self.result.emit(AdbResult("launch", False, "Enter a valid Android package name."))
            return False
        return self.execute(
            self.target_args(["shell", "monkey", "-p", package.strip(), "-c", "android.intent.category.LAUNCHER", "1"]),
            f"launch:{package.strip()}",
        )

    def install_apk(self, path: str) -> bool:
        apk = Path(path).expanduser()
        if apk.suffix.lower() != ".apk" or not apk.is_file():
            self.result.emit(AdbResult("install", False, "Choose a valid local .apk file first."))
            return False
        if not self.serial:
            return False
        return self.execute(
            self.target_args(["install", "-r", str(apk.resolve())]),
            f"install:{apk.name}",
            180,
        )


def valid_package(package: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+", package))


def parse_packages(output: str) -> list[str]:
    return sorted({line[8:].strip() for line in output.splitlines()
                   if line.startswith("package:") and valid_package(line[8:].strip())})


def parse_getprop(output: str) -> dict:
    props = dict(re.findall(r"^\[([^]\r\n]+)\]: \[([^]\r\n]*)\]$", output, re.M))
    return {key: props.get(prop, "") for key, prop in {
        "manufacturer": "ro.product.manufacturer", "model": "ro.product.model",
        "android_version": "ro.build.version.release", "api_level": "ro.build.version.sdk"}.items()}


def validate_apk(path: Path) -> None:
    import zipfile
    if not path.is_file() or path.suffix.lower() != ".apk" or path.stat().st_size > 2 * 1024**3:
        raise ValueError("Choose a valid local .apk file (maximum 2 GB).")
    try:
        with zipfile.ZipFile(path) as archive:
            if len(archive.infolist()) > 100000 or "AndroidManifest.xml" not in archive.namelist():
                raise ValueError("APK has no Android manifest or has too many entries.")
            manifest = archive.getinfo("AndroidManifest.xml")
            if manifest.file_size > 4 * 1024**2 or manifest.flag_bits & 1:
                raise ValueError("Invalid or encrypted APK manifest.")
            archive.read(manifest)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("Invalid APK archive.") from exc
