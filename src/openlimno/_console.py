"""Console/stdio hardening shared by every OpenLimno command-line entry point.

Teaching-lab and CI machines run consoles whose codec is narrower than UTF-8 —
a Chinese GBK console (code page 936), or Windows cp1252, or any environment
where ``PYTHONIOENCODING`` names a limited codec. rich encodes with that codec
directly and raises ``UnicodeEncodeError`` the moment a message carries a glyph
the codec lacks: the ``✓`` in ``openlimno validate``, an em-dash in a warning, a
BOM echoed back from a malformed scenario.

``harden_stdio()`` makes such a glyph degrade to a placeholder instead of
aborting the command.

This lived at module scope in ``openlimno.fishtank.cli`` until v3.6.1-post,
where it protected the whole ``openlimno`` CLI only by accident: ``cli.py``
imported the fishtank command eagerly, so the side effect ran for every
subcommand. When that import became lazy (to drop ~750 ms of scipy/pandas from
every invocation), the protection silently vanished from every non-fishtank
command and Windows CI broke on ``console.print("[green]✓[/] …")``.

Hardening stdio is a property of *being a CLI*, not of being the fishtank CLI,
so it belongs here where each entry point asks for it explicitly.
"""

from __future__ import annotations

import sys

from rich.console import Console

__all__ = ["harden_stdio", "make_console"]


def harden_stdio() -> None:
    """Set ``errors="replace"`` on stdout/stderr where the stream allows it.

    Safe to call more than once, and a no-op on streams that cannot be
    reconfigured (a pytest capture buffer, a plain pipe wrapper, a stream
    already detached).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError):
            pass


def make_console() -> Console:
    """Harden stdio, then build a rich Console that honours the error handler.

    ``legacy_windows=False`` keeps rich off its legacy Windows renderer, which
    writes through a path that ignores the stream's error handler — without it
    the reconfigure above would not actually save us on the console that needs
    it most.
    """
    harden_stdio()
    return Console(legacy_windows=False)
