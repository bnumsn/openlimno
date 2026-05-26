"""Registered native IBM submodel contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class IBMSubmodel:
    """Metadata for a selectable IBM submodel implementation."""

    slot: str
    id: str
    label: str
    description: str
    profile_parameters: tuple[str, ...] = ()
    default: bool = True


_SUBMODELS: tuple[IBMSubmodel, ...] = (
    IBMSubmodel(
        slot="growth",
        id="native-bioenergetic-growth-v0",
        label="Native bioenergetic growth",
        description="Mass-balance growth from consumption opportunity, respiration, and activity cost.",
        profile_parameters=(
            "max_daily_growth_mm",
            "max_consumption_fraction",
            "respiration_fraction",
            "activity_respiration_fraction",
        ),
    ),
    IBMSubmodel(
        slot="habitat_selection",
        id="native-habitat-utility-v0",
        label="Native habitat utility",
        description="Cell choice from CSI, cover, temperature, turbidity, mortality risk, and density.",
        profile_parameters=(
            "utility_growth_weight",
            "utility_mortality_weight",
            "density_competition_strength",
        ),
    ),
    IBMSubmodel(
        slot="light_cycle",
        id="native-daily-light-cycle-v0",
        label="Native daily light cycle",
        description="Dawn/day/dusk/night feeding and predation weights for each simulated day.",
        profile_parameters=(
            "light_phase_feeding_weights",
            "light_phase_predation_weights",
        ),
    ),
    IBMSubmodel(
        slot="mortality",
        id="native-risk-survival-v0",
        label="Native risk survival",
        description="Daily survival from baseline, predation exposure, thermal stress, and hydraulic stress.",
        profile_parameters=(
            "base_daily_survival",
            "predation_base_risk",
            "predation_csi_risk",
            "thermal_stress_mortality",
            "hydraulic_stress_mortality",
        ),
    ),
    IBMSubmodel(
        slot="movement",
        id="native-adjacent-reach-movement-v0",
        label="Native adjacent-reach movement",
        description="Optional ordered-adjacent reach movement gated by body size and habitat utility.",
        profile_parameters=(
            "allow_cross_reach_movement",
            "cross_reach_movement_rate",
            "cross_reach_movement_min_length_mm",
            "cross_reach_upstream_bias",
        ),
    ),
    IBMSubmodel(
        slot="movement",
        id="native-network-reach-movement-v0",
        label="Native graph reach movement",
        description=(
            "Graph-based reach movement with optional source/target reach links "
            "and barrier passage probabilities."
        ),
        profile_parameters=(
            "allow_cross_reach_movement",
            "cross_reach_movement_rate",
            "cross_reach_movement_min_length_mm",
            "cross_reach_habitat_utility_weight",
            "cross_reach_upstream_bias",
        ),
        default=False,
    ),
    IBMSubmodel(
        slot="spawning",
        id="native-redd-recruitment-v0",
        label="Native redd recruitment",
        description="Spawner selection, redd creation, egg survival, thermal incubation, and fry emergence.",
        profile_parameters=(
            "spawn_start_day",
            "spawn_end_day",
            "fecundity_per_female",
            "egg_incubation_degree_days",
            "egg_to_fry_survival",
        ),
    ),
    IBMSubmodel(
        slot="spawning",
        id="native-calibrated-redd-placement-v0",
        label="Native calibrated redd placement",
        description=(
            "Redd recruitment with placement scores that can include habitat priors, "
            "depth suitability, and scour-risk terms."
        ),
        profile_parameters=(
            "spawning_cover_weight",
            "spawning_csi_weight",
            "redd_min_depth_m",
            "redd_scour_velocity_ms",
        ),
        default=False,
    ),
)


def list_ibm_submodels(slot: str | None = None) -> tuple[IBMSubmodel, ...]:
    """Return registered IBM submodels, optionally filtered by slot."""

    if slot is None:
        return _SUBMODELS
    return tuple(model for model in _SUBMODELS if model.slot == slot)


def default_submodel_selection() -> dict[str, str]:
    """Return the default submodel id for each slot."""

    return {model.slot: model.id for model in _SUBMODELS if model.default}


def _ids_by_slot() -> dict[str, set[str]]:
    ids: dict[str, set[str]] = {}
    for model in _SUBMODELS:
        ids.setdefault(model.slot, set()).add(model.id)
    return ids


def validate_submodel_selection(selection: Mapping[str, object] | None) -> list[str]:
    """Return semantic validation errors for a scenario ``submodels`` block."""

    if selection is None:
        return []
    ids_by_slot = _ids_by_slot()
    errors: list[str] = []
    for slot, raw_id in selection.items():
        if slot not in ids_by_slot:
            allowed = ", ".join(sorted(ids_by_slot))
            errors.append(f"submodels/{slot}: unknown submodel slot; expected one of {allowed}")
            continue
        if not isinstance(raw_id, str):
            errors.append(f"submodels/{slot}: submodel id must be a string")
            continue
        if raw_id not in ids_by_slot[slot]:
            allowed = ", ".join(sorted(ids_by_slot[slot]))
            errors.append(f"submodels/{slot}: unsupported submodel id {raw_id!r}; expected {allowed}")
    return errors


def resolve_submodel_selection(selection: Mapping[str, object] | None) -> dict[str, str]:
    """Merge a scenario submodel selection with registered defaults."""

    errors = validate_submodel_selection(selection)
    if errors:
        raise ValueError("IBM submodel selection failed validation:\n  - " + "\n  - ".join(errors))
    resolved = default_submodel_selection()
    if selection is not None:
        for slot, raw_id in selection.items():
            resolved[slot] = str(raw_id)
    return resolved


__all__ = [
    "IBMSubmodel",
    "default_submodel_selection",
    "list_ibm_submodels",
    "resolve_submodel_selection",
    "validate_submodel_selection",
]
