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
from .cover import (
    DEFAULT_RIPARIAN_COVER_SI,
    cover_si_from_lulc_raster,
    cover_si_from_polyline,
    cover_si_summary,
    riparian_buffer_from_polyline,
    watershed_cover_si,
)
from .thermal import (
    DEFAULT_LETHAL_MARGIN_C,
    ThermalRange,
    thermal_hsi,
    thermal_metrics,
    thermal_suitability_series,
)
from .wua import cell_wua, wua_q_curve

__all__ = [
    "DriftingEggResult",
    "HMUThresholds",
    "HMUType",
    "HSICurve",
    "aggregate_wua_by_hmu",
    "aggregate_wua_by_reach",
    "cell_wua",
    "classify_hmu",
    "classify_reach",
    "composite_csi",
    "evaluate_drifting_egg",
    "load_drifting_egg_params",
    "load_hsi_from_parquet",
    "regulatory_export",
    "require_independence_ack",
    "wua_q_curve",
    "DEFAULT_LETHAL_MARGIN_C",
    "ThermalRange",
    "thermal_hsi",
    "thermal_metrics",
    "thermal_suitability_series",
    "DEFAULT_RIPARIAN_COVER_SI",
    "cover_si_from_lulc_raster",
    "cover_si_from_polyline",
    "cover_si_summary",
    "riparian_buffer_from_polyline",
    "watershed_cover_si",
]
