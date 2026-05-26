"""Hydrodynamics module. SPEC §4.1.

Provides two backends:

- ``Builtin1D`` — in-house Saint-Venant 1D (M1 MANSQ + M2 standard step; ADR-0003)
- ``SCHISMAdapter`` — subprocess wrapper for SCHISM 2D (M3; ADR-0002)

Both implement the ``HydroSolver`` Protocol. SPEC §3.2 rejects BMI in 1.0
(ADR-0004) because two backends don't justify a 25-method standard interface.

NAMESPACE NOTE (R-IBM-HYDROSOLVER cleanup track, ADR-0016 post-merge): this
package ALSO contains two workflow helpers that are NOT HydroSolver
implementations — they hardcode Builtin1D and sidestep the protocol:

- ``openlimno.hydro.calibration`` — grid-search Manning n calibration
- ``openlimno.hydro.gis_hydraulics`` — GIS-driven hydraulic cell builder

Round-22 review (codex A4 / gemini A3, MEDIUM) flagged this as namespace
pollution. The two modules' own docstrings document the boundary. Future
direction is either (a) a ``HydraulicWorkflow`` protocol added here, or
(b) moving the helpers to ``openlimno/workflows/``. Either lands as part
of the R-IBM-GOD-OBJECT refactor (still OPEN per ADR-0016).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .builtin_1d import (
    Builtin1D,
    CrossSection,
    MANSQResult,
    load_sections_from_parquet,
)
from .calibration import (
    Builtin1DCalibrationResult,
    Builtin1DCalibrationScore,
    calibrate_builtin1d_normal_depth,
    predict_builtin1d_normal_depth,
)
from .gis_hydraulics import (
    DEFAULT_DISCHARGES_M3S,
    GISHydraulicResult,
    build_builtin1d_gis_hydraulics,
)
from .schism import LTS_VERSION as SCHISM_LTS_VERSION
from .schism import (
    SCHISMAdapter,
    SCHISMBoundaryForcingPackage,
    SCHISMHydraulicResults,
    SCHISMRunReport,
    read_schism_hydraulic_results,
    write_schism_hydraulic_cells_csv,
    write_schism_type1_boundary_forcing,
)


class RunResult(Protocol):
    """Marker protocol for solver run results. M2 will define a concrete dataclass."""


class HydroSolver(Protocol):
    """Three-method solver contract. SPEC §3.2.1."""

    def prepare(self, case_yaml: str | Path, work_dir: str | Path) -> Path: ...

    def run(self, work_dir: str | Path) -> RunResult: ...

    def read_results(self, work_dir: str | Path) -> object:
        """Returns a WEDM-compatible xarray.Dataset."""
        ...


__all__ = [
    "DEFAULT_DISCHARGES_M3S",
    "SCHISM_LTS_VERSION",
    "Builtin1D",
    "Builtin1DCalibrationResult",
    "Builtin1DCalibrationScore",
    "CrossSection",
    "GISHydraulicResult",
    "HydroSolver",
    "MANSQResult",
    "RunResult",
    "SCHISMAdapter",
    "SCHISMBoundaryForcingPackage",
    "SCHISMHydraulicResults",
    "SCHISMRunReport",
    "build_builtin1d_gis_hydraulics",
    "calibrate_builtin1d_normal_depth",
    "load_sections_from_parquet",
    "predict_builtin1d_normal_depth",
    "read_schism_hydraulic_results",
    "write_schism_hydraulic_cells_csv",
    "write_schism_type1_boundary_forcing",
]
