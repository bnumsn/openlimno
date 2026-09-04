"""Cross-origin protection for the two local browser Studios.

Both Studios (``openlimno.fishtank.studio_http`` and
``openlimno.ibm.studio_http``) are single-user tools bound to loopback, but
they are still HTTP servers that any page in any other tab can talk to. These
tests pin the three checks that keep an outside page from driving them:

* **Host allowlist** — blocks DNS rebinding, the one attack where the browser
  believes the attacker's page is same-origin with the Studio and can therefore
  *read* the responses.
* **Origin check** — refuses a request that announces a foreign origin, while
  leaving requests with no Origin at all (curl, ``requests``, address-bar
  navigation) working, because that is how the course materials drive the API.
* **JSON Content-Type on POST** — the core regression here. A cross-origin
  ``fetch`` with ``Content-Type: application/json`` triggers a CORS preflight
  and never reaches us; one with ``text/plain`` or a form encoding is a
  "simple request" that skips the preflight entirely. The attacker cannot read
  the reply, but without this check the Studio would still have run the
  simulation — resource abuse on the shared hosts these classes run on.
"""

from __future__ import annotations

import http.client
import importlib
import json
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

JSON_HEADERS = {"Content-Type": "application/json"}


@dataclass(frozen=True)
class StudioServer:
    """A running Studio plus the cheapest request that exercises each verb."""

    name: str
    port: int
    post_path: str
    post_body: bytes
    get_paths: tuple[str, ...]

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        try:
            # http.client only skips its automatic Host header when the caller
            # supplies one, which is exactly how a rebound-DNS request looks.
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def post(self, headers: dict[str, str], body: bytes | None = None) -> tuple[int, bytes]:
        payload = self.post_body if body is None else body
        merged = {"Content-Length": str(len(payload)), **headers}
        return self.request("POST", self.post_path, headers=merged, body=payload)


@pytest.fixture(params=["fishtank", "ibm"])
def studio(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[StudioServer]:
    """Start one Studio on an OS-assigned loopback port for the duration."""

    server: ThreadingHTTPServer
    if request.param == "fishtank":
        from openlimno.fishtank.studio_http import _FishtankStudioHandler, _FishtankStudioServer

        server = _FishtankStudioServer(("127.0.0.1", 0), _FishtankStudioHandler)
        post_path = "/api/run"
        # One output row: enough to prove the request was executed, cheap
        # enough that the guard tests stay fast.
        post_body = json.dumps({"run": {"days": 1.0, "dt_output_hours": 24.0}}).encode("utf-8")
        get_paths = ("/", "/assets/three.module.min.js")
    else:
        from openlimno.ibm.studio_http import _IBMStudioHandler, _IBMStudioHTTPServer

        server = _IBMStudioHTTPServer(("127.0.0.1", 0), _IBMStudioHandler, tmp_path)
        # /api/validate does contract checks only — no simulation to wait on.
        post_path = "/api/validate"
        post_body = b"{}"
        get_paths = ("/", "/api/default")

    studio_server = StudioServer(
        name=str(request.param),
        port=int(server.server_port),
        post_path=post_path,
        post_body=post_body,
        get_paths=get_paths,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield studio_server
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()


# ---------------------------------------------------------------------------
# Regression guard: the ordinary local workflows must keep working
# ---------------------------------------------------------------------------


def test_same_origin_post_succeeds(studio: StudioServer) -> None:
    """The Studio page's own fetch (Origin == this server) is served."""

    status, body = studio.post({**JSON_HEADERS, "Origin": studio.origin})
    assert status == 200, body
    assert isinstance(json.loads(body), dict)


def test_post_without_origin_is_allowed(studio: StudioServer) -> None:
    """``curl -X POST -H 'Content-Type: application/json'`` still works.

    Command-line clients send no Origin header at all; browsers always send one
    on a cross-origin request, so allowing this costs no protection and keeps
    the documented teaching workflow (docs/fishtank/REHEARSAL_LOG) alive.
    """

    status, body = studio.post(JSON_HEADERS)
    assert status == 200, body


def test_json_content_type_with_charset_is_allowed(studio: StudioServer) -> None:
    status, body = studio.post({"Content-Type": "application/json; charset=utf-8"})
    assert status == 200, body


def test_get_from_local_host_succeeds(studio: StudioServer) -> None:
    status, _body = studio.request("GET", studio.get_paths[0])
    assert status == 200


@pytest.mark.parametrize("host_alias", ["127.0.0.1", "localhost", "[::1]"])
def test_local_host_aliases_are_accepted(studio: StudioServer, host_alias: str) -> None:
    """All three loopback spellings address the same server."""

    status, body = studio.post(
        {**JSON_HEADERS, "Host": f"{host_alias}:{studio.port}"},
    )
    assert status == 200, body


# ---------------------------------------------------------------------------
# Host header: DNS-rebinding defence
# ---------------------------------------------------------------------------


def test_rebound_host_header_is_rejected(studio: StudioServer) -> None:
    """A page that pointed its own domain at 127.0.0.1 is refused."""

    status, body = studio.post({**JSON_HEADERS, "Host": f"evil.example:{studio.port}"})
    assert status == 403, body
    message = json.loads(body)["error"]
    assert "Host" in message
    assert "evil.example" in message
    # Self-explanatory: a student who trips this must learn what to do next.
    assert "127.0.0.1" in message
    assert "rebinding" in message.lower()


def test_rebound_host_header_is_rejected_on_get(studio: StudioServer) -> None:
    """Static assets are refused too — the HTML is what bootstraps the API."""

    for path in studio.get_paths:
        status, body = studio.request("GET", path, headers={"Host": "evil.example"})
        assert status == 403, (path, body)
        assert "Refused" in json.loads(body)["error"]


def test_host_header_with_wrong_port_is_rejected(studio: StudioServer) -> None:
    """The allowlist pins the port too, not just the name."""

    status, body = studio.post({**JSON_HEADERS, "Host": f"127.0.0.1:{studio.port + 1}"})
    assert status == 403, body


def test_malformed_host_header_is_rejected(studio: StudioServer) -> None:
    status, body = studio.post({**JSON_HEADERS, "Host": "127.0.0.1:not-a-port"})
    assert status == 403, body


# ---------------------------------------------------------------------------
# Origin header
# ---------------------------------------------------------------------------


def test_foreign_origin_is_rejected(studio: StudioServer) -> None:
    status, body = studio.post({**JSON_HEADERS, "Origin": "http://evil.example"})
    assert status == 403, body
    message = json.loads(body)["error"]
    assert "Origin" in message
    assert "evil.example" in message
    assert "curl" in message


def test_foreign_origin_is_rejected_on_get(studio: StudioServer) -> None:
    status, body = studio.request(
        "GET", studio.get_paths[0], headers={"Origin": "http://evil.example"}
    )
    assert status == 403, body


def test_null_origin_is_rejected(studio: StudioServer) -> None:
    """``Origin: null`` is what a sandboxed iframe / file:// page sends."""

    status, body = studio.post({**JSON_HEADERS, "Origin": "null"})
    assert status == 403, body


def test_origin_on_a_different_port_is_rejected(studio: StudioServer) -> None:
    """A second Studio on the same machine is still a different origin."""

    status, body = studio.post({**JSON_HEADERS, "Origin": f"http://127.0.0.1:{studio.port + 1}"})
    assert status == 403, body


# ---------------------------------------------------------------------------
# Content-Type: the preflight-bypass path (core regression point)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content_type",
    [
        "text/plain",
        "text/plain;charset=UTF-8",
        "application/x-www-form-urlencoded",
        "multipart/form-data; boundary=x",
    ],
)
def test_simple_request_content_types_are_rejected(studio: StudioServer, content_type: str) -> None:
    """The three CORS "simple" media types skip the preflight — refuse them.

    Such a POST carries no Origin restriction the browser will enforce for us,
    so this check is the only thing between an unrelated tab and a simulation
    run on the user's machine.
    """

    status, body = studio.post({"Content-Type": content_type})
    assert status == 415, body
    message = json.loads(body)["error"]
    assert "application/json" in message
    assert "preflight" in message


def test_post_without_content_type_is_rejected(studio: StudioServer) -> None:
    """A bodiless cross-origin POST would otherwise run the defaults."""

    status, body = studio.request("POST", studio.post_path, headers={"Content-Length": "0"})
    assert status == 415, body


def test_content_type_rejection_does_not_run_the_model(studio: StudioServer) -> None:
    """The refusal must come before any work — that is the whole point."""

    status, body = studio.post({"Content-Type": "text/plain"}, body=b'{"run": {"days": 365}}')
    assert status == 415, body
    payload = json.loads(body)
    assert payload["ok"] is False
    assert "summary" not in payload
    assert "checks" not in payload


# ---------------------------------------------------------------------------
# Bind-address policy (module-level, no server needed)
# ---------------------------------------------------------------------------


def _bind_policy(module_name: str) -> Callable[[str], tuple[frozenset[str], bool]]:
    """Return the bind-address policy helper of one Studio module."""

    module = importlib.import_module(f"openlimno.{module_name}.studio_http")
    policy: Callable[[str], tuple[frozenset[str], bool]] = module._bind_policy
    return policy


@pytest.mark.parametrize("module_name", ["fishtank", "ibm"])
def test_loopback_bind_enforces_the_host_allowlist(module_name: str) -> None:
    allowed, enforce = _bind_policy(module_name)("127.0.0.1")
    assert enforce is True
    assert {"127.0.0.1", "localhost", "::1"} <= allowed


@pytest.mark.parametrize("module_name", ["fishtank", "ibm"])
@pytest.mark.parametrize("bind_host", ["0.0.0.0", "::", ""])
def test_wildcard_bind_relaxes_the_host_allowlist(module_name: str, bind_host: str) -> None:
    """A wildcard bind cannot enumerate the names clients will use.

    The operator asked for remote exposure explicitly (``--host``); we cannot
    express an allowlist for it, so the Host check stands down and Origin is
    validated against the request's own Host instead. ``run_*_studio`` prints a
    warning saying exactly that.
    """

    _allowed, enforce = _bind_policy(module_name)(bind_host)
    assert enforce is False


@pytest.mark.parametrize("module_name", ["fishtank", "ibm"])
def test_explicit_lan_bind_answers_to_its_own_name(module_name: str) -> None:
    allowed, enforce = _bind_policy(module_name)("192.168.1.5")
    assert enforce is True
    assert "192.168.1.5" in allowed
    assert "evil.example" not in allowed
