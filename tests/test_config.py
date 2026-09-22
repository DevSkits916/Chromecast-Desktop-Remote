import json

from chromecast_remote.config import DEFAULTS, load_settings, save_settings


def test_settings_round_trip(tmp_path):
    target = tmp_path / "settings.json"
    settings = load_settings(target)
    settings["device_ip"] = "192.168.1.44"
    settings["window"]["width"] = 512
    save_settings(settings, target)
    loaded = load_settings(target)
    assert loaded["device_ip"] == "192.168.1.44"
    assert loaded["window"]["width"] == 512


def test_corrupt_config_falls_back(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text("not-json", encoding="utf-8")
    assert load_settings(target)["adb_port"] == DEFAULTS["adb_port"]


def test_unknown_keys_are_ignored(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"unknown": "value", "adb_port": 1234}), encoding="utf-8")
    loaded = load_settings(target)
    assert "unknown" not in loaded
    assert loaded["adb_port"] == 1234
