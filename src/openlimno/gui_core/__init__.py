"""OpenLimno GUI core: shared dialog / handler logic for plugin + Studio.

Handlers live on `Controller`, which receives a `Host` adapter exposing
the four QGIS-iface-shaped methods the handlers need (main_window,
map_canvas, message_bar, status_bar). Both the QGIS plugin and
OpenLimno Studio create one Controller per session.

This module is the only place where build/run/click/plot logic lives;
plugin.py and studio/main_window.py are thin UI-toolkit-only wiring.
"""
from openlimno.gui_core.controller import Controller, Host

__all__ = ["Controller", "Host"]
