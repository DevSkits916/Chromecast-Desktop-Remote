from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QThreadPool, QTimer
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
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .adb import AdbController, AdbResult, KEYCODES, parse_mdns_services
from .config import DEFAULTS, find_adb, save_settings, set_launch_with_windows
from .platform_tools import PlatformToolsTask, SDK_TERMS_URL


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


class AdbSetupDialog(QDialog):
    def __init__(self, parent: "RemoteWindow"):
        super().__init__(parent)
        self.remote = parent
        self._task = None
        self.setWindowTitle("Set up Android Platform Tools")
        self.setMinimumWidth(470)
        root = QVBoxLayout(self)
        title = QLabel("Install managed ADB")
        title.setObjectName("title")
        root.addWidget(title)
        explanation = QLabel(
            "The remote can download Google's official Windows Platform Tools and keep ADB in your local AppData folder. "
            "No separate installation or terminal is required."
        )
        explanation.setWordWrap(True)
        root.addWidget(explanation)
        terms = QLabel(f'<a href="{SDK_TERMS_URL}">Read the Android SDK Terms and Conditions</a>')
        terms.setOpenExternalLinks(True)
        root.addWidget(terms)
        self.accept_terms = QCheckBox("I have read and accept the Android SDK Terms and Conditions")
        self.accept_terms.setChecked(bool(parent.settings.get("adb_terms_accepted")))
        root.addWidget(self.accept_terms)
        privacy = QLabel("The download comes directly from dl.google.com. The app sends no analytics or account data.")
        privacy.setWordWrap(True)
        privacy.setObjectName("muted")
        root.addWidget(privacy)
        self.status = QLabel("Ready to download.")
        self.status.setWordWrap(True)
        self.status.setObjectName("muted")
        root.addWidget(self.status)
        actions = QHBoxLayout()
        actions.addStretch()
        close = button("Close")
        close.clicked.connect(self.reject)
        self.install_button = button("Download and install", name="primary")
        self.install_button.clicked.connect(self._install)
        actions.addWidget(close)
        actions.addWidget(self.install_button)
        root.addLayout(actions)

    def _install(self) -> None:
        if not self.accept_terms.isChecked():
            self.status.setText("Accept the Android SDK terms before downloading Platform Tools.")
            return
        self.remote.settings["adb_terms_accepted"] = True
        save_settings(self.remote.settings)
        self.install_button.setEnabled(False)
        self.status.setText("Downloading and verifying Android Platform Tools…")
        self._task = PlatformToolsTask()
        self._task.signals.finished.connect(self._finished)
        QThreadPool.globalInstance().start(self._task)

    def _finished(self, ok: bool, message: str, adb_path: str) -> None:
        self.status.setText(message)
        self.install_button.setEnabled(not ok)
        if not ok:
            return
        self.remote.settings["adb_path"] = adb_path
        self.remote.controller.set_adb_path(adb_path)
        save_settings(self.remote.settings)
        self.remote._update_adb_notice()
        self.remote.message.setText("Managed ADB is ready. Turn on Wireless debugging, then use Auto-detect.")
        QTimer.singleShot(900, self.remote.connect_with_discovery)


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
        detect = button("Detect pairing port")
        detect.clicked.connect(self._detect)
        pair = button("Pair", name="primary")
        pair.clicked.connect(self._pair)
        actions.addWidget(cancel)
        actions.addWidget(detect)
        actions.addWidget(pair)
        root.addLayout(actions)
        self.remote.controller.result.connect(self._result)

    def _pair(self) -> None:
        if not self.ip.text().strip() or not self.code.text().strip():
            self.status.setText("Enter the TV IP, pairing port, and code shown on the TV.")
            return
        self.status.setText("Pairing…")
        self.remote.controller.pair_device(self.ip.text(), self.port.value(), self.code.text())

    def _detect(self) -> None:
        if not self.remote.controller.available:
            self.status.setText("Set up managed ADB before detecting the pairing port.")
            return
        self.status.setText("Looking for the TV's temporary pairing service…")
        self.remote.controller.discover_devices("discover_pair")

    def _result(self, result: AdbResult) -> None:
        if result.action == "discover_pair":
            if not result.ok:
                self.status.setText(result.output)
                return
            devices = parse_mdns_services(result.output, "_adb-tls-pairing._tcp")
            if not devices:
                self.status.setText("No pairing service found. Keep 'Pair device with pairing code' open on the TV and try again.")
                return
            current_ip = self.ip.text().strip()
            matches = [device for device in devices if device.ip == current_ip]
            selected = matches[0] if matches else devices[0]
            if len(devices) > 1 and not matches:
                labels = [f"{device.ip}:{device.port}  ({device.name})" for device in devices]
                chosen, accepted = QInputDialog.getItem(self, "Choose pairing device", "Discovered pairing services", labels, 0, False)
                if not accepted:
                    self.status.setText("Pairing-port detection canceled.")
                    return
                selected = devices[labels.index(chosen)]
            self.ip.setText(selected.ip)
            self.port.setValue(selected.port)
            self.status.setText(f"Detected pairing port {selected.port}. Enter the code shown on the TV.")
            return
        if result.action != "pair":
            return
        self.status.setText(("Paired successfully. The remote will now detect the connection port." if result.ok else result.output))
        if result.ok:
            self.remote.ip_edit.setText(self.ip.text().strip())
            QTimer.singleShot(700, self.remote.connect_with_discovery)


class SettingsDialog(QDialog):
    def __init__(self, parent: "RemoteWindow"):
        super().__init__(parent)
        self.remote = parent
        self.settings = deepcopy(parent.settings)
        self.setWindowTitle("Settings")
        self.resize(570, 610)
        root = QVBoxLayout(self)
        root.addWidget(self._general_tab())
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
        download = button("Install or repair managed ADB")
        download.clicked.connect(self.remote.open_adb_setup)
        layout.addWidget(download)
        self.auto = QCheckBox("Auto-connect on startup")
        self.auto.setChecked(bool(self.settings["auto_connect"]))
        self.detect = QCheckBox("Auto-detect the current Wireless Debugging port")
        self.detect.setChecked(bool(self.settings.get("auto_detect_port", True)))
        self.top = QCheckBox("Always on top by default")
        self.top.setChecked(bool(self.settings["always_on_top"]))
        self.compact = QCheckBox("Start in compact mode")
        self.compact.setChecked(bool(self.settings["compact_default"]))
        self.startup = QCheckBox("Launch with Windows")
        self.startup.setChecked(bool(self.settings["launch_windows"]))
        self.tray = QCheckBox("Closing the window minimizes to the tray")
        self.tray.setChecked(bool(self.settings["close_to_tray"]))
        for item in (self.auto, self.detect, self.top, self.compact, self.startup, self.tray):
            layout.addWidget(item)
        note = QLabel("Settings are stored only on this PC in your local AppData folder. No cloud service or telemetry is used.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        layout.addStretch()
        return page

    def _browse_adb(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(self, "Choose adb.exe", self.adb.text(), "ADB executable (adb.exe);;All files (*)")
        if chosen:
            self.adb.setText(chosen)

    def _save(self) -> None:
        old_startup = bool(self.remote.settings.get("launch_windows"))
        self.settings.update(
            {
                "device_ip": self.ip.text().strip(),
                "adb_port": self.port.value(),
                "adb_path": self.adb.text().strip(),
                "auto_connect": self.auto.isChecked(),
                "auto_detect_port": self.detect.isChecked(),
                "always_on_top": self.top.isChecked(),
                "compact_default": self.compact.isChecked(),
                "launch_windows": self.startup.isChecked(),
                "close_to_tray": self.tray.isChecked(),
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
        answer = QMessageBox.question(self, "Reset configuration", "Reset all settings to their defaults?")
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
        self._setup_dialog = None
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
        if self.controller.available and settings.get("auto_connect"):
            QTimer.singleShot(700, self.connect_with_discovery)
        elif not self.controller.available:
            QTimer.singleShot(800, self.prompt_adb_setup)

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
        mode = button("Compact", "Toggle compact remote")
        mode.clicked.connect(lambda: self.set_compact(not self.compact))
        settings_button = button("⚙", "Settings", "round")
        settings_button.clicked.connect(self.open_settings)
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
        self.connect_button.clicked.connect(self.connect_with_discovery)
        disconnect = button("Disconnect")
        disconnect.clicked.connect(self.disconnect_device)
        action_row.addWidget(self.connect_button)
        action_row.addWidget(disconnect)
        connection_layout.addLayout(action_row)
        setup_row = QHBoxLayout()
        detect = button("Auto-detect port")
        detect.clicked.connect(self.detect_port)
        pair = button("Pair device")
        pair.clicked.connect(lambda: PairDialog(self).exec())
        setup = button("Set up ADB")
        setup.clicked.connect(self.open_adb_setup)
        setup_row.addWidget(detect)
        setup_row.addWidget(pair)
        setup_row.addWidget(setup)
        connection_layout.addLayout(setup_row)
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

        volume = QHBoxLayout()
        for text, name in [("−", "volume_down"), ("Mute", "mute"), ("+", "volume_up")]:
            item = button(text, name.replace("_", " ").title())
            item.clicked.connect(lambda checked=False, key=name: self.send_key(key))
            volume.addWidget(item)
        root.addLayout(volume)

        install_layout = QVBoxLayout()
        install_layout.setContentsMargins(14, 12, 14, 12)
        install_title = QLabel("Sideload APK")
        install_title.setObjectName("muted")
        install_layout.addWidget(install_title)
        install_note = QLabel("Install or update an Android TV app. Only use APKs from sources you trust.")
        install_note.setWordWrap(True)
        install_note.setObjectName("muted")
        install_layout.addWidget(install_note)
        install_row = QHBoxLayout()
        self.apk_path_edit = QLineEdit()
        self.apk_path_edit.setReadOnly(True)
        self.apk_path_edit.setPlaceholderText("Select an .apk file…")
        browse_apk = button("Browse…")
        browse_apk.clicked.connect(self.select_apk)
        self.install_apk_button = button("Install", name="primary")
        self.install_apk_button.clicked.connect(self.install_apk)
        install_row.addWidget(self.apk_path_edit, 1)
        install_row.addWidget(browse_apk)
        install_row.addWidget(self.install_apk_button)
        install_layout.addLayout(install_row)
        self.install_card = card(install_layout)
        root.addWidget(self.install_card)

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
        connect.triggered.connect(self.connect_with_discovery)
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
            managed = "platform-tools" in Path(self.controller.adb_path).parts
            self.adb_notice.setText("Managed ADB ready — ports can be detected automatically." if managed else f"ADB ready: {self.controller.adb_path}")
        else:
            self.adb_notice.setText("ADB is not ready. Choose Set up ADB for automatic installation from Google.")

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

    def connect_with_discovery(self) -> None:
        if not self.controller.available:
            self.message.setText("Set up managed ADB before connecting.")
            self.open_adb_setup()
            return
        if self.settings.get("auto_detect_port", True):
            self.message.setText("Looking for Google TV devices and their current ports…")
            self.controller.discover_devices("discover_connect")
        else:
            self.connect_device()

    def detect_port(self) -> None:
        if not self.controller.available:
            self.message.setText("Set up managed ADB before detecting devices.")
            self.open_adb_setup()
            return
        self.message.setText("Scanning the local network for Wireless Debugging…")
        self.controller.discover_devices("discover")

    def _handle_discovery(self, result: AdbResult, connect_after: bool) -> None:
        if not result.ok:
            self.message.setText(result.output)
            return
        devices = parse_mdns_services(result.output)
        if not devices:
            if connect_after and self.ip_edit.text().strip():
                self.message.setText("No advertised port was found; trying the saved address and port…")
                self.connect_device()
            else:
                self.message.setText("No Google TV Wireless Debugging service was found. Confirm it is enabled and both devices use the same network.")
            return
        saved_ip = self.ip_edit.text().strip()
        matches = [device for device in devices if device.ip == saved_ip]
        selected = matches[0] if matches else devices[0]
        if len(devices) > 1 and not matches:
            labels = [f"{device.ip}:{device.port}  ({device.name})" for device in devices]
            chosen, accepted = QInputDialog.getItem(self, "Choose Google TV", "Discovered devices", labels, 0, False)
            if not accepted:
                self.message.setText("Port detection canceled.")
                return
            selected = devices[labels.index(chosen)]
        self.ip_edit.setText(selected.ip)
        self.port_edit.setValue(selected.port)
        self.settings["device_ip"] = selected.ip
        self.settings["adb_port"] = selected.port
        save_settings(self.settings)
        self.device_label.setText(f"{selected.ip}:{selected.port}")
        if connect_after:
            self.message.setText(f"Detected port {selected.port}; connecting…")
            self.connect_device()
        else:
            self.message.setText(f"Detected {selected.ip}:{selected.port}. Ready to connect.")

    def disconnect_device(self) -> None:
        self.message.setText("Disconnecting…")
        self.controller.disconnect_device()

    def send_key(self, name: str) -> None:
        self.controller.key(name)

    def select_apk(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(self, "Choose Android APK", "", "Android app package (*.apk)")
        if chosen:
            self.apk_path_edit.setText(chosen)
            self.message.setText(f"Ready to install {Path(chosen).name}.")

    def install_apk(self) -> None:
        if not self.connected:
            self.message.setText("Connect to the TV before installing an APK.")
            return
        path = self.apk_path_edit.text().strip()
        if not path:
            self.message.setText("Choose an APK file first.")
            return
        if self.controller.install_apk(path):
            self.message.setText(f"Installing {Path(path).name}… This can take a few minutes.")

    def _busy(self, busy: bool) -> None:
        self.connect_button.setText("Working…" if busy else "Connect")
        self.install_apk_button.setEnabled(not busy)

    def _handle_result(self, result: AdbResult) -> None:
        if result.action in ("discover", "discover_connect"):
            self._handle_discovery(result, result.action == "discover_connect")
            return
        if result.action == "discover_pair":
            return
        if result.action == "connect":
            self.connected = result.ok
        elif result.action == "disconnect" and result.ok:
            self.connected = False
        if result.ok:
            if result.action.startswith("key:"):
                self.message.setText(result.action.removeprefix("key:").replace("_", " ").title())
            elif result.action.startswith("launch:"):
                self.message.setText(f"Launched {result.action.split(':', 1)[1]}")
            elif result.action.startswith("install:"):
                self.message.setText(f"Installed {result.action.split(':', 1)[1]} successfully.")
            else:
                self.message.setText(result.output or f"{result.action.title()} complete.")
        else:
            self.message.setText(result.output)
        self.status_label.setText("● Connected" if self.connected else "● Disconnected")
        self.status_label.setObjectName("statusConnected" if self.connected else "statusDisconnected")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def set_always_on_top(self, enabled: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        if self.isVisible():
            self.show()

    def set_compact(self, compact: bool) -> None:
        self.compact = compact
        for widget in (self.connection_card, self.install_card):
            widget.setVisible(not compact)
        if compact:
            self.resize(max(330, min(self.width(), 390)), 560)
        else:
            self.resize(max(self.width(), 400), max(self.height(), 720))

    def open_settings(self) -> None:
        SettingsDialog(self).exec()

    def open_adb_setup(self) -> None:
        AdbSetupDialog(self).exec()

    def prompt_adb_setup(self) -> None:
        if self._setup_dialog and self._setup_dialog.isVisible():
            self._setup_dialog.raise_()
            return
        self._setup_dialog = AdbSetupDialog(self)
        self._setup_dialog.show()

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
                Qt.Key.Key_H: "home", Qt.Key.Key_PageUp: "volume_up", Qt.Key.Key_PageDown: "volume_down",
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
