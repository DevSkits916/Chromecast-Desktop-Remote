from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QListWidget,
    QTabWidget,
    QTextEdit,
    QPlainTextEdit,
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
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .adb import AdbController, AdbResult, KEYCODES, parse_mdns_services, parse_getprop, parse_packages, valid_package
from .config import migrate_settings, new_profile, managed_adb_path, DEFAULTS, find_adb, save_settings, set_launch_with_windows
from .platform_tools import PlatformToolsTask, SDK_TERMS_URL, installed_platform_version
from .connection import ConnectionSession, ConnectionState, match_discovered
from .updates import UpdateTask, RELEASE_URL
from . import __version__


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
        if getattr(self.remote, "_platform_task", None) is not None:
            self.status.setText("A managed ADB installation is already running.")
            return
        self._task = PlatformToolsTask(force=True)
        self.remote._platform_task = self._task
        self._task.signals.finished.connect(self._finished)
        QThreadPool.globalInstance().start(self._task)

    def _finished(self, ok: bool, message: str, adb_path: str) -> None:
        self.remote._platform_task = None
        self.status.setText(message)
        self.install_button.setEnabled(not ok)
        if not ok:
            return
        if self.remote.settings.get("adb_path") and Path(self.remote.settings["adb_path"]).resolve() != managed_adb_path().resolve():
            self.status.setText(message + " External ADB remains selected; choose managed adb.exe in Settings to switch.")
            return
        self.remote.settings["adb_path"] = adb_path
        self.remote.controller.set_adb_path(adb_path)
        save_settings(self.remote.settings)
        self.remote._update_adb_notice()
        self.remote.message.setText("Managed ADB is ready. Turn on Wireless debugging, then use Auto-detect.")
        QTimer.singleShot(900, self.remote.connect_with_discovery)


class HelpDialog(QDialog):
    def __init__(self, parent: "RemoteWindow"):
        super().__init__(parent)
        self.setWindowTitle("Help — Chromecast Remote")
        self.setFixedWidth(470)
        root = QVBoxLayout(self)
        title = QLabel("Connect your TV")
        title.setObjectName("title")
        root.addWidget(title)
        instructions = QLabel(
            "<b>1. Install ADB</b><br>"
            "Choose <b>Set up ADB</b>, read and accept Google's SDK terms, then click "
            "<b>Download and install</b>. You can also select an existing adb.exe in Settings.<br><br>"
            "<b>2. Prepare the TV</b><br>"
            "Connect your PC and TV to the same local network. On the TV, open "
            "<b>Settings → System → About</b> and select <b>Android TV OS build</b> seven times. "
            "Then open <b>Developer options</b> and turn on <b>Wireless debugging</b>. "
            "Menu names may vary by TV.<br><br>"
            "<b>3. Pair the device</b><br>"
            "On the TV, choose <b>Pair device with pairing code</b> and keep that screen open. "
            "In the remote, choose <b>Pair device</b>, then <b>Detect pairing port</b> "
            "(or enter the TV IP and pairing port). Enter the code shown on the TV and click <b>Pair</b>.<br><br>"
            "<b>4. Connect</b><br>"
            "The remote discovers Wireless Debugging devices automatically when it opens. "
            "After pairing it detects the connection port and connects. Use <b>Auto Detect</b> "
            "to scan again, then <b>Connect</b>. The pairing port and connection port are different.<br><br>"
            "If discovery finds nothing, check Wireless debugging and your network, or enter "
            "the address and connection port shown on the TV. Older cast-only Chromecast dongles are not supported."
        )
        instructions.setWordWrap(True)
        root.addWidget(instructions)
        actions = QHBoxLayout()
        setup = button("Set up ADB")
        setup.clicked.connect(parent.open_adb_setup)
        pair = button("Pair device")
        pair.clicked.connect(lambda: PairDialog(parent).exec())
        close = button("Close", name="primary")
        close.clicked.connect(self.close)
        for item in (setup, pair, close):
            actions.addWidget(item)
        root.addLayout(actions)


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
        self.code.setEchoMode(QLineEdit.EchoMode.Password)
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
        self.remote._set_state(ConnectionState.PAIRING)
        try:
            self.remote.controller.pair_device(self.ip.text(), self.port.value(), self.code.text())
        except ValueError as exc:
            self.status.setText(str(exc))
        self.code.clear()

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
            self.remote._adopt_paired_device(self.ip.text().strip())


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
        tabs = QTabWidget()
        pages = {}
        for name in ("General", "Devices", "Remote", "Keyboard", "ADB", "Updates"):
            page = QWidget()
            pages[name] = QVBoxLayout(page)
            tabs.addTab(page, name)
        self.ip = QLineEdit(self.settings["device_ip"])
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(self.settings["adb_port"])
        form = QFormLayout()
        form.addRow("Selected TV address", self.ip)
        form.addRow("Connection port", self.port)
        pages["Devices"].addLayout(form)
        note = QLabel("Use Add, Rename and Remove beside the TV selector in the main window. Auto-connect is saved separately for each TV.")
        note.setWordWrap(True)
        pages["Devices"].addWidget(note)
        self.adb = QLineEdit(self.settings["adb_path"])
        pages["ADB"].addWidget(QLabel("Selected adb.exe"))
        pages["ADB"].addWidget(self.adb)
        browse = button("Browse adb.exe")
        browse.clicked.connect(self._browse_adb)
        pages["ADB"].addWidget(browse)
        download = button("Repair / reinstall managed ADB")
        download.clicked.connect(self.remote.open_adb_setup)
        pages["ADB"].addWidget(download)
        for attr, label, key, category in (
            ("auto", "Auto-connect and recover this TV", "auto_connect", "Devices"),
            ("detect", "Discover current Wireless Debugging port", "auto_detect_port", "Devices"),
            ("top", "Always on top", "always_on_top", "Remote"),
            ("compact", "Start in compact mode", "compact_default", "Remote"),
            ("startup", "Launch with Windows", "launch_windows", "General"),
            ("tray", "Closing minimizes to tray", "close_to_tray", "General"),
            ("help_startup", "Show setup help at startup", "show_setup_help", "General")):
            control = QCheckBox(label)
            control.setChecked(self.settings[key])
            setattr(self, attr, control)
            pages[category].addWidget(control)
        keys = QLabel("Arrows: D-pad; Enter: OK; Escape/Backspace: Back; H: Home\nPage Up/Down: Volume; Space: Play/Pause; M: Mute\nR/F: Rewind/Fast Forward; P/N: Previous/Next\nShortcuts pause while editing text. Global hotkeys are deferred.")
        keys.setWordWrap(True)
        pages["Keyboard"].addWidget(keys)
        update = button(f"Check application update ({__version__})")
        update.clicked.connect(lambda: self.remote._check_update(False))
        pages["Updates"].addWidget(update)
        platform = button("Check official Platform Tools version")
        platform.clicked.connect(lambda: self.remote._check_update(True))
        pages["ADB"].addWidget(platform)
        note = QLabel("Checks run only when clicked. Downloads and application upgrades are never automatic. See Advanced / Device / ADB for results and the release link.")
        note.setWordWrap(True)
        pages["Updates"].addWidget(note)
        for layout in pages.values():
            layout.addStretch()
        return tabs

    def _browse_adb(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(self, "Choose adb.exe", self.adb.text(), "ADB executable (adb.exe);;All files (*)")
        if chosen:
            self.adb.setText(chosen)

    def _save(self) -> None:
        old_startup = bool(self.remote.settings.get("launch_windows"))
        self.settings.update(
            {
                "show_setup_help": self.help_startup.isChecked(),
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
        profile = next((p for p in self.settings["profiles"] if p["id"] == self.settings["selected_profile"]), None)
        if profile:
            profile.update(ip=self.ip.text().strip(), port=self.port.value(), auto_connect=self.auto.isChecked())
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
        self.settings = settings = migrate_settings(settings)
        self.session = ConnectionSession()
        self.apps_cache = {}
        self._update_tasks = []
        self.controller = AdbController(find_adb(settings.get("adb_path", "")))
        if self.controller.adb_path and not settings.get("adb_path"):
            self.settings["adb_path"] = self.controller.adb_path
        self.connected = False
        self.quitting = False
        self._setup_dialog = None
        self._help_dialog = None
        self.compact = bool(settings.get("compact_default"))
        self.setWindowTitle(f"Chromecast Desktop Remote {__version__}")
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
        self.setAcceptDrops(True)
        self.heartbeat = QTimer(self)
        self.heartbeat.setInterval(15000)
        self.heartbeat.timeout.connect(self._heartbeat)
        self.heartbeat.start()
        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.setSingleShot(True)
        self.reconnect_timer.timeout.connect(self._reconnect)
        QTimer.singleShot(300, self._startup_help)
        QTimer.singleShot(700, self._startup_discovery)

    def _startup_discovery(self) -> None:
        if self.quitting or not self.controller.available:
            return
        if self.settings.get("auto_connect"):
            self.connect_with_discovery()
        else:
            self.detect_port()

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
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("statusDisconnected")
        saved_ip = str(self.settings.get("device_ip", "")).strip()
        saved_port = int(self.settings.get("adb_port", 5555))
        self.device_label = QLabel(f"{saved_ip}:{saved_port}" if saved_ip else "No TV selected")
        self.device_label.setWordWrap(True)
        self.device_label.setTextFormat(Qt.TextFormat.PlainText)
        self.device_label.setObjectName("muted")
        status_col.addWidget(self.status_label)
        status_col.addWidget(self.device_label)
        root.addLayout(status_col)
        header.addStretch()
        mode = button("Compact", "Toggle compact remote")
        mode.clicked.connect(lambda: self.set_compact(not self.compact))
        settings_button = button("⚙", "Settings", "round")
        settings_button.clicked.connect(self.open_settings)
        header.addWidget(mode)
        help_button = button("Help", "ADB installation and device pairing instructions")
        help_button.clicked.connect(self.open_help)
        header.addWidget(help_button)
        header.addWidget(settings_button)
        root.addLayout(header)

        profile_row = QHBoxLayout()
        self.profile_selector = QComboBox()
        self.profile_selector.setAccessibleName("TV device profile")
        self.profile_selector.currentIndexChanged.connect(self._select_profile)
        profile_layout = QVBoxLayout()
        profile_layout.addWidget(self.profile_selector)
        for label, callback in (("Add", self._add_profile), ("Rename", self._rename_profile), ("Remove", self._remove_profile)):
            control = button(label)
            control.clicked.connect(callback)
            profile_row.addWidget(control)
        self.profile_bar = QWidget()
        profile_layout.addLayout(profile_row)
        self.profile_bar.setLayout(profile_layout)
        root.addWidget(self.profile_bar)
        self._refresh_profiles()
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
        detect = button("Auto Detect")
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
        self.connection_toggle = button("Connection setup")
        self.connection_toggle.setCheckable(True)
        self.connection_toggle.setChecked(not bool(self.settings['profiles']))
        self.connection_toggle.toggled.connect(lambda enabled: self.connection_card.setVisible(enabled and not self.compact))
        root.addWidget(self.connection_toggle)
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
            self._bind_control(item, name)
            item.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            nav_grid.addWidget(item, row, col)
        nav_grid.setColumnStretch(0, 1)
        nav_grid.setColumnStretch(1, 1)
        nav_grid.setColumnStretch(2, 1)
        root.addLayout(nav_grid, 1)

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
            self._bind_control(item, name)
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
        self.more_button = button("Advanced")
        self.more_button.setCheckable(True)
        self.more_button.toggled.connect(self._toggle_advanced)
        root.addWidget(self.more_button)
        self.advanced = QTabWidget()
        self.advanced.addTab(self._media_page(), "Media")
        self.advanced.addTab(self._text_page(), "Text")
        self.advanced.addTab(self._apps_page(), "Apps")
        self.advanced.addTab(self.install_card, "APK")
        self.advanced.addTab(self._info_page(), "Device / ADB")
        self.advanced.hide()
        root.addWidget(self.advanced)

        self.message = QLabel("Ready")
        self.message.setTextFormat(Qt.TextFormat.PlainText)
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
            self._set_state(ConnectionState.ADB_MISSING)
            self.adb_notice.setText("ADB is not ready. Choose Set up ADB for automatic installation from Google.")

    def connect_device(self) -> None:
        ip = self.ip_edit.text().strip()
        if not ip:
            self.message.setText("Enter the TV IP address first.")
            return
        self.settings["device_ip"] = ip
        self.settings["adb_port"] = self.port_edit.value()
        self._save_profile()
        save_settings(self.settings)
        self._set_state(ConnectionState.CONNECTING)
        self.device_label.setText(f"{ip}:{self.port_edit.value()}")
        self.message.setText("Connecting…")
        try:
            self.controller.connect_device(ip, self.port_edit.value())
        except ValueError as exc:
            self._set_state(ConnectionState.ERROR)
            self.message.setText(str(exc))

    def connect_with_discovery(self) -> None:
        self.session.start()
        self._set_state(ConnectionState.SEARCHING)
        self.reconnect_timer.stop()
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
        self._set_state(ConnectionState.SEARCHING)
        self.message.setText("Scanning the local network for Wireless Debugging…")
        self.controller.discover_devices("discover")

    def _handle_discovery(self, result: AdbResult, connect_after: bool) -> None:
        if not result.ok:
            self.message.setText(result.output)
            if connect_after:
                self._connection_failed(result.output)
            return
        devices = parse_mdns_services(result.output)
        if not devices:
            if connect_after and self.ip_edit.text().strip():
                self.message.setText("No advertised port was found; trying the saved address and port…")
                self.connect_device()
            else:
                self.message.setText("No Google TV Wireless Debugging service was found. Confirm it is enabled and both devices use the same network.")
            return
        profile = self._profile()
        selected = match_discovered(devices, profile)
        if profile and not selected and (profile["ip"] or profile["service_name"]):
            self.message.setText("Saved TV is not advertised. Keeping its address; other TVs will not be selected.")
            if connect_after:
                self.connect_device()
            return
        if not selected and len(devices) == 1:
            selected = devices[0]
        if not selected:
            labels = [f"{device.ip}:{device.port}  ({device.name})" for device in devices]
            chosen, accepted = QInputDialog.getItem(self, "Choose Google TV", "Discovered devices", labels, 0, False)
            if not accepted:
                self.message.setText("Port detection canceled.")
                return
            selected = devices[labels.index(chosen)]
        if not profile:
            profile = new_profile(selected.name, selected.ip, selected.port)
            self.settings["profiles"].append(profile)
            self.settings["selected_profile"] = profile["id"]
            self._refresh_profiles()
        profile["service_name"] = selected.name
        self._set_state(ConnectionState.DEVICE_FOUND)
        self.ip_edit.setText(selected.ip)
        self.port_edit.setValue(selected.port)
        self.settings["device_ip"] = selected.ip
        self.settings["adb_port"] = selected.port
        self._save_profile()
        save_settings(self.settings)
        self.device_label.setText(f"{selected.ip}:{selected.port}")
        if connect_after:
            self.message.setText(f"Detected port {selected.port}; connecting…")
            self.connect_device()
        else:
            self.message.setText(f"Detected {selected.ip}:{selected.port}. Ready to connect.")

    def disconnect_device(self) -> None:
        self.session.disconnect()
        self.reconnect_timer.stop()
        serial = self.controller.serial
        self.controller.invalidate()
        self.controller.serial = serial
        self.connected = False
        self._set_state(ConnectionState.OFFLINE)
        self.message.setText("Disconnecting…")
        self.controller.disconnect_device()
        self.controller.serial = ""

    def send_key(self, name: str) -> None:
        if self.connected:
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
        if any(action.startswith("install") for generation, action in self.controller._pending):
            return
        self.message.setText(f"Preparing APK: {Path(path).name}")
        if self.controller.install_apk(path):
            self.message.setText(f"Installing {Path(path).name}… This can take a few minutes.")

    def _busy(self, busy: bool) -> None:
        self.connect_button.setText("Working…" if busy else "Connect")
        self.install_apk_button.setEnabled(not busy)

    def _handle_result(self, result: AdbResult) -> None:
        if result.generation >= 0 and result.generation != self.controller.generation:
            return
        if result.action == "heartbeat":
            if not result.ok or result.output.strip() != "device":
                self._connection_failed(result.output)
            return
        if result.action == "info":
            if result.ok:
                profile = self._profile()
                if profile:
                    profile.update(parse_getprop(result.output))
                    save_settings(self.settings)
                self._show_info()
            else:
                self.message.setText(result.output)
            return
        if result.action in ("apps", "apps_system"):
            if result.ok:
                cache = self.apps_cache.setdefault(self.settings["selected_profile"], {})
                cache["system" if result.action == "apps_system" else "packages"] = parse_packages(result.output)
                self._filter_apps()
            else:
                self.message.setText(result.output)
            return
        if result.action in ("package_info", "adb_version"):
            self.info_label.setPlainText(result.output)
            return
        if result.action == "pair":
            self._set_state(ConnectionState.DEVICE_FOUND if result.ok else ConnectionState.PAIRING_REQUIRED)
        if result.action in ("discover", "discover_connect"):
            if self.session.paused and result.action == "discover_connect":
                return
            self._handle_discovery(result, result.action == "discover_connect")
            return
        if result.action == "discover_pair":
            return
        if result.action == "connect" and result.ok:
            self.controller.execute(self.controller.target_args(['get-state']), 'verify_connection', 5)
            return
        if result.action == "connect" or result.action == "verify_connection":
            if result.action == "verify_connection" and result.output.strip() != "device":
                result.ok = False
            self.connected = result.ok
            if result.ok:
                from datetime import datetime, timezone
                self.session.connected()
                self.reconnect_timer.stop()
                self.settings["setup_completed"] = True
                self._save_profile()
                profile = self._profile()
                if profile:
                    profile["last_connected"] = datetime.now(timezone.utc).isoformat()
                save_settings(self.settings)
                self._set_state(ConnectionState.CONNECTED)
                self.connection_toggle.setChecked(False)
                self.controller.execute(self.controller.target_args(["shell", "getprop"]), "info")
            else:
                self._connection_failed(result.output)
        elif result.action == "disconnect" and result.ok:
            self.connected = False
        if result.action == "old_disconnect":
            return
        if result.ok:
            if result.action == "uninstall":
                self._refresh_apps()
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
        self._set_state(ConnectionState.CONNECTED if self.connected else self.session.state)
        self.status_label.setObjectName("statusConnected" if self.connected else "statusDisconnected")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def set_always_on_top(self, enabled: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        if self.isVisible():
            self.show()

    def set_compact(self, compact: bool) -> None:
        self.compact = compact
        for widget in (self.profile_bar, self.more_button, self.connection_toggle):
            widget.setVisible(not compact)
        self.connection_card.setVisible(not compact and self.connection_toggle.isChecked())
        self.advanced.setVisible(not compact and self.more_button.isChecked())
        self.settings["compact_default"] = compact
        if compact:
            self.resize(max(330, min(self.width(), 390)), 560)
        else:
            self.resize(max(self.width(), 400), max(self.height(), 720))

    def open_settings(self) -> None:
        SettingsDialog(self).exec()

    def open_help(self) -> None:
        if self.quitting:
            return
        if self._help_dialog is None:
            self._help_dialog = HelpDialog(self)
        self._help_dialog.show()
        self._help_dialog.raise_()
        self._help_dialog.activateWindow()

    def open_adb_setup(self) -> None:
        AdbSetupDialog(self).exec()

    def prompt_adb_setup(self) -> None:
        if self._setup_dialog and self._setup_dialog.isVisible():
            self._setup_dialog.raise_()
            return
        self._setup_dialog = AdbSetupDialog(self)
        self._setup_dialog.show()

    def apply_settings(self, settings: dict) -> None:
        self.controller.invalidate()
        self.connected = False
        self.session.disconnect()
        self.reconnect_timer.stop()
        self.settings = settings = migrate_settings(settings)
        self._refresh_profiles()
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
            if isinstance(focus, (QLineEdit, QSpinBox, QTextEdit, QPlainTextEdit, QComboBox)) or QApplication.activeModalWidget():
                return super().eventFilter(watched, event)
            key = event.key()
            mapping = {
                Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down", Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right",
                Qt.Key.Key_Return: "ok", Qt.Key.Key_Enter: "ok", Qt.Key.Key_Escape: "back", Qt.Key.Key_Backspace: "back",
                Qt.Key.Key_Space: "play_pause", Qt.Key.Key_M: "mute",
                Qt.Key.Key_R: "rewind", Qt.Key.Key_F: "fast_forward",
                Qt.Key.Key_N: "next", Qt.Key.Key_P: "previous",
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
        self.session.disconnect()
        self.heartbeat.stop()
        self.reconnect_timer.stop()
        self.controller.invalidate()
        QApplication.quit()

    def _save_geometry(self) -> None:
        self.settings["window"] = {"x": self.x(), "y": self.y(), "width": self.width(), "height": self.height()}
        self.settings["device_ip"] = self.ip_edit.text().strip()
        self.settings["adb_port"] = self.port_edit.value()
        self._save_profile()
        save_settings(self.settings)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_geometry()
        if self.settings.get("close_to_tray") and self.tray and not self.quitting:
            event.ignore()
            self.hide()
            self.tray.showMessage("Chromecast Desktop Remote", "The remote is still running in the system tray.", QSystemTrayIcon.MessageIcon.Information, 2500)
            return
        self.quitting = True
        self.controller.invalidate()
        self.heartbeat.stop()
        self.reconnect_timer.stop()
        event.accept()
        QTimer.singleShot(0, QApplication.quit)

    def _adopt_paired_device(self, ip):
        self._save_profile()
        profile = next((p for p in self.settings['profiles'] if p['ip'] == ip), None)
        if profile is None:
            profile = new_profile('Paired TV', ip)
            self.settings['profiles'].append(profile)
        self._refresh_profiles()
        index = self.profile_selector.findData(profile['id'])
        if self.profile_selector.currentIndex() == index:
            self.connect_with_discovery()
        else:
            self.profile_selector.setCurrentIndex(index)
            if not profile['auto_connect']:
                self.connect_with_discovery()

    def _profile(self):
        return next((p for p in self.settings['profiles'] if p['id'] == self.settings['selected_profile']), None)

    def _save_profile(self):
        profile = self._profile()
        if not profile and self.ip_edit.text().strip():
            profile = new_profile('My TV', self.ip_edit.text().strip(), self.port_edit.value(), self.settings['auto_connect'])
            self.settings['profiles'].append(profile)
            self.settings['selected_profile'] = profile['id']
            self._refresh_profiles()
        if profile:
            profile.update(ip=self.ip_edit.text().strip(), port=self.port_edit.value(), auto_connect=self.settings['auto_connect'])

    def _refresh_profiles(self):
        self.profile_selector.blockSignals(True)
        self.profile_selector.clear()
        for profile in self.settings['profiles']:
            self.profile_selector.addItem(profile['name'], profile['id'])
        self.profile_selector.setCurrentIndex(self.profile_selector.findData(self.settings['selected_profile']))
        self.profile_selector.blockSignals(False)

    def _select_profile(self, index):
        if index < 0:
            return
        if hasattr(self, 'ip_edit'):
            self._save_profile()
        old_serial = self.controller.serial
        self.controller.invalidate()
        if old_serial:
            self.controller.execute(['disconnect', old_serial], 'old_disconnect')
        self.connected = False
        self.session.disconnect()
        self.reconnect_timer.stop()
        self.settings['selected_profile'] = self.profile_selector.itemData(index)
        profile = self._profile()
        self.settings.update(device_ip=profile['ip'], adb_port=profile['port'], auto_connect=profile['auto_connect'])
        self.ip_edit.setText(profile['ip'])
        self.port_edit.setValue(profile['port'])
        self.device_label.setText(profile['name'])
        self._set_state(ConnectionState.OFFLINE)
        self._filter_apps()
        self._show_info()
        save_settings(self.settings)
        if profile['auto_connect']:
            self.connect_with_discovery()

    def _add_profile(self):
        name, ok = QInputDialog.getText(self, 'Add TV', 'Friendly name')
        if not ok or not name.strip():
            return
        ip, ok = QInputDialog.getText(self, 'Add TV', 'IP address (leave empty to discover)')
        if not ok:
            return
        profile = new_profile(name.strip(), ip.strip())
        self.settings['profiles'].append(profile)
        self._refresh_profiles()
        self.profile_selector.setCurrentIndex(self.profile_selector.findData(profile['id']))

    def _rename_profile(self):
        profile = self._profile()
        if not profile:
            return
        name, ok = QInputDialog.getText(self, 'Rename TV', 'Friendly name', text=profile['name'])
        if ok and name.strip():
            profile['name'] = name.strip()
            self._refresh_profiles()
            save_settings(self.settings)

    def _remove_profile(self):
        profile = self._profile()
        if not profile or QMessageBox.question(self, 'Remove TV', f"Remove {profile['name']} from saved devices?") != QMessageBox.StandardButton.Yes:
            return
        self.disconnect_device()
        self.settings['profiles'].remove(profile)
        self.settings['selected_profile'] = ''
        self.settings['device_ip'] = ''
        self.ip_edit.clear()
        self._refresh_profiles()
        if self.settings['profiles']:
            self._select_profile(0)
        save_settings(self.settings)

    def _startup_help(self):
        if self.settings['show_setup_help'] or not self.settings['setup_completed'] or not self.controller.available or not self.settings['profiles']:
            self.open_help()

    def _set_state(self, state):
        self.session.state = state
        profile = self._profile()
        name = profile['name'] if profile else 'TV'
        labels = {
            ConnectionState.CONNECTED: f'Connected to {name}',
            ConnectionState.SEARCHING: 'Searching for Google TV...',
            ConnectionState.RECONNECTING: 'Connection lost, reconnecting...',
            ConnectionState.PAIRING_REQUIRED: 'TV found, pairing required',
            ConnectionState.ADB_MISSING: 'ADB is missing',
        }
        self.status_label.setText(labels.get(state, state.value.replace('_', ' ').title()))
        self.status_label.setAccessibleName(self.status_label.text())

    def _heartbeat(self):
        if self.connected and not self.session.paused and not self.quitting:
            self.controller.execute(self.controller.target_args(['get-state']), 'heartbeat', 5)

    def _connection_failed(self, output):
        self.connected = False
        delay = self.session.failed(output)
        self._set_state(self.session.state)
        profile = self._profile()
        if not self.session.paused and profile and profile['auto_connect'] and self.session.state != ConnectionState.UNAUTHORIZED:
            self.reconnect_timer.start(delay * 1000)

    def _reconnect(self):
        if self.session.paused or self.quitting:
            return
        if any(action in ('connect', 'discover_connect') for generation, action in self.controller._pending if generation == self.controller.generation):
            self.reconnect_timer.start(5000)
            return
        self._set_state(ConnectionState.RECONNECTING)
        self.controller.discover_devices('discover_connect')

    def _bind_control(self, control, name):
        control.setAccessibleName(name.replace('_', ' ').title())
        if name not in ('up', 'down', 'left', 'right', 'volume_up', 'volume_down', 'rewind', 'fast_forward'):
            control.clicked.connect(lambda checked=False: self.send_key(name))
            return
        repeat = HoldRepeat(control, lambda: self.send_key(name))
        control.pressed.connect(repeat.start)
        control.released.connect(repeat.stop)
        control._repeat = repeat

    def _toggle_advanced(self, expanded):
        if hasattr(self, 'advanced'):
            self.advanced.setVisible(expanded and not self.compact)

    def _media_page(self):
        page = QWidget()
        layout = QGridLayout(page)
        for i, (label, key) in enumerate((('Play / Pause', 'play_pause'), ('Rewind', 'rewind'), ('Fast Forward', 'fast_forward'), ('Previous', 'previous'), ('Next', 'next'), ('Stop', 'stop'))):
            control = button(label)
            self._bind_control(control, key)
            layout.addWidget(control, i // 2, i % 2)
        return page

    def _text_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText('Text for the focused TV input')
        layout.addWidget(self.text_edit)
        send = button('Send Text')
        send.clicked.connect(self._send_text)
        layout.addWidget(send)
        note = QLabel('Android input text works best with Latin text. Some characters and TV keyboards are unsupported.')
        note.setWordWrap(True)
        layout.addWidget(note)
        return page

    def _send_text(self):
        if not self.connected:
            self.message.setText('Connect to a TV first.')
            return
        try:
            self.controller.send_text(self.text_edit.text())
        except ValueError as exc:
            self.message.setText(str(exc))

    def _apps_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.app_filter = QLineEdit()
        self.app_filter.setPlaceholderText('Search installed packages')
        self.app_filter.textChanged.connect(self._filter_apps)
        layout.addWidget(self.app_filter)
        self.app_list = QListWidget()
        layout.addWidget(self.app_list)
        row = QGridLayout()
        for index, (label, callback) in enumerate((('Refresh', self._refresh_apps), ('Launch', self._launch_app), ('Favorite', self._favorite_app), ('Info', self._package_info), ('Uninstall', self._uninstall_app))):
            control = button(label)
            control.clicked.connect(callback)
            row.addWidget(control, index // 3, index % 3)
        layout.addLayout(row)
        note = QLabel('Package names are shown. Packages without a launcher may not open. System packages cannot be uninstalled here.')
        note.setWordWrap(True)
        layout.addWidget(note)
        return page

    def _refresh_apps(self):
        if not self.connected:
            self.message.setText('Connect to a TV first.')
            return
        self.apps_cache.pop(self.settings['selected_profile'], None)
        self.controller.execute(self.controller.target_args(['shell', 'pm', 'list', 'packages']), 'apps', 30)
        self.controller.execute(self.controller.target_args(['shell', 'pm', 'list', 'packages', '-s']), 'apps_system', 30)

    def _filter_apps(self):
        self.app_list.clear()
        profile = self._profile()
        favorites = profile['favorites'] if profile else []
        cache = self.apps_cache.get(self.settings['selected_profile'], {})
        query = self.app_filter.text().lower()
        for package in sorted(cache.get('packages', []), key=lambda p: (p not in favorites, p)):
            if query in package.lower():
                self.app_list.addItem(('* ' if package in favorites else '') + package)

    def _selected_package(self):
        item = self.app_list.currentItem()
        return item.text().removeprefix('* ') if item else ''

    def _launch_app(self):
        package = self._selected_package()
        if self.connected and valid_package(package):
            self.controller.launch_package(package)

    def _favorite_app(self):
        profile, package = self._profile(), self._selected_package()
        if profile and valid_package(package):
            favorites = profile['favorites']
            favorites.remove(package) if package in favorites else favorites.append(package)
            save_settings(self.settings)
            self._filter_apps()

    def _package_info(self):
        package = self._selected_package()
        if self.connected and valid_package(package):
            self.controller.execute(self.controller.target_args(['shell', 'dumpsys', 'package', package]), 'package_info', 20)
            self.advanced.setCurrentIndex(4)

    def _uninstall_app(self):
        package = self._selected_package()
        cache = self.apps_cache.get(self.settings['selected_profile'], {})
        if not self.connected or not valid_package(package):
            return
        if 'system' not in cache or package in cache['system']:
            self.message.setText('System packages or unverified packages cannot be removed here. Refresh first.')
            return
        if QMessageBox.warning(self, 'Uninstall app', f'Uninstall {package}? This may erase all its local data.', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.controller.execute(self.controller.target_args(['uninstall', package]), 'uninstall', 90)

    def _info_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.info_label = QPlainTextEdit('Connect to query device information.')
        self.info_label.setReadOnly(True)
        self.info_label.setMinimumHeight(160)
        layout.addWidget(self.info_label)
        for label, callback in (('Refresh Device Info', self._refresh_info), ('ADB version', self._adb_version), ('Check Platform Tools update', lambda: self._check_update(True)), ('Repair / reinstall managed ADB', self.open_adb_setup), (f'Check application update ({__version__})', lambda: self._check_update(False))):
            control = button(label)
            control.clicked.connect(callback)
            layout.addWidget(control)
        release = QLabel(f'<a href="{RELEASE_URL}">View Release</a>')
        release.setOpenExternalLinks(True)
        layout.addWidget(release)
        return page

    def _show_info(self):
        profile = self._profile() or {}
        details = [f"{key.replace('_', ' ').title()}: {profile.get(key) or 'Unavailable'}" for key in ('name', 'manufacturer', 'model', 'android_version', 'api_level', 'ip', 'port')]
        managed = Path(self.controller.adb_path).resolve() == managed_adb_path().resolve() if self.controller.adb_path else False
        details += [f'Installed Platform Tools: {installed_platform_version() if managed else "Use ADB version to inspect external tools"}', f'State: {self.session.state.value}', f"ADB: {self.controller.adb_path or 'Missing'}", 'Managed ADB' if managed else 'External ADB']
        self.info_label.setPlainText('\n'.join(details))

    def _refresh_info(self):
        if self.connected:
            self.controller.execute(self.controller.target_args(['shell', 'getprop']), 'info')
        self._show_info()

    def _adb_version(self):
        self.controller.execute(['version'], 'adb_version')

    def _check_update(self, platform=False):
        task = UpdateTask(platform)
        self._update_tasks.append(task)
        task.signals.finished.connect(self._update_checked)
        QThreadPool.globalInstance().start(task)
        self.message.setText('Checking for updates...')

    def _update_checked(self, ok, message):
        self.message.setText(message)

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).suffix.lower() == '.apk':
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).suffix.lower() == '.apk':
            self.apk_path_edit.setText(urls[0].toLocalFile())
            self.message.setText('APK selected. Open Advanced / APK and click Install.')
            event.acceptProposedAction()


class HoldRepeat:
    """One immediate action, 350 ms delay, then 110 ms repeats."""
    def __init__(self, parent, callback):
        self.callback = callback
        self.delay = QTimer(parent)
        self.delay.setSingleShot(True)
        self.delay.setInterval(350)
        self.timer = QTimer(parent)
        self.timer.setInterval(110)
        self.delay.timeout.connect(self._begin)
        self.timer.timeout.connect(callback)
        self.parent = parent
        parent.installEventFilter(RepeatGuard(parent, self))

    def start(self):
        self.stop()
        self.callback()
        self.delay.start()

    def _begin(self):
        if self.parent.isDown() and self.parent.isEnabled():
            self.callback()
            self.timer.start()

    def stop(self):
        self.delay.stop()
        self.timer.stop()


from PySide6.QtCore import QObject


class RepeatGuard(QObject):
    def __init__(self, parent, repeat):
        super().__init__(parent)
        self.repeat = repeat

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Hide, QEvent.Type.WindowDeactivate, QEvent.Type.EnabledChange):
            self.repeat.stop()
        return False
