"""Scenario IO, validation, and reproducible result writing for fishtank."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from .events import EventSchedule, TapWater, event_from_mapping
from .solver import Result, simulate
from .state import Chemistry, Params


@dataclass
class Scenario:
    """Loaded fishtank scenario document."""

    chemistry: Chemistry
    params: Params
    schedule: EventSchedule
    days: float
    dt_output_hours: float
    scenario_id: str
    raw: dict[str, Any]
    source_path: Path | None = None

    def run(self) -> Result:
        """Run this scenario and attach scenario metadata to provenance."""

        result = simulate(
            self.chemistry,
            self.params,
            days=self.days,
            dt_output_hours=self.dt_output_hours,
            schedule=self.schedule,
        )
        result.provenance["scenario"] = {
            "id": self.scenario_id,
            "path": str(self.source_path) if self.source_path else None,
            "sha256": scenario_sha256(self),
        }
        result.provenance["parameter_fingerprint"] = _stable_json_sha(
            {
                "scenario_sha256": result.provenance["scenario"]["sha256"],
                "inputs": result.provenance.get("inputs", {}),
            }
        )
        return result


_CHEMISTRY_ALIASES = {
    "TAN": ("TAN", "tan", "tan_mg_n_l"),
    "NO2": ("NO2", "no2", "no2_mg_n_l"),
    "NO3": ("NO3", "no3", "no3_mg_n_l"),
    "X_AOB": ("X_AOB", "x_aob", "x_aob_mg_l"),
    "X_NOB": ("X_NOB", "x_nob", "x_nob_mg_l"),
    "DO": ("DO", "do", "do_mg_l"),
}

_TAP_ALIASES = {
    "TAN": ("TAN", "tan", "tan_mg_n_l"),
    "NO2": ("NO2", "no2", "no2_mg_n_l"),
    "NO3": ("NO3", "no3", "no3_mg_l", "no3_mg_n_l"),
    "DO": ("DO", "do", "do_mg_l"),
}


def load_scenario(path: str | Path) -> Scenario:
    """Load a YAML/JSON fishtank scenario into typed objects."""

    src = Path(path)
    raw = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("scenario document must be a mapping")
    return scenario_from_mapping(raw, source_path=src)


def scenario_from_mapping(raw: dict[str, Any], *, source_path: Path | None = None) -> Scenario:
    """Build a :class:`Scenario` from an already-loaded mapping."""

    tank = _mapping(raw.get("tank", {}), "tank")
    chemistry_doc = _mapping(raw.get("chemistry", {}), "chemistry")
    run_doc = _mapping(raw.get("run", {}), "run")
    params_doc = _mapping(raw.get("parameters", {}), "parameters")
    tap_doc = _mapping(raw.get("tap_water", {}), "tap_water")

    chemistry = Chemistry(**_alias_values(chemistry_doc, _CHEMISTRY_ALIASES, Chemistry()))

    param_overrides: dict[str, float] = {}
    for key in ("volume_l", "temperature_c", "ph", "DO_sat", "k_a"):
        if key in tank:
            param_overrides[key] = _finite_float(tank[key], f"tank.{key}")
    param_overrides.update(
        {str(key): _finite_float(value, f"parameters.{key}") for key, value in params_doc.items()}
    )
    params = Params().with_overrides(**param_overrides)

    days = _finite_float(run_doc.get("days", 42.0), "run.days")
    dt_output_hours = _finite_float(run_doc.get("dt_output_hours", 6.0), "run.dt_output_hours")
    if days < 0.0:
        raise ValueError("run.days must be non-negative")
    if dt_output_hours <= 0.0:
        raise ValueError("run.dt_output_hours must be greater than zero")
    tap_water = TapWater(**_alias_values(tap_doc, _TAP_ALIASES, TapWater()))
    events_doc = raw.get("events", []) or []
    if not isinstance(events_doc, list):
        raise ValueError("events must be a list")
    events = [event_from_mapping(item, i) for i, item in enumerate(events_doc)]
    schedule = EventSchedule(events=events, tap_water=tap_water, horizon=days)
    return Scenario(
        chemistry=chemistry,
        params=params,
        schedule=schedule,
        days=days,
        dt_output_hours=dt_output_hours,
        scenario_id=str(raw.get("scenario_id", source_path.stem if source_path else "fishtank")),
        raw=raw,
        source_path=source_path,
    )


def validate_scenario(path: str | Path) -> list[str]:
    """Return validation errors for a scenario file; empty means valid."""

    try:
        scenario = load_scenario(path)
        simulate(
            scenario.chemistry,
            scenario.params,
            days=scenario.days,
            dt_output_hours=scenario.dt_output_hours,
            schedule=scenario.schedule,
        )
    except Exception as exc:  # noqa: BLE001 - CLI validation returns messages, not tracebacks
        return [str(exc)]
    return []


def run_scenario(path: str | Path) -> Result:
    """Load and run a scenario file."""

    return load_scenario(path).run()


def write_scenario(scenario: Scenario | dict[str, Any], path: str | Path) -> Path:
    """Write a scenario mapping as YAML."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = scenario.raw if isinstance(scenario, Scenario) else scenario
    out.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return out


def read_observation(path: str | Path) -> pd.DataFrame:
    """Read an observation table used by calibration."""

    src = Path(path)
    if src.suffix.lower() == ".parquet":
        return pd.read_parquet(src)
    return pd.read_csv(src)


def write_result(result: Result, output_dir: str | Path) -> dict[str, Path]:
    """Write timeseries, event log, warnings, and provenance sidecars."""

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "timeseries": out / "timeseries.csv",
        "events_log": out / "events_log.csv",
        "warnings": out / "warnings.json",
        "provenance": out / "provenance.json",
    }
    result.timeseries.to_csv(paths["timeseries"], index=False)
    result.events_log.to_csv(paths["events_log"], index=False)
    paths["warnings"].write_text(
        json.dumps(result.warnings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    provenance = dict(result.provenance)
    provenance["outputs"] = {
        **dict(provenance.get("outputs", {})),
        "files": {
            key: {
                "path": path.name,
                "sha256": _sha256_path(path),
            }
            for key, path in paths.items()
            if key != "provenance"
        },
    }
    paths["provenance"].write_text(
        json.dumps(provenance, indent=2, sort_keys=True, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    result.provenance = provenance
    return paths


def scenario_sha256(scenario: Scenario) -> str:
    """Hash the source file if available, otherwise hash the canonical mapping."""

    if scenario.source_path and scenario.source_path.exists():
        return _sha256_path(scenario.source_path)
    return _stable_json_sha(scenario.raw)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return value


def _alias_values(doc: dict[str, Any], aliases: dict[str, tuple[str, ...]], defaults: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    for target, keys in aliases.items():
        value = _first_present(doc, keys)
        out[target] = getattr(defaults, target) if value is None else _finite_float(value, target)
    return out


def _first_present(doc: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in doc:
            return doc[key]
    return None


def _finite_float(value: Any, label: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric, got {value!r}") from exc
    if not pd.notna(out):
        raise ValueError(f"{label} must be finite, got {value!r}")
    if out in (float("inf"), float("-inf")):
        raise ValueError(f"{label} must be finite, got {value!r}")
    return out


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_json_sha(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "Scenario",
    "load_scenario",
    "read_observation",
    "run_scenario",
    "scenario_from_mapping",
    "scenario_sha256",
    "validate_scenario",
    "write_result",
    "write_scenario",
]
