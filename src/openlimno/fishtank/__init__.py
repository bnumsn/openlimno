"""openlimno.fishtank — mechanistic ODE model of a closed freshwater
aquarium (microcosm).

Doubles as the worked example for a 4-hour Master's "Aquatic Ecology
Models" lab. See docs/fishtank/SPEC.md + docs/fishtank/COURSE_PLAN.md.

Tier-1 (nitrogen cycle) is implemented; carbonate/pH, plants, fish
bioenergetics are Tier-2 extensions taught as course exercises.
"""

from __future__ import annotations

from .agent import FishAgent, MicrobePatch, simulate_agent_based_model
from .carbonate import alkalinity_drop_meq, diagnostic_ph_trajectory, ph_from_dic_alk
from .events import Event, EventSchedule, TapWater
from .io import (
    Scenario,
    load_scenario,
    read_observation,
    run_scenario,
    scenario_from_mapping,
    scenario_sha256,
    validate_scenario,
    write_result,
    write_scenario,
)
from .library import default_params, equipment, species, tap_water
from .processes import derivatives, monod, oxidation_fluxes
from .solver import Result, simulate
from .state import Chemistry, Params, nh3_free_fraction
from .studio_http import run_fishtank_studio

__all__ = [
    "Chemistry",
    "Event",
    "EventSchedule",
    "FishAgent",
    "MicrobePatch",
    "Params",
    "Result",
    "Scenario",
    "TapWater",
    "alkalinity_drop_meq",
    "default_params",
    "derivatives",
    "diagnostic_ph_trajectory",
    "equipment",
    "load_scenario",
    "monod",
    "nh3_free_fraction",
    "oxidation_fluxes",
    "ph_from_dic_alk",
    "read_observation",
    "run_fishtank_studio",
    "run_scenario",
    "scenario_from_mapping",
    "scenario_sha256",
    "simulate",
    "simulate_agent_based_model",
    "species",
    "tap_water",
    "validate_scenario",
    "write_result",
    "write_scenario",
]
