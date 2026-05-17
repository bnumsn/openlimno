"""Habitat assessment module. SPEC §4.2.

Public API:
    HSICurve.evaluate(values)         -> per-cell suitability ∈ [0,1]
    composite_csi(suits, method)      -> per-cell CSI
    cell_wua(csi, area)               -> per-cell WUA contribution
    wua_q_curve(...)                  -> WUA as function of Q
    load_hsi_from_parquet(path)       -> {(species, stage, var): HSICurve}

Enforces SPEC §4.2.2.2 acknowledge_independence for geom/arith composites.
"""

from __future__ import annotations

from . import regulatory_export
from .cells import (
    DEFAULT_GROUP_COLUMNS,
    HabitatCellsResult,
    evaluate_habitat_cells,
    summarize_habitat_by_hmu,
    summarize_habitat_cells,
)
from .cover import (
    DEFAULT_RIPARIAN_COVER_SI,
    cover_si_from_lulc_raster,
    cover_si_from_polyline,
    cover_si_summary,
    riparian_buffer_from_polyline,
    watershed_cover_si,
)
from .drifting_egg import DriftingEggResult, evaluate_drifting_egg, load_drifting_egg_params
from .hmu import (
    HMUThresholds,
    HMUType,
    aggregate_wua_by_hmu,
    aggregate_wua_by_reach,
    classify_hmu,
    classify_reach,
)
from .hsi import HSICurve, composite_csi, load_hsi_from_parquet, require_independence_ack
from .thermal import (
    DEFAULT_LETHAL_MARGIN_C,
    ThermalRange,
    thermal_hsi,
    thermal_metrics,
    thermal_suitability_series,
)
from .wua import cell_wua, wua_q_curve

__all__ = [
    "DEFAULT_GROUP_COLUMNS",
    "DEFAULT_LETHAL_MARGIN_C",
    "DEFAULT_RIPARIAN_COVER_SI",
    "DriftingEggResult",
    "HMUThresholds",
    "HMUType",
    "HSICurve",
    "HabitatCellsResult",
    "ThermalRange",
    "aggregate_wua_by_hmu",
    "aggregate_wua_by_reach",
    "cell_wua",
    "classify_hmu",
    "classify_reach",
    "composite_csi",
    "cover_si_from_lulc_raster",
    "cover_si_from_polyline",
    "cover_si_summary",
    "evaluate_drifting_egg",
    "evaluate_habitat_cells",
    "load_drifting_egg_params",
    "load_hsi_from_parquet",
    "regulatory_export",
    "require_independence_ack",
    "riparian_buffer_from_polyline",
    "summarize_habitat_by_hmu",
    "summarize_habitat_cells",
    "thermal_hsi",
    "thermal_metrics",
    "thermal_suitability_series",
    "watershed_cover_si",
    "wua_q_curve",
]
