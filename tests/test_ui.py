import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from chromecast_remote.config import DEFAULTS
from chromecast_remote.ui import RemoteWindow


def test_window_builds_and_modes(monkeypatch):
    app = QApplication.instance() or QApplication([])
    settings = dict(DEFAULTS)
    settings["window"] = dict(DEFAULTS["window"])
    settings["auto_connect"] = False
    settings["close_to_tray"] = False
    window = RemoteWindow(settings)
    assert window.minimumWidth() >= 300
    window.set_compact(True)
    assert window.compact
    assert not window.connection_card.isVisible()
    window.set_compact(False)
    assert not window.compact
    window.quitting = True
    window.close()
    app.processEvents()


def test_keyboard_shortcuts_and_text_field(monkeypatch):
    app = QApplication.instance() or QApplication([])
    settings = dict(DEFAULTS)
    settings["window"] = dict(DEFAULTS["window"])
    settings["auto_connect"] = False
    settings["close_to_tray"] = False
    window = RemoteWindow(settings)
    sent = []
    monkeypatch.setattr(window, "send_key", sent.append)
    window.show()
    window.activateWindow()
    window.setFocus()
    app.processEvents()
    QTest.keyClick(window, Qt.Key.Key_Up)
    QTest.keyClick(window, Qt.Key.Key_Space)
    assert sent == ["up", "play_pause"]
    window.text_edit.setFocus()
    QTest.keyClicks(window.text_edit, "Hello TV")
    assert window.text_edit.text() == "Hello TV"
    window.quitting = True
    window.close()
    app.processEvents()
