"""Event attribution and reporting helpers for native IBM runs."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pandas as pd

EVENT_COLUMNS = ["scenario_id", "reach_id", "day", "event", "n", "n_eggs"]


class SpawnerProfile(Protocol):
    maturity_length_mm: float


def counts_by_reach(frame: pd.DataFrame, default_reach_id: str) -> dict[str, int]:
    """Count rows by reach, falling back to the configured reach id."""

    if frame.empty:
        return {}
    if "reach_id" not in frame:
        return {default_reach_id: int(len(frame))}
    return {
        str(key): int(value)
        for key, value in frame.groupby(frame["reach_id"].astype(str)).size().items()
    }


def spawner_counts_by_reach(
    fish: pd.DataFrame,
    profile: SpawnerProfile,
    spawn_season: int | None,
    default_reach_id: str,
) -> dict[str, int]:
    """Count fish that are eligible to spawn in the active season."""

    if spawn_season is None:
        return {}
    spawned_season = pd.to_numeric(fish["spawned_season"], errors="coerce").fillna(-1).astype(int)
    mature = (
        fish["alive"].astype(bool)
        & (fish["length_mm"] >= float(profile.maturity_length_mm))
        & (spawned_season != int(spawn_season))
    )
    return counts_by_reach(fish.loc[mature], default_reach_id)


def event_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    """Return a stable event table with all standard columns present."""

    return pd.DataFrame.from_records(rows, columns=EVENT_COLUMNS)


def summarize_events(events: pd.DataFrame) -> pd.DataFrame:
    """Aggregate event counts into a compact attribution report."""

    columns = [
        "scenario_id",
        "reach_id",
        "event",
        "n_events",
        "total_n",
        "total_eggs",
        "first_day",
        "last_day",
    ]
    if events.empty:
        return pd.DataFrame(columns=columns)
    table = events.copy()
    table["n"] = pd.to_numeric(table.get("n", 0), errors="coerce").fillna(0).astype(int)
    table["n_eggs"] = (
        pd.to_numeric(table.get("n_eggs", 0), errors="coerce").fillna(0).astype(int)
    )
    table["day"] = pd.to_numeric(table.get("day", 0), errors="coerce").fillna(0).astype(int)
    return (
        table.groupby(["scenario_id", "reach_id", "event"], dropna=False, as_index=False)
        .agg(
            n_events=("event", "size"),
            total_n=("n", "sum"),
            total_eggs=("n_eggs", "sum"),
            first_day=("day", "min"),
            last_day=("day", "max"),
        )
        .sort_values(["scenario_id", "reach_id", "event"], kind="mergesort")
        .reset_index(drop=True)[columns]
    )


def daily_event_summary(events: pd.DataFrame) -> pd.DataFrame:
    """Aggregate event counts by day, reach, and event type."""

    columns = ["scenario_id", "reach_id", "day", "event", "n", "n_eggs"]
    if events.empty:
        return pd.DataFrame(columns=columns)
    table = events.copy()
    table["n"] = pd.to_numeric(table.get("n", 0), errors="coerce").fillna(0).astype(int)
    table["n_eggs"] = (
        pd.to_numeric(table.get("n_eggs", 0), errors="coerce").fillna(0).astype(int)
    )
    return (
        table.groupby(["scenario_id", "reach_id", "day", "event"], dropna=False, as_index=False)
        .agg(n=("n", "sum"), n_eggs=("n_eggs", "sum"))
        .sort_values(["scenario_id", "reach_id", "day", "event"], kind="mergesort")
        .reset_index(drop=True)[columns]
    )


def write_event_report(events: pd.DataFrame, output_dir: str | Path) -> dict[str, str]:
    """Write daily and total event attribution tables."""

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    daily_path = out / "native_ibm_event_daily.csv"
    summary_path = out / "native_ibm_event_summary.csv"
    daily_event_summary(events).to_csv(daily_path, index=False)
    summarize_events(events).to_csv(summary_path, index=False)
    return {
        "native_ibm_event_daily": str(daily_path),
        "native_ibm_event_summary": str(summary_path),
    }


__all__ = [
    "EVENT_COLUMNS",
    "counts_by_reach",
    "daily_event_summary",
    "event_frame",
    "spawner_counts_by_reach",
    "summarize_events",
    "write_event_report",
]
