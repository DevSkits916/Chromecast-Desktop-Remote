from pathlib import Path
import sys

from chromecast_remote.adb import AdbController, KEYCODES, device_serial, escape_android_text, friendly_error, run_adb


def test_device_serial():
    assert device_serial(" 192.168.1.20 ", "37123") == "192.168.1.20:37123"


def test_android_text_escaping():
    escaped = escape_android_text("Hello TV & 100%")
    assert escaped == r"Hello%sTV%s\&%s100\%"


def test_friendly_errors():
    assert "authorized" in friendly_error("error: device unauthorized")
    assert "offline" in friendly_error("device offline")
    assert "Could not reach" in friendly_error("failed to connect")
    assert "newer version" in friendly_error("Failure [INSTALL_FAILED_VERSION_DOWNGRADE]")
    assert "enough free storage" in friendly_error("Failure [INSTALL_FAILED_INSUFFICIENT_STORAGE]")


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


def test_install_apk_targets_saved_tv_and_uses_replace(tmp_path, monkeypatch):
    apk = tmp_path / "Example TV App.apk"
    apk.write_bytes(b"mock apk")
    controller = AdbController()
    controller.serial = "192.168.1.20:37123"
    captured = {}

    def fake_execute(args, action, timeout=12.0):
        captured.update(args=args, action=action, timeout=timeout)
        return True

    monkeypatch.setattr(controller, "execute", fake_execute)
    assert controller.install_apk(str(apk))
    assert captured["args"] == ["-s", controller.serial, "install", "-r", str(apk.resolve())]
    assert captured["action"] == "install:Example TV App.apk"
    assert captured["timeout"] == 180


def test_install_apk_rejects_missing_or_non_apk(tmp_path):
    controller = AdbController()
    results = []
    controller.result.connect(results.append)
    assert not controller.install_apk(str(tmp_path / "missing.apk"))
    assert not controller.install_apk(str(tmp_path / "notes.txt"))
    assert all("valid local .apk" in result.output for result in results)
