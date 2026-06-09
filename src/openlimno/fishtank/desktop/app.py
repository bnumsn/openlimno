"""Desktop app entry point."""

from __future__ import annotations

import sys


def run() -> int:
    """Create the QApplication, show the main window, run the event loop."""
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
