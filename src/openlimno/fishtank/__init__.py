"""openlimno.fishtank — mechanistic ODE model of a closed freshwater
aquarium (microcosm).

Doubles as the worked example for a 4-hour Master's "Aquatic Ecology
Models" lab. See docs/fishtank/SPEC.md + docs/fishtank/COURSE_PLAN.md.

Tier-1 (nitrogen cycle) is implemented; carbonate/pH, plants, fish
bioenergetics are Tier-2 extensions taught as course exercises.
"""

from __future__ import annotations

from .processes import derivatives, monod, oxidation_fluxes
from .solver import Result, simulate
from .state import Chemistry, Params, nh3_free_fraction

__all__ = [
    "Chemistry",
    "Params",
    "Result",
    "derivatives",
    "monod",
    "nh3_free_fraction",
    "oxidation_fluxes",
    "simulate",
]
