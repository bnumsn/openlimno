"""Native desktop application for the fishtank model (PySide6).

A thin view over the same headless API the browser Studio uses
(:mod:`openlimno.fishtank.studio_http`); all model logic stays in the core.
The browser Studio is kept as a lightweight remote/fallback option.

Run with ``python -m openlimno.fishtank desktop`` or :func:`run`.
"""

from __future__ import annotations

__all__ = ["run"]


def run() -> int:
    """Launch the desktop app. Imported lazily so the package stays importable
    (and unit-testable) on hosts without PySide6 installed."""
    from .app import run as _run

    return _run()
