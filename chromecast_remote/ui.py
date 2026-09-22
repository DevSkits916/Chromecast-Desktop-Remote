from __future__ import annotations

import json
import sys
import webbrowser
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .adb import AdbController, AdbResult, KEYCODES
from .config import DEFAULTS, find_adb, save_settings, set_launch_with_windows


def app_icon() -> QIcon:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).parents[1]))
    return QIcon(str(root / "assets" / "icon.svg"))


def button(text: str, tooltip: str = "", name: str = "") -> QPushButton:
    item = QPushButton(text)
    if tooltip:
        item.setToolTip(tooltip)
    if name:
        item.setObjectName(name)
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    return item


def card(layout) -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    frame.setLayout(layout)
    return frame


class PairDialog(QDialog):
    def __init__(self, parent: "RemoteWindow"):
        super().__init__(parent)
        self.remote = parent
        self.setWindowTitle("Pair Google TV")
        self.setMinimumWidth(430)
        root = QVBoxLayout(self)
        title = QLabel("Pair with Wireless Debugging")
        title.setObjectName("title")
        root.addWidget(title)
        instructions = QLabel(
            "On the TV, open Settings → System → About, click Android TV OS build 7 times, "
            "then open Developer options → Wireless debugging → Pair device with pairing code."
        )
        instructions.setWordWrap(True)
        instructions.setObjectName("muted")
        root.addWidget(instructions)
        form = QFormLayout()
        self.ip = QLineEdit(parent.ip_edit.text())
        self.ip.setPlaceholderText("192.168.1.50")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(37000)
        self.code = QLineEdit()
        self.code.setPlaceholderText("6-digit code")
        self.code.setMaxLength(12)
        form.addRow("TV IP", self.ip)
        form.addRow("Pairing port", self.port)
        form.addRow("Pairing code", self.code)
        root.addLayout(form)
        self.status = QLabel("Pairing uses a temporary port shown by the TV, not usually port 5555.")
        self.status.setWordWrap(True)
        self.status.setObjectName("muted")
        root.addWidget(self.status)
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = button("Close")
        cancel.clicked.connect(self.reject)
        pair = button("Pair", name="primary")
        pair.clicked.connect(self._pair)
        actions.addWidget(cancel)
        actions.addWidget(pair)
        root.addLayout(actions)
        self.remote.controller.result.connect(self._result)

    def _pair(self) -> None:
        if not self.ip.text().strip() or not self.code.text().strip():
            self.status.setText("Enter the TV IP, pairing port, and code shown on the TV.")
            return
        self.status.setText("Pairing…")
        self.remote.controller.pair_device(self.ip.text(), self.port.value(), self.code.text())

    def _result(self, result: AdbResult) -> None:
        if result.action != "pair":
            return
        self.status.setText(("Paired successfully. Close this screen, enter the connection port, then Connect." if result.ok else result.output))
        if result.ok:
            self.remote.ip_edit.setText(self.ip.text().strip())


class SettingsDialog(QDialog):
    def __init__(self, parent: "RemoteWindow"):
        super().__init__(parent)
        self.remote = parent
        self.settings = deepcopy(parent.settings)
        self.setWindowTitle("Settings")
        self.resize(570, 610)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), "General")
        tabs.addTab(self._apps_tab(), "Apps")
        root.addWidget(tabs)
        actions = QHBoxLayout()
        reset = button("Reset configuration")
        reset.clicked.connect(self._reset)
        actions.addWidget(reset)
        actions.addStretch()
        cancel = button("Cancel")
        cancel.clicked.connect(self.reject)
        save = button("Save", name="primary")
        save.clicked.connect(self._save)
        actions.addWidget(cancel)
        actions.addWidget(save)
        root.addLayout(actions)

    def _general_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.ip = QLineEdit(str(self.settings["device_ip"]))
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(self.settings["adb_port"]))
        adb_row = QWidget()
        adb_layout = QHBoxLayout(adb_row)
        adb_layout.setContentsMargins(0, 0, 0, 0)
        self.adb = QLineEdit(str(self.settings["adb_path"]))
        browse = button("Browse…")
        browse.clicked.connect(self._browse_adb)
        adb_layout.addWidget(self.adb, 1)
        adb_layout.addWidget(browse)
        form.addRow("Saved TV address", self.ip)
        form.addRow("Connection port", self.port)
        form.addRow("Path to adb.exe", adb_row)
        layout.addLayout(form)
        download = button("Download official Android Platform Tools")
        download.clicked.connect(lambda: webbrowser.open("https://developer.android.com/tools/releases/platform-tools"))
        layout.addWidget(download)
        self.auto = QCheckBox("Auto-connect on startup")
        self.auto.setChecked(bool(self.settings["auto_connect"]))
        self.top = QCheckBox("Always on top by default")
        self.top.setChecked(bool(self.settings["always_on_top"]))
        self.compact = QCheckBox("Start in compact mode")
        self.compact.setChecked(bool(self.settings["compact_default"]))
        self.startup = QCheckBox("Launch with Windows")
        self.startup.setChecked(bool(self.settings["launch_windows"]))
        self.tray = QCheckBox("Closing the window minimizes to the tray")
        self.tray.setChecked(bool(self.settings["close_to_tray"]))
        for item in (self.auto, self.top, self.compact, self.startup, self.tray):
            layout.addWidget(item)
        note = QLabel("Settings are stored only on this PC in your local AppData folder. No cloud service or telemetry is used.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        layout.addStretch()
        return page

    def _apps_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        note = QLabel("Package names vary by TV and app version. These defaults are editable and launching uses Android's package launcher.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        self.app_list = QListWidget()
        for app in self.settings.get("apps", []):
            self.app_list.addItem(f'{app.get("name", "App")}  —  {app.get("package", "")}')
        layout.addWidget(self.app_list)
        form = QFormLayout()
        self.app_name = QLineEdit()
        self.app_name.setPlaceholderText("Plex")
        self.app_package = QLineEdit()
        self.app_package.setPlaceholderText("com.example.tv")
        form.addRow("Button name", self.app_name)
        form.addRow("Android package", self.app_package)
        layout.addLayout(form)
        actions = QHBoxLayout()
        add = button("Add app")
        add.clicked.connect(self._add_app)
        remove = button("Remove selected")
        remove.clicked.connect(lambda: self.app_list.takeItem(self.app_list.currentRow()))
        actions.addWidget(add)
        actions.addWidget(remove)
        actions.addStretch()
        layout.addLayout(actions)
        return page

    def _browse_adb(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(self, "Choose adb.exe", self.adb.text(), "ADB executable (adb.exe);;All files (*)")
        if chosen:
            self.adb.setText(chosen)

    def _add_app(self) -> None:
        name, package = self.app_name.text().strip(), self.app_package.text().strip()
        if name and package:
            self.app_list.addItem(f"{name}  —  {package}")
            self.app_name.clear()
            self.app_package.clear()

    def _collect_apps(self) -> list[dict]:
        apps = []
        for index in range(self.app_list.count()):
            parts = self.app_list.item(index).text().split("  —  ", 1)
            if len(parts) == 2:
                apps.append({"name": parts[0].strip(), "package": parts[1].strip()})
        return apps

    def _save(self) -> None:
        old_startup = bool(self.remote.settings.get("launch_windows"))
        self.settings.update(
            {
                "device_ip": self.ip.text().strip(),
                "adb_port": self.port.value(),
                "adb_path": self.adb.text().strip(),
                "auto_connect": self.auto.isChecked(),
                "always_on_top": self.top.isChecked(),
                "compact_default": self.compact.isChecked(),
                "launch_windows": self.startup.isChecked(),
                "close_to_tray": self.tray.isChecked(),
                "apps": self._collect_apps(),
            }
        )
        if old_startup != self.startup.isChecked():
            ok, message = set_launch_with_windows(self.startup.isChecked())
            if not ok:
                QMessageBox.warning(self, "Windows startup", message)
                self.settings["launch_windows"] = old_startup
        self.remote.apply_settings(self.settings)
        self.accept()

    def _reset(self) -> None:
        answer = QMessageBox.question(self, "Reset configuration", "Reset all settings and app buttons to their defaults?")
        if answer == QMessageBox.StandardButton.Yes:
            if self.remote.settings.get("launch_windows"):
                set_launch_with_windows(False)
            self.settings = deepcopy(DEFAULTS)
            self.remote.apply_settings(self.settings)
            self.accept()


class RemoteWindow(QMainWindow):
    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings
        self.controller = AdbController(find_adb(settings.get("adb_path", "")))
        if self.controller.adb_path and not settings.get("adb_path"):
            self.settings["adb_path"] = self.controller.adb_path
        self.connected = False
        self.quitting = False
        self.compact = bool(settings.get("compact_default"))
        self.setWindowTitle("Chromecast Desktop Remote")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(330, 510)
        self._build_ui()
        self._build_tray()
        self.controller.result.connect(self._handle_result)
        self.controller.busy_changed.connect(self._busy)
        QApplication.instance().installEventFilter(self)
        self._restore_window()
        self.set_always_on_top(bool(settings.get("always_on_top")))
        self.set_compact(self.compact)
        self._update_adb_notice()
        if settings.get("auto_connect") and settings.get("device_ip") and self.controller.available:
            QTimer.singleShot(700, self.connect_device)

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        root = QVBoxLayout(host)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        status_col = QVBoxLayout()
        self.status_label = QLabel("● Disconnected")
        self.status_label.setObjectName("statusDisconnected")
        saved_ip = str(self.settings.get("device_ip", "")).strip()
        saved_port = int(self.settings.get("adb_port", 5555))
        self.device_label = QLabel(f"{saved_ip}:{saved_port}" if saved_ip else "No TV selected")
        self.device_label.setObjectName("muted")
        status_col.addWidget(self.status_label)
        status_col.addWidget(self.device_label)
        header.addLayout(status_col, 1)
        self.top_button = button("Pin", "Always on top")
        self.top_button.setCheckable(True)
        self.top_button.toggled.connect(self.set_always_on_top)
        mode = button("Compact", "Toggle compact remote")
        mode.clicked.connect(lambda: self.set_compact(not self.compact))
        settings_button = button("⚙", "Settings", "round")
        settings_button.clicked.connect(self.open_settings)
        header.addWidget(self.top_button)
        header.addWidget(mode)
        header.addWidget(settings_button)
        root.addLayout(header)

        connection_layout = QVBoxLayout()
        connection_layout.setContentsMargins(14, 14, 14, 14)
        connect_row = QHBoxLayout()
        self.ip_edit = QLineEdit(str(self.settings.get("device_ip", "")))
        self.ip_edit.setPlaceholderText("TV IP address")
        self.port_edit = QSpinBox()
        self.port_edit.setRange(1, 65535)
        self.port_edit.setValue(int(self.settings.get("adb_port", 5555)))
        self.port_edit.setMaximumWidth(92)
        connect_row.addWidget(self.ip_edit, 1)
        connect_row.addWidget(self.port_edit)
        connection_layout.addLayout(connect_row)
        action_row = QHBoxLayout()
        self.connect_button = button("Connect", name="primary")
        self.connect_button.clicked.connect(self.connect_device)
        disconnect = button("Disconnect")
        disconnect.clicked.connect(self.disconnect_device)
        pair = button("Pair device")
        pair.clicked.connect(lambda: PairDialog(self).exec())
        action_row.addWidget(self.connect_button)
        action_row.addWidget(disconnect)
        action_row.addWidget(pair)
        connection_layout.addLayout(action_row)
        self.adb_notice = QLabel()
        self.adb_notice.setWordWrap(True)
        self.adb_notice.setObjectName("muted")
        connection_layout.addWidget(self.adb_notice)
        self.connection_card = card(connection_layout)
        root.addWidget(self.connection_card)

        power_row = QHBoxLayout()
        power_row.addStretch()
        power = button("⏻", "Power", "round")
        power.clicked.connect(lambda: self.send_key("power"))
        power_row.addWidget(power)
        power_row.addStretch()
        root.addLayout(power_row)

        nav_grid = QGridLayout()
        nav_grid.setHorizontalSpacing(10)
        nav_grid.setVerticalSpacing(10)
        for text, name, row, col in [
            ("▲", "up", 0, 1), ("◀", "left", 1, 0), ("OK", "ok", 1, 1),
            ("▶", "right", 1, 2), ("▼", "down", 2, 1),
        ]:
            item = button(text, name.replace("_", " ").title(), "ok" if name == "ok" else "nav")
            item.clicked.connect(lambda checked=False, key=name: self.send_key(key))
            nav_grid.addWidget(item, row, col)
        nav_grid.setColumnStretch(0, 1)
        nav_grid.setColumnStretch(1, 1)
        nav_grid.setColumnStretch(2, 1)
        root.addLayout(nav_grid)

        back_home = QHBoxLayout()
        back = button("↩  Back")
        back.clicked.connect(lambda: self.send_key("back"))
        home = button("⌂  Home")
        home.clicked.connect(lambda: self.send_key("home"))
        back_home.addWidget(back)
        back_home.addWidget(home)
        root.addLayout(back_home)

        media_layout = QVBoxLayout()
        media_layout.setContentsMargins(14, 12, 14, 12)
        media_title = QLabel("Media")
        media_title.setObjectName("muted")
        media_layout.addWidget(media_title)
        media_row = QHBoxLayout()
        for text, name in [("⏪", "rewind"), ("⏯", "play_pause"), ("⏩", "fast_forward")]:
            item = button(text, name.replace("_", " ").title(), "round")
            item.clicked.connect(lambda checked=False, key=name: self.send_key(key))
            media_row.addWidget(item)
        media_layout.addLayout(media_row)
        self.media_card = card(media_layout)
        root.addWidget(self.media_card)

        volume = QHBoxLayout()
        for text, name in [("−", "volume_down"), ("Mute", "mute"), ("+", "volume_up")]:
            item = button(text, name.replace("_", " ").title())
            item.clicked.connect(lambda checked=False, key=name: self.send_key(key))
            volume.addWidget(item)
        root.addLayout(volume)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(14, 12, 14, 12)
        text_label = QLabel("Send text to the focused TV field")
        text_label.setObjectName("muted")
        text_layout.addWidget(text_label)
        text_row = QHBoxLayout()
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("Type text…")
        self.text_edit.returnPressed.connect(self.send_text)
        send = button("Send", name="primary")
        send.clicked.connect(self.send_text)
        text_row.addWidget(self.text_edit, 1)
        text_row.addWidget(send)
        text_layout.addLayout(text_row)
        self.text_card = card(text_layout)
        root.addWidget(self.text_card)

        apps_layout = QVBoxLayout()
        apps_layout.setContentsMargins(14, 12, 14, 12)
        apps_title = QLabel("Apps")
        apps_title.setObjectName("muted")
        apps_layout.addWidget(apps_title)
        self.apps_row = QHBoxLayout()
        apps_layout.addLayout(self.apps_row)
        self.apps_card = card(apps_layout)
        root.addWidget(self.apps_card)
        self.refresh_apps()

        self.message = QLabel("Ready")
        self.message.setWordWrap(True)
        self.message.setObjectName("muted")
        root.addWidget(self.message)
        scroll.setWidget(host)
        self.setCentralWidget(scroll)

    def _build_tray(self) -> None:
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(app_icon(), self)
        menu = QMenu()
        show = QAction("Show Remote", self)
        show.triggered.connect(self.show_remote)
        hide = QAction("Hide Remote", self)
        hide.triggered.connect(self.hide)
        connect = QAction("Connect", self)
        connect.triggered.connect(self.connect_device)
        disconnect = QAction("Disconnect", self)
        disconnect.triggered.connect(self.disconnect_device)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        for action in (show, hide, connect, disconnect):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.setToolTip("Chromecast Desktop Remote")
        tray.activated.connect(lambda reason: self.show_remote() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        tray.show()
        self.tray = tray

    def _restore_window(self) -> None:
        state = self.settings.get("window", {})
        self.resize(max(330, int(state.get("width") or 420)), max(510, int(state.get("height") or 780)))
        x, y = state.get("x"), state.get("y")
        if x is not None and y is not None:
            screens = QApplication.screens()
            point_ok = any(screen.availableGeometry().adjusted(-80, -80, 80, 80).contains(int(x), int(y)) for screen in screens)
            if point_ok:
                self.move(int(x), int(y))

    def _update_adb_notice(self) -> None:
        if self.controller.available:
            self.adb_notice.setText(f"ADB ready: {Path(self.controller.adb_path).name}")
        else:
            self.adb_notice.setText("ADB is not installed or could not be found. Open Settings to choose adb.exe or download official Platform Tools.")

    def refresh_apps(self) -> None:
        while self.apps_row.count():
            item = self.apps_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        apps = self.settings.get("apps", [])
        if not apps:
            label = QLabel("Add app buttons in Settings.")
            label.setObjectName("muted")
            self.apps_row.addWidget(label)
            return
        for app in apps:
            item = button(str(app.get("name", "App")))
            package = str(app.get("package", ""))
            item.setToolTip(package)
            item.clicked.connect(lambda checked=False, pkg=package: self.controller.launch_package(pkg))
            self.apps_row.addWidget(item)

    def connect_device(self) -> None:
        ip = self.ip_edit.text().strip()
        if not ip:
            self.message.setText("Enter the TV IP address first.")
            return
        self.settings["device_ip"] = ip
        self.settings["adb_port"] = self.port_edit.value()
        save_settings(self.settings)
        self.device_label.setText(f"{ip}:{self.port_edit.value()}")
        self.message.setText("Connecting…")
        self.controller.connect_device(ip, self.port_edit.value())

    def disconnect_device(self) -> None:
        self.message.setText("Disconnecting…")
        self.controller.disconnect_device()

    def send_key(self, name: str) -> None:
        self.controller.key(name)

    def send_text(self) -> None:
        text = self.text_edit.text()
        if not text:
            return
        if self.controller.send_text(text):
            self.message.setText("Sending text…")

    def _busy(self, busy: bool) -> None:
        self.connect_button.setText("Working…" if busy else "Connect")

    def _handle_result(self, result: AdbResult) -> None:
        if result.action == "connect":
            self.connected = result.ok
        elif result.action == "disconnect" and result.ok:
            self.connected = False
        if result.ok:
            if result.action == "text":
                self.text_edit.clear()
            if result.action.startswith("key:"):
                self.message.setText(result.action.removeprefix("key:").replace("_", " ").title())
            elif result.action.startswith("launch:"):
                self.message.setText(f"Launched {result.action.split(':', 1)[1]}")
            else:
                self.message.setText(result.output or f"{result.action.title()} complete.")
        else:
            self.message.setText(result.output)
        self.status_label.setText("● Connected" if self.connected else "● Disconnected")
        self.status_label.setObjectName("statusConnected" if self.connected else "statusDisconnected")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def set_always_on_top(self, enabled: bool) -> None:
        self.top_button.blockSignals(True)
        self.top_button.setChecked(enabled)
        self.top_button.setText("Pinned" if enabled else "Pin")
        self.top_button.blockSignals(False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        if self.isVisible():
            self.show()

    def set_compact(self, compact: bool) -> None:
        self.compact = compact
        for widget in (self.connection_card, self.media_card, self.text_card, self.apps_card):
            widget.setVisible(not compact)
        if compact:
            self.resize(max(330, min(self.width(), 390)), 560)
        else:
            self.resize(max(self.width(), 400), max(self.height(), 720))

    def open_settings(self) -> None:
        SettingsDialog(self).exec()

    def apply_settings(self, settings: dict) -> None:
        self.settings = settings
        self.ip_edit.setText(str(settings.get("device_ip", "")))
        self.port_edit.setValue(int(settings.get("adb_port", 5555)))
        found = find_adb(str(settings.get("adb_path", "")))
        self.controller.set_adb_path(found)
        if found:
            self.settings["adb_path"] = found
        self.set_always_on_top(bool(settings.get("always_on_top")))
        self.set_compact(bool(settings.get("compact_default")))
        self.refresh_apps()
        self._update_adb_notice()
        save_settings(self.settings)

    def eventFilter(self, watched, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress and self.isActiveWindow():
            focus = QApplication.focusWidget()
            if isinstance(focus, (QLineEdit, QSpinBox)):
                return super().eventFilter(watched, event)
            key = event.key()
            mapping = {
                Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down", Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right",
                Qt.Key.Key_Return: "ok", Qt.Key.Key_Enter: "ok", Qt.Key.Key_Escape: "back", Qt.Key.Key_Backspace: "back",
                Qt.Key.Key_H: "home", Qt.Key.Key_Space: "play_pause", Qt.Key.Key_PageUp: "volume_up", Qt.Key.Key_PageDown: "volume_down",
            }
            if key in mapping and not event.isAutoRepeat():
                self.send_key(mapping[key])
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # The event filter handles remote shortcuts while preserving text entry.
        super().keyPressEvent(event)

    def show_remote(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self.quitting = True
        self._save_geometry()
        QApplication.quit()

    def _save_geometry(self) -> None:
        self.settings["window"] = {"x": self.x(), "y": self.y(), "width": self.width(), "height": self.height()}
        self.settings["device_ip"] = self.ip_edit.text().strip()
        self.settings["adb_port"] = self.port_edit.value()
        save_settings(self.settings)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_geometry()
        if self.settings.get("close_to_tray") and self.tray and not self.quitting:
            event.ignore()
            self.hide()
            self.tray.showMessage("Chromecast Desktop Remote", "The remote is still running in the system tray.", QSystemTrayIcon.MessageIcon.Information, 2500)
            return
        self.quitting = True
        event.accept()
        QTimer.singleShot(0, QApplication.quit)
