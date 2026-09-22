STYLE = r"""
QWidget { background: #111318; color: #f4f5f8; font-family: "Segoe UI"; font-size: 14px; }
QMainWindow, QDialog { background: #111318; }
QLabel#title { font-size: 20px; font-weight: 700; }
QLabel#muted { color: #9ea5b2; }
QLabel#statusConnected { color: #65d58b; font-weight: 600; }
QLabel#statusDisconnected { color: #ff7a82; font-weight: 600; }
QFrame#card { background: #1a1d24; border: 1px solid #292d37; border-radius: 18px; }
QPushButton { background: #282c35; border: 1px solid #353a46; border-radius: 14px; padding: 10px 14px; font-weight: 600; }
QPushButton:hover { background: #343945; border-color: #535b6b; }
QPushButton:pressed { background: #6774f7; border-color: #8992ff; }
QPushButton:disabled { color: #666c78; background: #20232a; }
QPushButton#primary { background: #6d78f7; border-color: #7f89ff; }
QPushButton#primary:hover { background: #7d87ff; }
QPushButton#round { border-radius: 24px; min-width: 46px; min-height: 46px; padding: 0; font-size: 18px; }
QPushButton#nav { border-radius: 30px; min-width: 58px; min-height: 58px; padding: 0; font-size: 20px; }
QPushButton#ok { background: #e9ebf2; color: #111318; border-radius: 32px; min-width: 62px; min-height: 62px; padding: 0; }
QLineEdit, QSpinBox, QComboBox { background: #20242c; border: 1px solid #353a46; border-radius: 10px; padding: 9px; selection-background-color: #6d78f7; }
QLineEdit:focus, QSpinBox:focus { border-color: #7f89ff; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 19px; height: 19px; }
QTabWidget::pane { border: 0; }
QTabBar::tab { background: #1b1e25; padding: 10px 16px; border-radius: 9px; margin: 2px; }
QTabBar::tab:selected { background: #3a4050; }
QScrollArea { border: 0; }
QListWidget { background: #171a20; border: 1px solid #303540; border-radius: 10px; padding: 5px; }
QToolTip { background: #292d37; color: white; border: 1px solid #4a5060; padding: 5px; }
"""
