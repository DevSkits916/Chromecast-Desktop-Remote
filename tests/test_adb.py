from pathlib import Path
import sys

from chromecast_remote.adb import KEYCODES, device_serial, escape_android_text, friendly_error, run_adb


def test_device_serial():
    assert device_serial(" 192.168.1.20 ", "37123") == "192.168.1.20:37123"


def test_android_text_escaping():
    escaped = escape_android_text("Hello TV & 100%")
    assert escaped == r"Hello%sTV%s\&%s100\%"


def test_friendly_errors():
    assert "authorized" in friendly_error("error: device unauthorized")
    assert "offline" in friendly_error("device offline")
    assert "Could not reach" in friendly_error("failed to connect")


def test_missing_adb_is_safe(tmp_path: Path):
    result = run_adb(str(tmp_path / "missing-adb.exe"), ["version"], "probe")
    assert not result.ok
    assert "not found" in result.output.lower()


def test_mock_adb_success_and_failure():
    success = run_adb(sys.executable, ["-c", "print('connected to mock-tv:5555')"], "connect")
    failure = run_adb(sys.executable, ["-c", "import sys; print('error: device offline'); sys.exit(1)"], "key:home")
    assert success.ok
    assert "mock-tv" in success.output
    assert not failure.ok
    assert "offline" in failure.output.lower()


def test_required_android_keycodes():
    assert KEYCODES == {
        "up": 19, "down": 20, "left": 21, "right": 22, "ok": 23,
        "back": 4, "home": 3, "power": 26, "volume_up": 24,
        "volume_down": 25, "mute": 164, "play_pause": 85,
        "rewind": 89, "fast_forward": 90,
    }
