"""OpenLimno QGIS Plugin entry point.

QGIS calls ``classFactory(iface)`` to instantiate the plugin.
"""

from __future__ import annotations


def classFactory(iface):  # noqa: N802 (QGIS API)
    from .plugin import OpenLimnoPlugin

    return OpenLimnoPlugin(iface)
