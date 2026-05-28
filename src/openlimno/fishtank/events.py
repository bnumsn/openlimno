"""Discrete keeper events + solver segmentation (SPEC §5, Hour-3 [core]).

The continuous ODE is integrated BETWEEN event times; at each event the
state is mapped instantaneously (water change dilutes dissolved species
toward tap water; the attached biofilm is untouched). This module defines
the event types and the boundary application; ``solver.simulate`` runs
the segment loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .state import Chemistry, Params

# Dissolved species that a water change dilutes toward tap values. The
# attached biofilm states (X_AOB, X_NOB) are deliberately absent — they
# live on the media and are NOT removed by a water change (SPEC §1/§5).
_DISSOLVED = ("TAN", "NO2", "NO3", "DO")

# Same-day ordering: water change first (sets the baseline), then dosing,
# then a feeding/ammonia change. Lower number applies earlier.
_PRIORITY = {"water_change": 0, "dose": 1, "ammonia_dose": 2, "feed": 3}


@dataclass(frozen=True)
class Event:
    """A scheduled keeper action.

    kind ∈ {water_change, ammonia_dose, feed, dose}. ``value`` meaning:
      - water_change : fraction in [0, 1]
      - ammonia_dose : new dose rate [mg-N/L/day] for subsequent segment
      - feed         : food [g/day] for subsequent segment (Tier-1 maps
                       to an ammonia-equivalent dose via a_exc)
      - dose         : amount added to ``target`` state, e.g. DO/NO3
    """

    day: float
    kind: str
    value: float
    target: str = ""        # for kind="dose": which state to bump

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
    """An ordered list of events with helpers for the segment loop."""

    events: list[Event] = field(default_factory=list)
    tap_water: TapWater = field(default_factory=TapWater)

    def boundaries(self, days: float) -> list[float]:
        """Sorted unique event days strictly inside (0, days)."""
        inner = sorted({e.day for e in self.events if 0.0 < e.day < days})
        return inner

    def at(self, day: float) -> list[Event]:
        """Events occurring on ``day``, in apply order."""
        same = [e for e in self.events if e.day == day]
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
        f = max(0.0, min(1.0, event.value))
        for name in _DISSOLVED:
            old = getattr(c, name)
            setattr(c, name, old * (1.0 - f) + tap.get(name) * f)
        # X_AOB, X_NOB untouched — attached biofilm survives a water change.
    elif event.kind == "ammonia_dose":
        p = params.with_overrides(ammonia_dose_mg_n_l_day=event.value)
    elif event.kind == "feed":
        # Tier-1: convert g-food/day to an ammonia-equivalent dose.
        dose = params.a_exc * event.value / params.volume_l
        p = params.with_overrides(ammonia_dose_mg_n_l_day=dose)
    elif event.kind == "dose":
        if event.target:
            setattr(c, event.target, getattr(c, event.target) + event.value)
    else:
        raise ValueError(f"unknown event kind: {event.kind!r}")
    return c, p
