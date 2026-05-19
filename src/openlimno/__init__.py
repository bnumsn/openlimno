"""OpenLimno: open-source water ecology modeling platform.

See SPEC.md (v0.5 frozen, Approved-for-M0) for the full design contract.
"""

# v2.5.1 (R8-7): hardcode ``__version__`` from the source tree so a
# checkout (``pip install -e .`` or PYTHONPATH=src) never reports the
# stale installed-wheel metadata. The version string here MUST agree
# with ``pyproject.toml``'s ``[project].version``; a pinned test
# (``tests/unit/test_version_consistency.py``) enforces that.
__version__ = "3.3.0"

__all__ = ["__version__"]
