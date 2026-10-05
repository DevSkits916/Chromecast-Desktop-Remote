import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest

@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr('chromecast_remote.ui.save_settings', lambda settings: None)
    monkeypatch.setattr('chromecast_remote.ui.find_adb', lambda configured='': None)
    monkeypatch.setattr('chromecast_remote.ui.QTimer.singleShot', lambda interval, callback: None)
