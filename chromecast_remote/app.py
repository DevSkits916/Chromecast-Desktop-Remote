from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from .config import load_settings
from .styles import STYLE
from .ui import RemoteWindow


def main() -> int:
    QCoreApplication.setOrganizationName("LocalTools")
    QCoreApplication.setApplicationName("Chromecast Desktop Remote")
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#111318"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#f4f5f8"))
    app.setPalette(palette)
    window = RemoteWindow(load_settings())
    window.show()
    return app.exec()
