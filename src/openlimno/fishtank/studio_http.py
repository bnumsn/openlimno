"""Local browser Studio for the fishtank model."""

from __future__ import annotations

import json
import math
import socket
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .agent import simulate_agent_based_model
from .calibration import fit
from .carbonate import diagnostic_ph_trajectory
from .events import EventSchedule, TapWater, event_from_mapping
from .io import read_observation
from .library import scenario_payload, scenarios
from .solver import Result, simulate
from .state import Chemistry, Params
from .studio_assets import INDEX_HTML

_VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
_REQUEST_BODY_LIMIT_BYTES = 256 * 1024
_STUDIO_ODE_MAX_DAYS = 365.0
_STUDIO_ABM_MAX_DAYS = 120.0
_STUDIO_MAX_LITERAL_EVENTS = 200
_STUDIO_MAX_EXPANDED_EVENTS = 1000
_STUDIO_MIN_REPEAT_DAYS = 0.25
_STUDIO_MAX_OUTPUT_ROWS = 5000
_STUDIO_MAX_ABM_STEPS = 6500
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

# The Studio opens on the fishless cycle — a coherent scenario with no fish at
# risk. The rest of the typical cases ship in the scenario library (§8) and are
# offered through the preset dropdown / GET /api/scenarios.
DEFAULT_SCENARIO = "fishless_cycle"


def default_studio_payload() -> dict[str, Any]:
    """Return the default browser-state payload (the fishless-cycle preset)."""

    return scenario_payload(DEFAULT_SCENARIO)


def list_studio_scenarios() -> list[dict[str, Any]]:
    """Return the typical-scenario presets for the Studio dropdown."""

    return [
        {
            "id": name,
            "label": entry["label"],
            "label_zh": entry.get("label_zh", entry["label"]),
            "description": entry["description"],
            "description_zh": entry.get("description_zh", entry["description"]),
            "payload": entry["payload"],
        }
        for name, entry in scenarios().items()
    ]


def run_studio_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Run a Studio payload and return JSON-safe result data."""

    payload = _payload_with_defaults(payload)
    chemistry, params, schedule, days, dt_hours = _payload_to_model(
        payload,
        max_days=_STUDIO_ODE_MAX_DAYS,
    )
    result = simulate(chemistry, params, days=days, dt_output_hours=dt_hours, schedule=schedule)
    # The post-hoc diagnostic assumes every NO3 increase is nitrification-driven
    # alkalinity loss. Three things break that assumption — the SAME three
    # diagnostic_ph_trajectory itself warns about — so skip it (and its
    # UserWarning) whenever any holds, rather than show a misleading curve:
    #   couple_ph>0 : the timeseries pH is already the authoritative solved pH;
    #   mu_plant>0  : plant uptake is an NO3 sink the proxy can't see;
    #   k_denit>0   : denitrification voids NO3, breaking the proxy too.
    if params.couple_ph > 0.0 or params.mu_plant > 0.0 or params.k_denit > 0.0:
        ph_df = None
    else:
        carbonate = _mapping(payload.get("carbonate", {}), "carbonate")
        ph_df = diagnostic_ph_trajectory(
            result,
            initial_alk_meq_l=_float(
                carbonate.get("initial_alk_meq_l", 1.4), "carbonate.initial_alk_meq_l"
            ),
            dic_mmol_l=_float(carbonate.get("dic_mmol_l", 1.45), "carbonate.dic_mmol_l"),
        )
    return _result_payload(result, ph_df)


def run_agent_based_studio_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the Studio agent-based model payload."""

    payload = _payload_with_defaults(payload)
    _validate_studio_payload_limits(
        payload,
        max_days=_STUDIO_ABM_MAX_DAYS,
        model_label="agent-based Studio run",
        validate_abm_steps=True,
    )
    return simulate_agent_based_model(payload)


def calibrate_studio_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Calibrate default nitrification rates from the bundled observation log."""

    payload = _payload_with_defaults(payload)
    chemistry, params, _schedule, days, _dt_hours = _payload_to_model(
        payload,
        max_days=_STUDIO_ODE_MAX_DAYS,
    )
    obs_path = (
        Path(__file__).resolve().parents[3] / "data" / "aquarium_logs" / "tank_A_fishless.csv"
    )
    obs = read_observation(obs_path)
    result = fit(
        obs,
        chemistry=chemistry,
        base_params=params,
        fit_names=("mu_AOB", "mu_NOB"),
        bounds=((0.1, 1.5), (0.1, 1.5)),
        days=days,
    )
    return {
        "ok": True,
        "best_params": result.best_params,
        "best_rmse": result.best_rmse,
        "n_evals": result.n_evals,
        "converged": result.converged,
        "message": result.message,
    }


def _port_available(host: str, port: int) -> bool:
    """True if ``port`` can be bound right now (no ``SO_REUSEADDR``, so it gives
    a truthful answer even against an existing Studio that set it)."""

    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
            return True
        except OSError:
            return False


def run_fishtank_studio(
    *,
    host: str = "127.0.0.1",
    port: int = 8768,
    open_browser: bool = True,
) -> None:
    """Serve the local browser Studio until interrupted.

    If ``port`` is already taken — e.g. several students sharing one host over
    RDP, or a previous Studio window left open — fall back to an OS-assigned
    free port so each instance gets its own. We probe first because the server
    sets ``SO_REUSEADDR`` (needed for quick restarts), which on Windows would
    otherwise let a second instance silently bind the same port.
    """

    requested = port
    if port and not _port_available(host, port):
        port = 0  # already in use — let the OS pick a free port
    server = _FishtankStudioServer((host, port), _FishtankStudioHandler)
    if requested and server.server_port != requested:
        print(
            f"OpenLimno Fishtank Studio: port {requested} is busy, using free "
            f"port {server.server_port} instead",
            flush=True,
        )
    url = f"http://{host}:{server.server_port}/"
    if host not in _LOCAL_HOSTS:
        print(
            "Warning: OpenLimno Fishtank Studio is intended for trusted local use; "
            "do not expose it directly to the public internet.",
            flush=True,
        )
    print(f"OpenLimno Fishtank Studio serving {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - manual server path
        pass
    finally:
        server.server_close()


class _FishtankStudioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _FishtankStudioHandler(BaseHTTPRequestHandler):
    server_version = "OpenLimnoFishtankStudio/0.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/index.html"}:
            self._send_html(INDEX_HTML)
            return
        if self.path == "/assets/three.module.min.js":
            self._send_file(_VENDOR_DIR / "three.module.min.js", "text/javascript; charset=utf-8")
            return
        if self.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if self.path == "/api/default":
            self._send_json(default_studio_payload())
            return
        if self.path == "/api/scenarios":
            self._send_json({"default": DEFAULT_SCENARIO, "scenarios": list_studio_scenarios()})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self._read_json()
            if self.path == "/api/run":
                self._send_json(run_studio_payload(payload))
                return
            if self.path == "/api/agents":
                self._send_json(run_agent_based_studio_payload(payload))
                return
            if self.path == "/api/calibrate":
                self._send_json(calibrate_studio_payload(payload))
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except _PayloadTooLargeError as exc:
            self._send_json(
                {"ok": False, "error": str(exc)},
                status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
        except Exception as exc:  # noqa: BLE001 - convert model errors into browser JSON
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            n_bytes = int(raw_length)
        except ValueError as exc:
            raise ValueError(f"Content-Length must be an integer, got {raw_length!r}") from exc
        if n_bytes < 0:
            raise ValueError(f"Content-Length must be non-negative, got {raw_length!r}")
        if n_bytes > _REQUEST_BODY_LIMIT_BYTES:
            raise _PayloadTooLargeError(
                f"request body too large: {n_bytes} bytes (max {_REQUEST_BODY_LIMIT_BYTES} bytes)"
            )
        raw = self.rfile.read(n_bytes) if n_bytes else b"{}"
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("request body must be a JSON object")
        return data

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        # The single-page app IS the HTML (inline JS/CSS). Never let a browser
        # serve a stale cached copy — after a Studio update a normal refresh must
        # pick up the new page, not silently keep dead/old handlers.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _payload_to_model(
    payload: dict[str, Any],
    *,
    max_days: float,
) -> tuple[Chemistry, Params, EventSchedule, float, float]:
    tank = _mapping(payload.get("tank", {}), "tank")
    chemistry_doc = _mapping(payload.get("chemistry", {}), "chemistry")
    params_doc = _mapping(payload.get("parameters", {}), "parameters")
    tap_doc = _mapping(payload.get("tap_water", {}), "tap_water")
    days, dt_hours, events = _validate_studio_payload_limits(
        payload,
        max_days=max_days,
        model_label="ODE Studio run",
    )

    chemistry = Chemistry(
        TAN=_float(chemistry_doc.get("TAN", 0.0), "chemistry.TAN"),
        NO2=_float(chemistry_doc.get("NO2", 0.0), "chemistry.NO2"),
        NO3=_float(chemistry_doc.get("NO3", 5.0), "chemistry.NO3"),
        X_AOB=_float(chemistry_doc.get("X_AOB", 0.02), "chemistry.X_AOB"),
        X_NOB=_float(chemistry_doc.get("X_NOB", 0.02), "chemistry.X_NOB"),
        DO=_float(chemistry_doc.get("DO", 7.5), "chemistry.DO"),
        # Tier-2 initial pools — without these the Studio silently reset
        # planted_tank's B_plant and the coupled-pH presets' DIC/Alk to the
        # defaults, so those presets would not run as designed in the browser.
        B_plant=_float(chemistry_doc.get("B_plant", 0.0), "chemistry.B_plant"),
        DIC=_float(chemistry_doc.get("DIC", 2.0), "chemistry.DIC"),
        Alk=_float(chemistry_doc.get("Alk", 2.0), "chemistry.Alk"),
    )
    # Ingest the full parameter set (matches io.scenario_from_mapping and the
    # ABM) so DO_sat / k_a / kinetic overrides from the scenario reach the ODE.
    param_overrides: dict[str, float] = {}
    for key in ("volume_l", "temperature_c", "ph", "DO_sat", "k_a"):
        if key in tank:
            param_overrides[key] = _float(tank[key], f"tank.{key}")
    for key, value in params_doc.items():
        param_overrides[str(key)] = _float(value, f"parameters.{key}")
    params = Params().with_overrides(**param_overrides)
    tap = TapWater(
        TAN=_float(tap_doc.get("TAN", 0.0), "tap_water.TAN"),
        NO2=_float(tap_doc.get("NO2", 0.0), "tap_water.NO2"),
        NO3=_float(tap_doc.get("NO3", 5.0), "tap_water.NO3"),
        DO=_float(tap_doc.get("DO", 8.5), "tap_water.DO"),
        # Carbonate buffer of the replacement water: under couple_ph a Studio
        # water change must mix tap DIC/Alk, else the browser can't rescue a pH
        # crash with buffered tap (defaults match the tank, so a no-op at Tier-1).
        DIC=_float(tap_doc.get("DIC", 2.0), "tap_water.DIC"),
        Alk=_float(tap_doc.get("Alk", 2.0), "tap_water.Alk"),
    )
    return (
        chemistry,
        params,
        EventSchedule(events=events, tap_water=tap, horizon=days),
        days,
        dt_hours,
    )


def _payload_with_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    """Return ``payload`` overlaid on the Studio default scenario.

    Browser calls send a complete payload, but API users often send small
    partial objects such as ``{"run": {"days": 7}}``. Treat omitted fields as
    the same fishless-cycle defaults that the browser gets from ``/api/default``
    so direct API calls cannot drift onto a different implicit carbonate/tank
    baseline.
    """

    return _deep_merge(default_studio_payload(), payload)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _result_payload(result: Result, ph_df: Any) -> dict[str, Any]:
    df = result.timeseries.round(6)
    # ph_df is None for coupled runs (pH lives in the timeseries instead).
    ph_records = (
        ph_df[["day", "alk_meq_l", "ph_dynamic"]].round(6).to_dict(orient="records")
        if ph_df is not None
        else []
    )
    final = df.iloc[-1]
    summary = {
        "final_TAN": float(final["TAN"]),
        "final_NO2": float(final["NO2"]),
        "final_NO3": float(final["NO3"]),
        "min_DO": float(df["DO"].min()),
        "max_NH3_free": float(df["NH3_free"].max()),
        "final_ph_dynamic": float(ph_records[-1]["ph_dynamic"])
        if ph_records
        else float(final["pH"]),
    }
    return {
        "ok": True,
        "summary": summary,
        "warnings": result.warnings,
        "timeseries": df.to_dict(orient="records"),
        "events_log": result.events_log.round(6).to_dict(orient="records"),
        "ph_diagnostic": ph_records,
        "provenance": result.provenance,
    }


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _float(value: Any, label: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric, got {value!r}") from exc
    if out != out or out in (float("inf"), float("-inf")):
        raise ValueError(f"{label} must be finite, got {value!r}")
    return out


class _PayloadTooLargeError(ValueError):
    """Request exceeds the local Studio API body limit."""


def _validate_studio_payload_limits(
    payload: dict[str, Any],
    *,
    max_days: float,
    model_label: str,
    validate_abm_steps: bool = False,
) -> tuple[float, float, list[Any]]:
    run = _mapping(payload.get("run", {}), "run")
    days = _float(run.get("days", 42.0), "run.days")
    dt_hours = _float(run.get("dt_output_hours", 6.0), "run.dt_output_hours")
    if days < 0.0:
        raise ValueError(f"run.days must be non-negative, got {days!r}")
    if days > max_days:
        raise ValueError(f"run.days must be <= {max_days:g} for {model_label}, got {days!r}")
    if dt_hours <= 0.0:
        raise ValueError(f"run.dt_output_hours must be greater than zero, got {dt_hours!r}")

    output_rows = math.floor(days / (dt_hours / 24.0)) + 2 if days else 1
    if output_rows > _STUDIO_MAX_OUTPUT_ROWS:
        raise ValueError(
            "requested output grid is too large; increase run.dt_output_hours "
            f"or shorten run.days (max {_STUDIO_MAX_OUTPUT_ROWS} rows)"
        )

    events_doc = payload.get("events", []) or []
    if not isinstance(events_doc, list):
        raise ValueError("events must be a list")
    if len(events_doc) > _STUDIO_MAX_LITERAL_EVENTS:
        raise ValueError(f"events must contain at most {_STUDIO_MAX_LITERAL_EVENTS} entries")
    events = [event_from_mapping(item, i) for i, item in enumerate(events_doc)]
    _validate_event_expansion(events, days)

    if validate_abm_steps:
        agents = _mapping(payload.get("agents", {}), "agents")
        default_dt_days = min(0.25, dt_hours / 24.0)
        dt_days = _float(agents.get("dt_days", default_dt_days), "agents.dt_days")
        if dt_days <= 0.0:
            raise ValueError(f"agents.dt_days must be greater than zero, got {dt_days!r}")
        abm_steps = math.floor(days / dt_days) + 2 if days else 1
        if abm_steps > _STUDIO_MAX_ABM_STEPS:
            raise ValueError(
                "agent-based Studio run has too many steps; increase agents.dt_days "
                f"or shorten run.days (max {_STUDIO_MAX_ABM_STEPS} steps)"
            )
    return days, dt_hours, events


def _validate_event_expansion(events: list[Any], days: float) -> None:
    expanded = 0
    for event in events:
        if event.repeat_days > 0.0:
            if event.repeat_days < _STUDIO_MIN_REPEAT_DAYS:
                raise ValueError(
                    f"events repeat_days must be 0 or >= {_STUDIO_MIN_REPEAT_DAYS:g} days "
                    "for Studio runs"
                )
            if event.day < days:
                expanded += max(0, math.ceil((days - event.day) / event.repeat_days))
        else:
            expanded += 1
        if expanded > _STUDIO_MAX_EXPANDED_EVENTS:
            raise ValueError(
                "events expand to too many applications for a Studio run "
                f"(max {_STUDIO_MAX_EXPANDED_EVENTS})"
            )


def find_free_port(host: str = "127.0.0.1") -> int:
    """Return an available local TCP port for smoke tests and demos."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


__all__ = [
    "DEFAULT_SCENARIO",
    "calibrate_studio_payload",
    "default_studio_payload",
    "find_free_port",
    "list_studio_scenarios",
    "run_agent_based_studio_payload",
    "run_fishtank_studio",
    "run_studio_payload",
]
