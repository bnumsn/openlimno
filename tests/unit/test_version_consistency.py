"""v2.5.1 (R8-7): pin ``openlimno.__version__`` to ``pyproject.toml``.

The v1.x package used ``importlib.metadata.version("openlimno")`` to
resolve ``__version__``, which reads from the installed wheel's
metadata — a stale ``0.1.0a10`` was observed during the 8th-pass
review when the source tree was newer than the installed wheel,
poisoning every ``provenance.json`` written from that checkout.

v2.5.1 hardcodes ``__version__`` in ``src/openlimno/__init__.py``.
This test enforces that the source-tree constant agrees with the
canonical version declared in ``pyproject.toml``.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import openlimno


def test_v251_init_version_matches_pyproject():
    """The hardcoded ``openlimno.__version__`` must equal
    ``pyproject.toml``'s ``[project].version``."""
    pyproject_path = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    if not pyproject_path.exists():
        # Test run from an installed-only checkout (no source).
        # ``__version__`` should still be the constant from __init__.py.
        return
    pyproject_data = tomllib.loads(pyproject_path.read_text())
    expected = pyproject_data["project"]["version"]
    assert openlimno.__version__ == expected, (
        f"R8-7 drift: openlimno.__version__={openlimno.__version__!r} "
        f"but pyproject.toml says {expected!r}. Update "
        f"src/openlimno/__init__.py."
    )
