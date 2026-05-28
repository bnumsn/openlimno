"""openlimno.fishtank — mechanistic ODE model of a closed freshwater
aquarium (microcosm).

Doubles as the worked example for a 4-hour Master's "Aquatic Ecology
Models" lab. See docs/fishtank/SPEC.md + docs/fishtank/COURSE_PLAN.md.

Tier-1 (nitrogen cycle) is implemented; carbonate/pH, plants, fish
bioenergetics are Tier-2 extensions taught as course exercises.
"""

from __future__ import annotations

from .carbonate import alkalinity_drop_meq, diagnostic_ph_trajectory, ph_from_dic_alk
from .events import Event, EventSchedule, TapWater
from .processes import derivatives, monod, oxidation_fluxes
from .solver import Result, simulate
from .state import Chemistry, Params, nh3_free_fraction

__all__ = [
    "Chemistry",
    "Event",
    "EventSchedule",
    "Params",
    "Result",
    "TapWater",
    "alkalinity_drop_meq",
    "derivatives",
    "diagnostic_ph_trajectory",
    "monod",
    "nh3_free_fraction",
    "oxidation_fluxes",
    "ph_from_dic_alk",
    "simulate",
]
