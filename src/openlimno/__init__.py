"""OpenLimno: open-source water ecology modeling platform.

See SPEC.md (v0.5 frozen, Approved-for-M0) for the full design contract.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("openlimno")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
