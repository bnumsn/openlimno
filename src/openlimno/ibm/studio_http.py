"""HTTP server layer for the OpenLimno IBM Studio.

R-IBM-GOD-OBJECT partial split (ADR-0016 cleanup track): extracted
from ``openlimno.ibm.studio`` (3,315 LOC) so the HTTP routing and
serving layer (~148 LOC) lives separately from the business
logic (handlers, scenario runners, GIS bridge, comparison shaping)
and the embedded HTML template (~735 LOC).

The dispatch table in ``_IBMStudioHandler.routes`` maps URL paths to
business handler functions. Those handlers live in ``studio.py`` and
are imported here. ``studio.py`` re-exports ``run_ibm_studio`` from
this module so the existing public API
``from openlimno.ibm.studio import run_ibm_studio`` keeps working.

This is a one-direction extraction — ``studio_http`` imports from
``studio``, never the reverse. The studio.py-side re-export uses a
deferred-import pattern to avoid the circular reference at import
time.

⚠️ This module is part of the R-IBM-STUDIO-CONSOLIDATE dev-only
surface. See ``openlimno/ibm/studio.py`` module banner for the full
context.
"""
from __future__ import annotations

import json
import webbrowser
from collections.abc import Mapping
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar, cast
from urllib.parse import urlparse

from openlimno.ibm.studio import (
    _INDEX_HTML,
    _as_int,
    _json_default,
    _sanitize_for_json,
    compare_instream7_for_studio,
    default_studio_scenario_resolved,
    import_gis_for_studio,
    run_instream7_benchmark_for_studio,
    run_studio_calibration,
    run_studio_ensemble,
    run_studio_scenario,
    validate_studio_payload,
)


class _IBMStudioHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer subclass that carries the output_dir for handlers."""

    output_dir: Path

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        output_dir: Path,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.output_dir = output_dir


class _IBMStudioHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the local browser IBM Studio.

    All routes dispatch to business handlers imported from
    ``openlimno.ibm.studio``.  This handler does NOT contain
    application logic — only HTTP framing and JSON encoding.
    """

    server_version = "OpenLimnoIBMStudio/0.1"
    routes: ClassVar[dict[str, str]] = {
        "/": "index",
        "/index.html": "index",
        "/api/default": "default",
        "/favicon.ico": "favicon",
        "/api/run": "run",
        "/api/validate": "validate",
        "/api/ensemble": "ensemble",
        "/api/calibrate": "calibrate",
        "/api/gis/import": "gis_import",
        "/api/instream7/benchmark": "instream7_benchmark",
        "/api/instream7/compare": "instream7_compare",
    }

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    @property
    def studio_server(self) -> _IBMStudioHTTPServer:
        return cast(_IBMStudioHTTPServer, self.server)

    def _send_bytes(
        self, body: bytes, *, content_type: str, status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        self.send_response(int(status))
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(
        self, payload: Mapping[str, object], *, status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        # Strict JSON: emit ``null`` for NaN / +Inf / -Inf instead of the
        # non-standard ``NaN`` / ``Infinity`` tokens that Python's
        # ``allow_nan=True`` default produces (browsers' ``response.json()``
        # rejects those — 2026-05-26 software-test S2, Codex caught when
        # ``initial_abundance=0`` made ``final_mean_length_mm = NaN``).
        body = json.dumps(
            _sanitize_for_json(payload),
            default=_json_default,
            allow_nan=False,
        ).encode("utf-8")
        self._send_bytes(body, content_type="application/json; charset=utf-8", status=status)

    def _read_json(self) -> Mapping[str, object]:
        length = _as_int(self.headers.get("Content-Length"), 0, min_value=0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, Mapping):
            raise ValueError("request body must be a JSON object")
        return cast(Mapping[str, object], data)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        route = self.routes.get(path)
        if route == "index":
            self._send_bytes(_INDEX_HTML.encode("utf-8"), content_type="text/html; charset=utf-8")
            return
        if route == "default":
            self._send_json(default_studio_scenario_resolved())
            return
        if route == "favicon":
            self._send_bytes(b"", content_type="image/x-icon")
            return
        self._send_json({"ok": False, "error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def do_HEAD(self) -> None:
        path = urlparse(self.path).path
        route = self.routes.get(path)
        if route in {"index", "default", "favicon"}:
            self.send_response(int(HTTPStatus.OK))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_response(int(HTTPStatus.NOT_FOUND))
        self.end_headers()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        route = self.routes.get(path)
        try:
            payload = self._read_json()
            if route == "run":
                self._send_json(run_studio_scenario(payload, self.studio_server.output_dir))
                return
            if route == "validate":
                self._send_json(validate_studio_payload(payload, self.studio_server.output_dir))
                return
            if route == "ensemble":
                self._send_json(run_studio_ensemble(payload, self.studio_server.output_dir))
                return
            if route == "calibrate":
                self._send_json(run_studio_calibration(payload, self.studio_server.output_dir))
                return
            if route == "gis_import":
                self._send_json(import_gis_for_studio(payload))
                return
            if route == "instream7_benchmark":
                self._send_json(
                    run_instream7_benchmark_for_studio(payload, self.studio_server.output_dir)
                )
                return
            if route == "instream7_compare":
                self._send_json(
                    compare_instream7_for_studio(payload, self.studio_server.output_dir)
                )
                return
            self._send_json({"ok": False, "error": "not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:  # pragma: no cover - exercised through browser/server smoke
            # Surface a user-readable error category instead of the raw
            # Python exception class name so a stack-trace-shaped leak
            # (e.g. ``JSONDecodeError: Expecting property name…``) can't
            # ship to the browser body (2026-05-26 pass-2 N5', Codex).
            self._send_json(
                {"ok": False, "error": _user_error_message(exc)},
                status=HTTPStatus.BAD_REQUEST,
            )


def _user_error_message(exc: BaseException) -> str:
    """Map a Python exception to a user-friendly error string for the
    Studio's 400 responses, without leaking the exception class name.
    Order matters: ``JSONDecodeError`` is a ``ValueError`` subclass and
    must be matched first.
    """
    text = str(exc) or exc.__class__.__name__
    if isinstance(exc, json.JSONDecodeError):
        return f"request body is not valid JSON: {exc.msg}"
    if isinstance(exc, KeyError):
        return f"missing required field: {text}"
    if isinstance(exc, ValueError):
        return text
    return text


def run_ibm_studio(
    *,
    host: str = "127.0.0.1",
    port: int = 8770,
    output_dir: str | Path = "/tmp/openlimno_ibm_studio",
    open_browser: bool = True,
) -> None:
    """Serve the local browser IBM Studio until interrupted."""

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    server = _IBMStudioHTTPServer((host, port), _IBMStudioHandler, out)
    actual_port = int(server.server_address[1])
    url = f"http://{host}:{actual_port}/"
    print(f"OpenLimno IBM Studio serving {url}", flush=True)
    print(f"Run output directory: {out}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
