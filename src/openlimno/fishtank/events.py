"""Discrete keeper events + solver segmentation (SPEC §5, Hour-3 [core]).

The continuous ODE is integrated BETWEEN event times; at each event the
state is mapped instantaneously (water change dilutes dissolved species
toward tap water; the attached biofilm is untouched). This module defines
the event types and the boundary application; ``solver.simulate`` runs
the segment loop.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .state import STATE_ORDER, Chemistry, Params

# Dissolved species that a water change dilutes toward tap values. The
# attached biofilm states (X_AOB, X_NOB) are deliberately absent — they
# live on the media and are NOT removed by a water change (SPEC §1/§5).
_DISSOLVED = ("TAN", "NO2", "NO3", "DO")

# Attached biofilm guilds — the states a ``wipe_biofilm`` event reduces
# (washing media under chlorinated tap water, or a medication that kills
# nitrifiers). The mirror image of _DISSOLVED: a water change leaves these
# untouched, a biofilm wipe leaves the dissolved pool untouched.
_BIOFILM = ("X_AOB", "X_NOB")

# Params an event may retarget mid-run via ``set_param`` (time-varying
# driver, e.g. a power outage dropping reaeration k_a, or a heat-wave
# raising temperature). Restricted to physical/forcing fields so a scenario
# can't silently rewrite a kinetic constant mid-segment.
_SETTABLE_PARAMS = frozenset({"k_a", "DO_sat", "temperature_c", "R_fish", "ph"})

# Same-day ordering per SPEC §5: reset actions first (water change /
# biofilm wipe), then feed, then dose; ammonia_dose / set_param alongside
# dose. Lower number applies earlier.
_PRIORITY = {
    "water_change": 0,
    "wipe_biofilm": 0,
    "feed": 1,
    "dose": 2,
    "ammonia_dose": 2,
    "set_param": 2,
}
_VALID_EVENT_KINDS = frozenset(_PRIORITY)


@dataclass(frozen=True)
class Event:
    """A scheduled keeper action.

    kind ∈ {water_change, wipe_biofilm, ammonia_dose, feed, dose,
    set_param}. ``value`` meaning:
      - water_change : fraction in [0, 1]
      - wipe_biofilm : fraction in [0, 1] of attached biofilm removed
                       (washed media / medication kills nitrifiers); the
                       dissolved pool is untouched — the mirror of a water
                       change
      - ammonia_dose : new dose rate [mg-N/L/day] for subsequent segment
      - feed         : food [g/day] for subsequent segment (Tier-1 maps
                       to an ammonia-equivalent dose via a_exc)
      - dose         : amount added to ``target`` state, e.g. DO/NO3
      - set_param    : retarget a physical/forcing param ``target`` (one of
                       k_a, DO_sat, temperature_c, R_fish, ph) to ``value``
                       for the subsequent segment (power outage, heat wave)

    ``repeat_days`` (>0) materialises the event every ``repeat_days`` from
    ``day`` up to the run horizon (see EventSchedule.expand).
    """

    day: float
    kind: str
    value: float
    target: str = ""        # for kind="dose": which state to bump
    repeat_days: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in _VALID_EVENT_KINDS:
            raise ValueError(f"unknown event kind: {self.kind!r}")
        if not math.isfinite(self.day) or self.day < 0.0:
            raise ValueError(f"event day must be finite and non-negative, got {self.day!r}")
        if not math.isfinite(self.value):
            raise ValueError(f"event value must be finite, got {self.value!r}")
        if self.repeat_days < 0.0 or not math.isfinite(self.repeat_days):
            raise ValueError(
                f"repeat_days must be finite and non-negative, got {self.repeat_days!r}"
            )
        if self.kind in {"water_change", "wipe_biofilm"} and not 0.0 <= self.value <= 1.0:
            raise ValueError(f"{self.kind} fraction must be in [0, 1], got {self.value!r}")
        if self.kind in {"ammonia_dose", "feed"} and self.value < 0.0:
            raise ValueError(f"{self.kind} value must be non-negative, got {self.value!r}")
        if self.kind == "dose" and self.target not in STATE_ORDER:
            raise ValueError(f"dose target must be one of {STATE_ORDER}, got {self.target!r}")
        if self.kind == "set_param" and self.target not in _SETTABLE_PARAMS:
            raise ValueError(
                f"set_param target must be one of {sorted(_SETTABLE_PARAMS)}, got {self.target!r}"
            )

    @property
    def priority(self) -> int:
        return _PRIORITY.get(self.kind, 99)


@dataclass
class TapWater:
    """Replacement-water chemistry used by water_change."""

    TAN: float = 0.0
    NO2: float = 0.0
    NO3: float = 5.0
    DO: float = 8.5

    def get(self, name: str) -> float:
        return float(getattr(self, name, 0.0))


@dataclass
class EventSchedule:
    """An ordered list of events with helpers for the segment loop.

    Set ``horizon`` (run length, days) so ``repeat_days`` events expand;
    if 0, events are taken as-is (single occurrences)."""

    events: list[Event] = field(default_factory=list)
    tap_water: TapWater = field(default_factory=TapWater)
    horizon: float = 0.0

    def expand(self, days: float) -> list[Event]:
        """Materialise repeating events up to ``days`` (inclusive of day 0,
        exclusive of ``days``). Non-repeating events pass through once."""
        out: list[Event] = []
        for e in self.events:
            if e.repeat_days and e.repeat_days > 0:
                d = e.day
                while d < days:
                    out.append(Event(d, e.kind, e.value, e.target))
                    d += e.repeat_days
            else:
                out.append(e)
        return out

    def boundaries(self, days: float) -> list[float]:
        """Sorted unique event days strictly inside (0, days)."""
        return sorted({e.day for e in self.expand(days) if 0.0 < e.day < days})

    def at(self, day: float) -> list[Event]:
        """Events occurring on ``day``, in apply order. Uses ``horizon``
        for repeat expansion when set (else just the literal events)."""
        days = self.horizon if self.horizon > 0 else (day + 1.0)
        same = [e for e in self.expand(days) if e.day == day]
        return sorted(same, key=lambda e: e.priority)


def apply_event(
    chem: Chemistry, params: Params, event: Event, tap: TapWater,
) -> tuple[Chemistry, Params]:
    """Apply one event, returning (new_chemistry, new_params).

    Water change dilutes dissolved species toward tap; the biofilm X is
    carried through unchanged. ammonia_dose/feed update params for the
    next segment. dose bumps a single state.
    """
    c = Chemistry(**vars(chem))
    p = params

    if event.kind == "water_change":
        f = event.value
        for name in _DISSOLVED:
            old = getattr(c, name)
            setattr(c, name, old * (1.0 - f) + tap.get(name) * f)
        # X_AOB, X_NOB untouched — attached biofilm survives a water change.
    elif event.kind == "wipe_biofilm":
        # Mirror of water_change: knock back the attached biofilm (washed
        # media / medication) while leaving the dissolved pool alone. The
        # tank then has to re-colonise — TAN/NO2 climb back until X recovers.
        f = event.value
        for name in _BIOFILM:
            setattr(c, name, getattr(c, name) * (1.0 - f))
    elif event.kind == "set_param":
        # Retarget a physical/forcing param for the next segment (power
        # outage → low k_a, heat wave → higher temperature_c). The segment
        # solver already re-reads params each segment, so this takes effect
        # exactly like ammonia_dose does.
        p = params.with_overrides(**{event.target: event.value})
    elif event.kind == "ammonia_dose":
        p = params.with_overrides(ammonia_dose_mg_n_l_day=event.value)
    elif event.kind == "feed":
        # Tier-1: convert g-food/day to an ammonia-equivalent dose, stored in
        # the SEPARATE feed_dose source (NOT overwriting the abiotic
        # ammonia_dose) so dosing and feeding ADD rather than replace — this
        # is the source the agent-based model also sums (per-fish excretion).
        #   a_exc [g-N/g-food] · value [g-food/day] / V [L] → g-N/L/day
        #   × 1000 → mg-N/L/day.
        dose = params.a_exc * event.value / params.volume_l * 1000.0
        p = params.with_overrides(feed_dose_mg_n_l_day=dose)
    elif event.kind == "dose":
        setattr(c, event.target, getattr(c, event.target) + event.value)
    else:
        raise ValueError(f"unknown event kind: {event.kind!r}")
    return c, p


def event_from_mapping(value: Any, index: int = 0) -> Event:
    """Parse one scenario/Studio event mapping.

    All public entry points use this function so YAML files, browser payloads,
    and ABM runs accept the same field aliases:
    ``kind``/``type``, ``value``/``fraction``/``rate_mg_n_l_day``/
    ``amount_g``/``amount``, and ``target``/``chemical``.
    """

    doc = _mapping(value, f"events[{index}]")
    kind = str(doc.get("kind", doc.get("type", "")))
    day = _finite_float(doc.get("day", 0.0), f"events[{index}].day")
    repeat_days = _finite_float(doc.get("repeat_days", 0.0), f"events[{index}].repeat_days")
    target = str(doc.get("target", doc.get("chemical", "")))
    event_value = _event_value(doc, kind)
    if event_value is None:
        raise ValueError(f"events[{index}] missing value for kind {kind!r}")
    return Event(
        day=day,
        kind=kind,
        value=_finite_float(event_value, f"events[{index}].value"),
        target=target,
        repeat_days=repeat_days,
    )


def _event_value(doc: dict[str, Any], kind: str) -> Any:
    if kind in {"water_change", "wipe_biofilm"}:
        return doc.get("value", doc.get("fraction"))
    if kind == "ammonia_dose":
        return doc.get("value", doc.get("rate_mg_n_l_day"))
    if kind == "feed":
        return doc.get("value", doc.get("amount_g"))
    if kind == "dose":
        return doc.get("value", doc.get("amount"))
    if kind == "set_param":
        return doc.get("value", doc.get("to"))
    return doc.get("value")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return value


def _finite_float(value: Any, label: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric, got {value!r}") from exc
    if not math.isfinite(out):
        raise ValueError(f"{label} must be finite, got {value!r}")
    return out
