"""OpenLimno QGIS Plugin entry point.

QGIS calls ``classFactory(iface)`` to instantiate the plugin.
"""

from __future__ import annotations

from typing import Any


def classFactory(iface: Any) -> Any:  # noqa: N802 (QGIS API)
    from .plugin import OpenLimnoPlugin

    return OpenLimnoPlugin(iface)
