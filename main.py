#!/usr/bin/env python3
"""
SATURN — Bitcoin Intelligence Terminal
Entry point.

Usage:
    python main.py            # demo mode (DEMO_MODE=1 by default)
    DEMO_MODE=0 python main.py  # connect to real Bitcoin/LN nodes
"""

import sys
import os
import logging

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# ── Qt bootstrap ──────────────────────────────────────────────────────────────
try:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont
    _QT = "PyQt5"
except ImportError:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    _QT = "PySide6"

# DPI awareness (Windows)
if hasattr(Qt, "AA_EnableHighDpiScaling"):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
if hasattr(Qt, "AA_UseHighDpiPixmaps"):
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

from gui.main_window import MainWindow
import config

def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("SATURN")
    app.setApplicationVersion(config.APP_VERSION)
    app.setOrganizationName("SATURN Labs")

    # Default monospace font
    font = QFont("JetBrains Mono", 10)
    font.setStyleHint(QFont.Monospace)
    app.setFont(font)

    window = MainWindow()
    window.show()

    return app.exec_() if _QT == "PyQt5" else app.exec()


if __name__ == "__main__":
    sys.exit(main())
