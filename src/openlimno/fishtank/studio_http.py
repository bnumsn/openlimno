"""Local browser Studio for the fishtank model."""

from __future__ import annotations

import json
import socket
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .agent import simulate_agent_based_model
from .calibration import fit
from .carbonate import diagnostic_ph_trajectory
from .events import Event, EventSchedule, TapWater
from .io import read_observation
from .library import scenario_payload, scenarios
from .solver import Result, simulate
from .state import Chemistry, Params
from .studio_assets import INDEX_HTML

_VENDOR_DIR = Path(__file__).resolve().parent / "vendor"

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
        {"id": name, "label": entry["label"], "description": entry["description"], "payload": entry["payload"]}
        for name, entry in scenarios().items()
    ]


def run_studio_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Run a Studio payload and return JSON-safe result data."""

    chemistry, params, schedule, days, dt_hours = _payload_to_model(payload)
    result = simulate(chemistry, params, days=days, dt_output_hours=dt_hours, schedule=schedule)
    carbonate = _mapping(payload.get("carbonate", {}), "carbonate")
    ph_df = diagnostic_ph_trajectory(
        result,
        initial_alk_meq_l=_float(carbonate.get("initial_alk_meq_l", 1.4), "carbonate.initial_alk_meq_l"),
        dic_mmol_l=_float(carbonate.get("dic_mmol_l", 1.45), "carbonate.dic_mmol_l"),
    )
    return _result_payload(result, ph_df)


def run_agent_based_studio_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the Studio agent-based model payload."""

    return simulate_agent_based_model(payload)


def calibrate_studio_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Calibrate default nitrification rates from the bundled observation log."""

    chemistry, params, _schedule, days, _dt_hours = _payload_to_model(payload)
    obs_path = Path(__file__).resolve().parents[3] / "data" / "aquarium_logs" / "tank_A_fishless.csv"
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


def run_fishtank_studio(
    *,
    host: str = "127.0.0.1",
    port: int = 8768,
    open_browser: bool = True,
) -> None:
    """Serve the local browser Studio until interrupted."""

    server = _FishtankStudioServer((host, port), _FishtankStudioHandler)
    url = f"http://{host}:{server.server_port}/"
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
        except Exception as exc:  # noqa: BLE001 - convert model errors into browser JSON
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        n_bytes = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n_bytes) if n_bytes else b"{}"
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("request body must be a JSON object")
        return data

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
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
) -> tuple[Chemistry, Params, EventSchedule, float, float]:
    tank = _mapping(payload.get("tank", {}), "tank")
    run = _mapping(payload.get("run", {}), "run")
    chemistry_doc = _mapping(payload.get("chemistry", {}), "chemistry")
    params_doc = _mapping(payload.get("parameters", {}), "parameters")
    tap_doc = _mapping(payload.get("tap_water", {}), "tap_water")
    events_doc = payload.get("events", [])
    if not isinstance(events_doc, list):
        raise ValueError("events must be a list")

    chemistry = Chemistry(
        TAN=_float(chemistry_doc.get("TAN", 0.0), "chemistry.TAN"),
        NO2=_float(chemistry_doc.get("NO2", 0.0), "chemistry.NO2"),
        NO3=_float(chemistry_doc.get("NO3", 5.0), "chemistry.NO3"),
        X_AOB=_float(chemistry_doc.get("X_AOB", 0.02), "chemistry.X_AOB"),
        X_NOB=_float(chemistry_doc.get("X_NOB", 0.02), "chemistry.X_NOB"),
        DO=_float(chemistry_doc.get("DO", 7.5), "chemistry.DO"),
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
    days = _float(run.get("days", 42.0), "run.days")
    dt_hours = _float(run.get("dt_output_hours", 6.0), "run.dt_output_hours")
    tap = TapWater(
        TAN=_float(tap_doc.get("TAN", 0.0), "tap_water.TAN"),
        NO2=_float(tap_doc.get("NO2", 0.0), "tap_water.NO2"),
        NO3=_float(tap_doc.get("NO3", 5.0), "tap_water.NO3"),
        DO=_float(tap_doc.get("DO", 8.5), "tap_water.DO"),
    )
    events = [_event_from_payload(item, i) for i, item in enumerate(events_doc)]
    return chemistry, params, EventSchedule(events=events, tap_water=tap, horizon=days), days, dt_hours


def _result_payload(result: Result, ph_df: Any) -> dict[str, Any]:
    df = result.timeseries.round(6)
    ph_records = ph_df[["day", "alk_meq_l", "ph_dynamic"]].round(6).to_dict(orient="records")
    final = df.iloc[-1]
    summary = {
        "final_TAN": float(final["TAN"]),
        "final_NO2": float(final["NO2"]),
        "final_NO3": float(final["NO3"]),
        "min_DO": float(df["DO"].min()),
        "max_NH3_free": float(df["NH3_free"].max()),
        "final_ph_dynamic": float(ph_records[-1]["ph_dynamic"]) if ph_records else float(final["pH"]),
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


def _event_from_payload(value: Any, index: int) -> Event:
    doc = _mapping(value, f"events[{index}]")
    return Event(
        day=_float(doc.get("day", 0.0), f"events[{index}].day"),
        kind=str(doc.get("kind", "")),
        value=_float(doc.get("value", 0.0), f"events[{index}].value"),
        target=str(doc.get("target", "")),
        repeat_days=_float(doc.get("repeat_days", 0.0), f"events[{index}].repeat_days"),
    )


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
