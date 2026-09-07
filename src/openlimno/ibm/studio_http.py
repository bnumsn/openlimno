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
from urllib.parse import urlparse, urlsplit

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

# ---------------------------------------------------------------------------
# Cross-origin guard
#
# The IBM Studio is a local single-user dev tool, but it is still an HTTP server
# any web page the user has open can talk to. Three cheap checks close the three
# ways that goes wrong (mirrors openlimno.fishtank.studio_http):
#
#   Host         a page on attacker.example can point its own DNS name at
#                127.0.0.1 ("DNS rebinding"); the browser then treats
#                http://attacker.example:8770/ as same-origin with the attacker
#                and *can read the responses*. Host is the header that still
#                tells the truth, so we only answer to our own names.
#   Origin       a request carrying an unrecognised Origin is refused. A request
#                with no Origin (address-bar navigation, curl) is allowed.
#   Content-Type enforced for POST in ``_read_json``: without it a page can send
#                a CORS "simple request" (text/plain or form-encoded) that skips
#                the preflight, and the Studio would run the scenario anyway.
# ---------------------------------------------------------------------------

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
# Bind addresses meaning "every interface": the set of names a legitimate client
# may use is not enumerable, so the Host allowlist is relaxed for such a run.
_WILDCARD_BIND_HOSTS = frozenset({"", "0.0.0.0", "::"})
_JSON_MEDIA_TYPE = "application/json"
# How much of a refused request's body we are willing to read before closing
# the connection (see ``_drain_request_body``).
_DRAIN_LIMIT_BYTES = 256 * 1024


def _normalize_host(value: str) -> str:
    """Lower-case a host and strip the brackets IPv6 literals are written in."""

    host = value.strip().lower()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host


def _bind_policy(host: str) -> tuple[frozenset[str], bool]:
    """Return ``(allowed_hosts, enforce_host_header)`` for a bind address."""

    bind_host = _normalize_host(host)
    if bind_host in _WILDCARD_BIND_HOSTS:
        return _LOCAL_HOSTS, False
    return _LOCAL_HOSTS | {bind_host}, True


def _parse_authority(value: str | None) -> tuple[str, int] | None:
    """Split a ``host[:port]`` authority (Host header) into ``(host, port)``."""

    if value is None:
        return None
    try:
        parts = urlsplit(f"//{value.strip()}")
        hostname = parts.hostname
        port = parts.port
    except ValueError:  # malformed port, e.g. "evil.com:notaport"
        return None
    if not hostname:
        return None
    return hostname.lower(), 80 if port is None else port


def _parse_origin(value: str) -> tuple[str, int] | None:
    """Split an ``http://host[:port]`` Origin into ``(host, port)``.

    Anything that is not plain ``http`` — including the literal ``null`` sent by
    sandboxed iframes and ``file://`` pages — returns ``None`` and is refused:
    this server speaks http only, so no other scheme can be one of its pages.
    """

    try:
        parts = urlsplit(value.strip())
        hostname = parts.hostname
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "http" or not hostname:
        return None
    return hostname.lower(), 80 if port is None else port


def _shown(value: str | None, limit: int = 120) -> str:
    """Render a header value for an error message without echoing an essay."""

    if value is None:
        return "absent"
    return repr(value[:limit] + "…") if len(value) > limit else repr(value)


def _host_header_error(value: str | None, allowed: frozenset[str], port: int) -> str | None:
    authority = _parse_authority(value)
    if authority is not None and authority[0] in allowed and authority[1] == port:
        return None
    expected = ", ".join(f"{host}:{port}" for host in sorted(allowed))
    return (
        "Refused: this Studio only answers requests addressed to itself. The Host "
        f"header was {_shown(value)}, but this server answers to: {expected}. Open "
        f"the Studio at http://127.0.0.1:{port}/ instead. (The check blocks DNS "
        "rebinding, where an outside web page aims its own domain name at "
        "127.0.0.1 so it can read what your local tools say.)"
    )


def _origin_header_error(
    value: str | None,
    *,
    host_header: str | None,
    allowed: frozenset[str],
    port: int,
    enforce_host: bool,
) -> str | None:
    if value is None or not value.strip():
        # No Origin at all: address-bar navigation, curl, requests. Browsers
        # always send one on a cross-origin fetch, so allowing this costs
        # nothing and keeps command-line use working.
        return None
    origin = _parse_origin(value)
    if enforce_host:
        ok = origin is not None and origin[0] in allowed and origin[1] == port
        expected = ", ".join(f"http://{host}:{port}" for host in sorted(allowed))
    else:
        # Wildcard bind: "our own origin" is whatever this request was addressed
        # to, so require Origin and Host to agree.
        host_authority = _parse_authority(host_header)
        ok = origin is not None and host_authority is not None and origin == host_authority
        expected = f"http://{host_header}" if host_header else f"http://<this host>:{port}"
    if ok:
        return None
    return (
        f"Refused: cross-origin request. The Origin header was {_shown(value)}, which "
        f"is not this Studio ({expected}). Only the Studio page served from this "
        "server may call its API — another site in another tab must not. "
        "Command-line clients (curl, requests) send no Origin and are unaffected."
    )


def _content_type_error(value: str | None, port: int) -> str | None:
    media_type = (value or "").split(";", 1)[0].strip().lower()
    if media_type == _JSON_MEDIA_TYPE:
        return None
    return (
        f"Refused: POST bodies must be JSON. The Content-Type header was {_shown(value)}, "
        f"expected '{_JSON_MEDIA_TYPE}' (a ';charset=utf-8' parameter is fine). Requiring "
        "it is what stops another web page from POSTing runs to this Studio without a "
        "CORS preflight. From a shell, add the header: curl -X POST -H "
        f"'Content-Type: application/json' -d '{{}}' http://127.0.0.1:{port}/api/run"
    )


class _UnsupportedMediaTypeError(ValueError):
    """POST body was not sent as ``application/json``."""


class _IBMStudioHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer subclass that carries the output_dir for handlers."""

    output_dir: Path
    #: Host names this server answers to, and whether the Host header is
    #: enforced at all (it is not for a wildcard bind — see ``_bind_policy``).
    allowed_hosts: frozenset[str]
    enforce_host_header: bool

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        output_dir: Path,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.output_dir = output_dir
        self.allowed_hosts, self.enforce_host_header = _bind_policy(server_address[0])


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

    def _cross_origin_error(self) -> str | None:
        """Return a refusal message if this request is not one of our own."""

        server = self.studio_server
        port = int(server.server_port)
        host_header = self.headers.get("Host")
        if server.enforce_host_header:
            error = _host_header_error(host_header, server.allowed_hosts, port)
            if error is not None:
                return error
        return _origin_header_error(
            self.headers.get("Origin"),
            host_header=host_header,
            allowed=server.allowed_hosts,
            port=port,
            enforce_host=server.enforce_host_header,
        )

    def _drain_request_body(self) -> None:
        """Read and discard the body of a request we are about to refuse.

        Closing a socket that still has unread bytes queued makes the kernel
        send RST, which can wipe out the response we just wrote — the caller
        would see a connection reset instead of the explanation.
        """

        length = _as_int(self.headers.get("Content-Length"), 0, min_value=0)
        if 0 < length <= _DRAIN_LIMIT_BYTES:
            self.rfile.read(length)

    def _reject_cross_origin(self, error: str) -> None:
        self._drain_request_body()
        self._send_json({"ok": False, "error": error}, status=HTTPStatus.FORBIDDEN)

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
        # An empty body is checked too: a bodiless cross-origin POST would
        # otherwise start a default scenario run without a preflight.
        content_type_error = _content_type_error(
            self.headers.get("Content-Type"), int(self.studio_server.server_port)
        )
        if content_type_error is not None:
            self._drain_request_body()  # so the 415 body survives the close
            raise _UnsupportedMediaTypeError(content_type_error)
        length = _as_int(self.headers.get("Content-Length"), 0, min_value=0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, Mapping):
            raise ValueError("request body must be a JSON object")
        return cast(Mapping[str, object], data)

    def do_GET(self) -> None:
        error = self._cross_origin_error()
        if error is not None:
            self._reject_cross_origin(error)
            return
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
        if self._cross_origin_error() is not None:
            # A HEAD response carries no body, so the explanation only reaches
            # the status line; GET the same URL to read why it was refused.
            self.send_response(int(HTTPStatus.FORBIDDEN))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
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
        error = self._cross_origin_error()
        if error is not None:
            self._reject_cross_origin(error)
            return
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
        except _UnsupportedMediaTypeError as exc:
            self._send_json(
                {"ok": False, "error": str(exc)},
                status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            )
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
    if _normalize_host(host) not in _LOCAL_HOSTS:
        # Parity with the fishtank Studio: binding off-localhost is allowed (the
        # operator asked for it with --host) but never silent — this server has
        # no authentication of any kind.
        print(
            "Warning: OpenLimno IBM Studio is intended for trusted local use; do not "
            "expose it directly to the public internet. It has no authentication: "
            f"anyone who can reach {host}:{actual_port} can start runs on this machine.",
            flush=True,
        )
        if not server.enforce_host_header:
            print(
                f"Warning: --host {host} serves every interface, so the Host-header "
                "check that protects against DNS rebinding is relaxed for this run. "
                "Prefer --host 127.0.0.1 unless you really need remote access.",
                flush=True,
            )
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
