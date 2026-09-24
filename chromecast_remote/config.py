from __future__ import annotations

import json
import os
import shutil
from copy import deepcopy
from pathlib import Path

APP_NAME = "ChromecastDesktopRemote"
DEFAULT_APPS = [
    {"name": "YouTube", "package": "com.google.android.youtube.tv"},
    {"name": "Netflix", "package": "com.netflix.ninja"},
    {"name": "Spotify", "package": "com.spotify.tv.android"},
]
DEFAULTS = {
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
    "apps": DEFAULT_APPS,
}


def config_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(root) / APP_NAME


def config_path() -> Path:
    return config_dir() / "settings.json"


def managed_adb_path() -> Path:
    return config_dir() / "platform-tools" / "adb.exe"


def load_settings(path: Path | None = None) -> dict:
    settings = deepcopy(DEFAULTS)
    target = path or config_path()
    try:
        saved = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            for key, value in saved.items():
                if key in settings:
                    if key == "window" and isinstance(value, dict):
                        settings[key].update(value)
                    else:
                        settings[key] = value
    except (OSError, json.JSONDecodeError, TypeError):
        pass
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
