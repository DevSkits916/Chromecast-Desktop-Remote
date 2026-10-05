from __future__ import annotations

import json
import os
import shutil
from copy import deepcopy
from pathlib import Path

APP_NAME = "ChromecastDesktopRemote"
DEFAULTS = {
    "schema_version": 2,
    "profiles": [],
    "selected_profile": "",
    "setup_completed": False,
    "show_setup_help": False,
    "device_ip": "",
    "adb_port": 5555,
    "adb_path": "",
    "adb_terms_accepted": False,
    "auto_connect": True,
    "auto_detect_port": True,
    "always_on_top": False,
    "compact_default": False,
    "close_to_tray": True,
    "launch_windows": False,
    "window": {"x": None, "y": None, "width": 420, "height": 780},
}


def config_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(root) / APP_NAME


def config_path() -> Path:
    return config_dir() / "settings.json"


def managed_adb_path() -> Path:
    return config_dir() / "platform-tools" / "adb.exe"


def load_settings(path: Path | None = None) -> dict:
    target = path or config_path()
    try:
        saved = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        saved = {}
    return migrate_settings(saved)


def new_profile(name: str, ip: str = "", port: int = 5555, auto_connect: bool = True) -> dict:
    import uuid
    return dict(id=uuid.uuid4().hex, name=name, ip=ip, port=port,
                service_name="", model="", manufacturer="", android_version="",
                api_level="", auto_connect=auto_connect, last_connected="", favorites=[])


def migrate_settings(saved) -> dict:
    settings = deepcopy(DEFAULTS)
    if not isinstance(saved, dict):
        return settings
    for key, default in DEFAULTS.items():
        value = saved.get(key, default)
        if key == "window":
            if isinstance(value, dict):
                for field, fallback in default.items():
                    candidate = value.get(field, fallback)
                    if type(candidate) is int and (field in ("x", "y") or 100 <= candidate <= 10000):
                        settings[key][field] = candidate
                    elif candidate is None and field in ("x", "y"):
                        settings[key][field] = None
        elif isinstance(value, type(default)):
            settings[key] = deepcopy(value)
    if not 1 <= settings["adb_port"] <= 65535:
        settings["adb_port"] = 5555
    profiles = []
    for value in settings["profiles"]:
        if not isinstance(value, dict) or not isinstance(value.get("ip"), str):
            continue
        profile = new_profile("TV")
        for key, default in profile.items():
            candidate = value.get(key, default)
            if isinstance(candidate, type(default)):
                profile[key] = candidate
        if not 1 <= profile["port"] <= 65535:
            profile["port"] = 5555
        if any(p["id"] == profile["id"] for p in profiles):
            continue
        profiles.append(profile)
    if not profiles and settings["device_ip"]:
        profiles.append(new_profile("My TV", settings["device_ip"], settings["adb_port"], settings["auto_connect"]))
    settings["profiles"] = profiles
    settings["schema_version"] = 2
    if profiles:
        chosen = next((p for p in profiles if p["id"] == settings["selected_profile"]), profiles[0])
        settings["selected_profile"] = chosen["id"]
        settings.update(device_ip=chosen["ip"], adb_port=chosen["port"], auto_connect=chosen["auto_connect"])
    else:
        settings["selected_profile"] = ""
    return settings


def save_settings(settings: dict, path: Path | None = None) -> None:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(target)


def find_adb(configured: str = "") -> str | None:
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(managed_adb_path())
    on_path = shutil.which("adb")
    if on_path:
        candidates.append(Path(on_path))
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    user = Path(os.environ.get("USERPROFILE", ""))
    candidates.extend(
        [
            local / "Android" / "Sdk" / "platform-tools" / "adb.exe",
            user / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools" / "adb.exe",
            Path("C:/Android/platform-tools/adb.exe"),
        ]
    )
    bundled = Path(getattr(__import__("sys"), "_MEIPASS", "")) / "platform-tools" / "adb.exe"
    if str(bundled) and bundled.exists():
        candidates.insert(0, bundled)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def startup_shortcut_path() -> Path:
    appdata = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Chromecast Desktop Remote.cmd"


def set_launch_with_windows(enabled: bool) -> tuple[bool, str]:
    import sys

    shortcut = startup_shortcut_path()
    try:
        if enabled:
            shortcut.parent.mkdir(parents=True, exist_ok=True)
            if getattr(sys, "frozen", False):
                command = f'@start "" "{sys.executable}"\n'
            else:
                command = f'@start "" "{sys.executable}" "{Path(__file__).parents[1] / "app.py"}"\n'
            shortcut.write_text(command, encoding="utf-8")
        elif shortcut.exists():
            shortcut.unlink()
        return True, "Startup preference updated."
    except OSError as exc:
        return False, f"Could not update Windows startup: {exc}"
