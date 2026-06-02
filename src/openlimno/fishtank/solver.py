"""ODE integration wrapper (SPEC §7 solver.py [core]).

Tier-1: a single ``scipy.integrate.solve_ivp`` call over the run window.
Discrete events (water change etc.) add a stop/apply/restart segment
loop in Hour 3 — kept out of the Tier-1 path so the Hour-2 build is
minimal.
"""

from __future__ import annotations

import hashlib
import json
import platform
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

from openlimno import __version__

from .events import EventSchedule, apply_event
from .processes import derivatives
from .state import STATE_ORDER, Chemistry, Params, nh3_free_fraction


@dataclass
class Result:
    """Simulation output (SPEC §9)."""

    timeseries: pd.DataFrame          # day + state columns + NH3_free + pH
    params: Params
    warnings: list[str]
    events_log: pd.DataFrame          # one row per instantaneous event application
    provenance: dict[str, Any]        # reproducibility fingerprint + run context


# Toxicity thresholds (literature, SPEC §9)
_NH3_FREE_STRESS = 0.05   # mg/L free NH3 → chronic fish stress
_NO2_STRESS = 0.5         # mg-N/L → "brown blood"
_NO3_WC_DUE = 50.0        # mg-N/L → water change due


def _integrate_segment(
    y0: list[float], p: Params, t0: float, t1: float, t_eval: np.ndarray,
) -> np.ndarray:
    """Integrate one event-free segment and return the state at t_eval."""
    sol = solve_ivp(
        derivatives,
        t_span=(t0, t1),
        y0=y0,
        args=(p,),
        method="LSODA",
        max_step=0.25,
        t_eval=t_eval,
        rtol=1e-6,
        atol=1e-9,
    )
    if not sol.success:
        raise RuntimeError(f"solve_ivp failed on [{t0}, {t1}]: {sol.message}")
    return sol.y


def simulate(
    chemistry: Chemistry | None = None,
    params: Params | None = None,
    *,
    days: float = 42.0,
    dt_output_hours: float = 6.0,
    schedule: EventSchedule | None = None,
) -> Result:
    """Integrate the fishtank model.

    Without ``schedule`` this is a single-segment Tier-1 fishless cycle.
    With a ``schedule``, the solver stops at each event day, applies the
    event's instantaneous state/parameter map, and restarts — so water
    changes, dose changes, and feeding take effect mid-run (SPEC §5).

    Returns a Result whose timeseries has one row per output step with
    the six state variables plus the derived NH3_free and (fixed) pH.
    """
    _validate_run_args(days=days, dt_output_hours=dt_output_hours)

    chem = chemistry or Chemistry()
    p = params or Params()
    initial_chem = Chemistry(**vars(chem))
    initial_params = Params(**vars(p))
    event_rows: list[dict[str, Any]] = []

    full_grid = _output_grid(days, dt_output_hours)

    # Expand repeats ONCE so boundaries + per-day lookup are consistent.
    expanded: list = schedule.expand(days) if schedule else []

    def events_on(day: float) -> list:
        same = [e for e in expanded if e.day == day]
        return sorted(same, key=lambda e: e.priority)

    def apply_events_at(day: float, event_chem: Chemistry, event_params: Params) -> tuple[Chemistry, Params]:
        for ev in events_on(day):
            before = Chemistry(**vars(event_chem))
            before_params = event_params
            event_chem, event_params = apply_event(
                event_chem, event_params, ev, schedule.tap_water  # type: ignore[union-attr]
            )
            event_rows.append(
                {
                    "day": float(day),
                    "kind": ev.kind,
                    "target": ev.target,
                    "value": float(ev.value),
                    "repeat_days": float(ev.repeat_days),
                    "priority": ev.priority,
                    "TAN_before": before.TAN,
                    "NO2_before": before.NO2,
                    "NO3_before": before.NO3,
                    "DO_before": before.DO,
                    "TAN_after": event_chem.TAN,
                    "NO2_after": event_chem.NO2,
                    "NO3_after": event_chem.NO3,
                    "DO_after": event_chem.DO,
                    "ammonia_dose_before": before_params.ammonia_dose_mg_n_l_day,
                    "ammonia_dose_after": event_params.ammonia_dose_mg_n_l_day,
                }
            )
        return event_chem, event_params

    boundaries = sorted({e.day for e in expanded if 0.0 < e.day < days})
    seg_edges = [0.0, *boundaries, days]

    # Day-0 events apply to the initial state before any integration
    # (e.g. an ammonia_dose set at day 0). Without this they'd be lost,
    # since segment boundaries are strictly inside (0, days).
    if schedule:
        chem = Chemistry(**vars(chem))
        chem, p = apply_events_at(0.0, chem, p)

    if days == 0.0:
        df = _build_timeseries([0.0], [chem.to_vector()], p)
        warnings = _build_warnings(df)
        events_log = _build_events_log(event_rows)
        provenance = _build_provenance(
            initial_chem=initial_chem,
            initial_params=initial_params,
            final_params=p,
            days=days,
            dt_output_hours=dt_output_hours,
            schedule=schedule,
            timeseries=df,
            events_log=events_log,
            warnings=warnings,
        )
        return Result(
            timeseries=df,
            params=p,
            warnings=warnings,
            events_log=events_log,
            provenance=provenance,
        )

    y = chem.to_vector()
    times: list[float] = []
    states: list[np.ndarray] = []
    n_seg = len(seg_edges) - 1
    for i in range(n_seg):
        t0, t1 = seg_edges[i], seg_edges[i + 1]
        is_last = i == n_seg - 1
        # Always evaluate at BOTH segment edges plus the interior grid
        # points, so the pre-event state at t1 is available to carry
        # across the boundary regardless of whether t1 lands on the
        # output grid (the off-grid corruption fixed here).
        inner = full_grid[(full_grid > t0) & (full_grid < t1)]
        t_eval = np.unique(np.concatenate(([t0], inner, [t1])))
        seg_y = _integrate_segment(y, p, t0, t1, t_eval)
        # Record [t0 .. t1): drop the pre-event boundary row on non-final
        # segments — the post-event t1 row is recorded by the next
        # segment, which starts from the post-event state. Final segment
        # keeps t1 (= days). Each grid point thus appears exactly once,
        # with post-event state at boundaries.
        keep_mask = np.ones(t_eval.size, dtype=bool) if is_last else (t_eval < t1)
        times.extend(t_eval[keep_mask].tolist())
        states.append(seg_y[:, keep_mask])
        # Carry the pre-event state at t1 forward, then apply events.
        y = seg_y[:, -1].tolist()
        if schedule and not is_last:
            chem_end = Chemistry.from_vector(y)
            chem_end, p = apply_events_at(t1, chem_end, p)
            y = chem_end.to_vector()

    arr = np.concatenate(states, axis=1)
    # Events landing exactly on the final day are never segment boundaries
    # (those are strictly inside (0, days)) and the days==0 case already
    # returned above — so apply any final-day events to the last state here,
    # with no risk of double-application. (events_on returns [] when there is
    # no schedule, so the `schedule and` guard just skips the work.)
    if schedule and events_on(days):
        chem_end = Chemistry.from_vector(arr[:, -1].tolist())
        chem_end, p = apply_events_at(days, chem_end, p)
        arr[:, -1] = chem_end.to_vector()

    df = _build_timeseries(times, arr.T.tolist(), p)
    warnings = _build_warnings(df)
    events_log = _build_events_log(event_rows)
    provenance = _build_provenance(
        initial_chem=initial_chem,
        initial_params=initial_params,
        final_params=p,
        days=days,
        dt_output_hours=dt_output_hours,
        schedule=schedule,
        timeseries=df,
        events_log=events_log,
        warnings=warnings,
    )
    return Result(
        timeseries=df,
        params=p,
        warnings=warnings,
        events_log=events_log,
        provenance=provenance,
    )


def _validate_run_args(*, days: float, dt_output_hours: float) -> None:
    if not np.isfinite(days) or days < 0.0:
        raise ValueError(f"days must be finite and non-negative, got {days!r}")
    if not np.isfinite(dt_output_hours) or dt_output_hours <= 0.0:
        raise ValueError(
            f"dt_output_hours must be finite and greater than zero, got {dt_output_hours!r}"
        )


def _output_grid(days: float, dt_output_hours: float) -> np.ndarray:
    """Output times in days, with spacing no larger than ``dt_output_hours``.

    The previous implementation used ``linspace`` after rounding the number
    of points, which silently changed a requested 7-hour output cadence into
    8-hour rows over a 1-day run. Here the requested step is preserved and the
    final run horizon is appended when it falls off-cadence.
    """

    if days == 0.0:
        return np.array([0.0], dtype=float)
    step_days = dt_output_hours / 24.0
    grid = np.arange(0.0, days, step_days, dtype=float)
    if grid.size == 0:
        grid = np.array([0.0], dtype=float)
    if np.isclose(grid[-1], days, rtol=0.0, atol=1e-12):
        grid[-1] = days
        return grid
    return np.append(grid, days)


def _build_timeseries(times: list[float], states: list[list[float]], p: Params) -> pd.DataFrame:
    df = pd.DataFrame(states, columns=list(STATE_ORDER))
    df.insert(0, "day", times)
    if p.couple_ph > 0.0:
        # Coupled Tier-2: pH is the integrated carbonate state, solved per row
        # from (DIC, Alk, T), so the toxic free-NH3 fraction tracks the drift.
        from .carbonate import ph_from_dic_alk

        ph_series = [
            _safe_ph(ph_from_dic_alk, float(dic), float(alk), p.temperature_c, p.ph)
            for dic, alk in zip(df["DIC"], df["Alk"], strict=True)
        ]
        df["pH"] = [round(v, 4) for v in ph_series]
        df["NH3_free"] = [
            round(max(tan, 0.0) * nh3_free_fraction(ph, p.temperature_c), 6)
            for tan, ph in zip(df["TAN"], ph_series, strict=True)
        ]
    else:
        f_free = nh3_free_fraction(p.ph, p.temperature_c)
        df["NH3_free"] = (df["TAN"].clip(lower=0.0) * f_free).round(6)
        df["pH"] = p.ph
    return df


def _safe_ph(solver: Any, dic: float, alk: float, temperature_c: float, fallback: float) -> float:
    """pH from the carbonate solver, falling back to the scenario pH if the
    buffer is driven outside the solvable bracket (mirrors processes)."""
    try:
        return solver(dic, alk, temperature_c)
    except ValueError:
        return fallback


def _build_warnings(df: pd.DataFrame) -> list[str]:
    warnings: list[str] = []
    _flag(
        warnings,
        df,
        "NH3_free",
        _NH3_FREE_STRESS,
        "free NH3 > 0.05 mg/L (chronic fish stress)",
    )
    _flag(warnings, df, "NO2", _NO2_STRESS, "NO2 > 0.5 mg-N/L (brown-blood risk)")
    _flag(warnings, df, "NO3", _NO3_WC_DUE, "NO3 > 50 mg-N/L (water change due)")
    return warnings


def _build_events_log(rows: list[dict[str, Any]]) -> pd.DataFrame:
    columns = [
        "day",
        "kind",
        "target",
        "value",
        "repeat_days",
        "priority",
        "TAN_before",
        "NO2_before",
        "NO3_before",
        "DO_before",
        "TAN_after",
        "NO2_after",
        "NO3_after",
        "DO_after",
        "ammonia_dose_before",
        "ammonia_dose_after",
    ]
    return pd.DataFrame(rows, columns=columns)


def _git_sha() -> str:
    repo = Path(__file__).resolve().parents[3]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "unknown"


def _stable_json_sha(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _schedule_payload(schedule: EventSchedule | None) -> list[dict[str, Any]]:
    if schedule is None:
        return []
    return [
        {
            "day": event.day,
            "kind": event.kind,
            "value": event.value,
            "target": event.target,
            "repeat_days": event.repeat_days,
        }
        for event in schedule.events
    ]


def _tap_water_payload(schedule: EventSchedule | None) -> dict[str, float] | None:
    if schedule is None:
        return None
    tap = schedule.tap_water
    return {
        "TAN": float(tap.TAN),
        "NO2": float(tap.NO2),
        "NO3": float(tap.NO3),
        "DO": float(tap.DO),
    }


def _build_provenance(
    *,
    initial_chem: Chemistry,
    initial_params: Params,
    final_params: Params,
    days: float,
    dt_output_hours: float,
    schedule: EventSchedule | None,
    timeseries: pd.DataFrame,
    events_log: pd.DataFrame,
    warnings: list[str],
) -> dict[str, Any]:
    fingerprint_payload = {
        "chemistry": asdict(initial_chem),
        "params": asdict(initial_params),
        "days": days,
        "dt_output_hours": dt_output_hours,
        "schedule": _schedule_payload(schedule),
        "tap_water": _tap_water_payload(schedule),
    }
    parameter_fingerprint = _stable_json_sha(fingerprint_payload)
    return {
        "openlimno_version": __version__,
        "schema": "openlimno-provenance/0.1+fishtank",
        "run_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "machine": {
            "host": socket.gethostname(),
            "platform": platform.platform(),
            "python": sys.version,
        },
        "parameter_fingerprint": parameter_fingerprint,
        "inputs": {
            "chemistry": asdict(initial_chem),
            "params": asdict(initial_params),
            "days": days,
            "dt_output_hours": dt_output_hours,
            "events": _schedule_payload(schedule),
            "tap_water": _tap_water_payload(schedule),
        },
        "outputs": {
            "timeseries_rows": int(len(timeseries)),
            "events": int(len(events_log)),
            "final_day": float(timeseries["day"].iloc[-1]) if len(timeseries) else 0.0,
            "final_params": asdict(final_params),
        },
        "warnings": list(warnings),
    }


def _flag(warnings: list[str], df: pd.DataFrame, col: str, thresh: float, msg: str) -> None:
    over = df[df[col] > thresh]
    if not over.empty:
        first_day = float(over["day"].iloc[0])
        warnings.append(f"{msg} — first crossed on day {first_day:.1f}")
