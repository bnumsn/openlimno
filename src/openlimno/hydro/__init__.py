"""Hydrodynamics module. SPEC §4.1.

Provides two backends:

- ``Builtin1D`` — in-house Saint-Venant 1D (M1 MANSQ + M2 standard step; ADR-0003)
- ``SCHISMAdapter`` — subprocess wrapper for SCHISM 2D (M3; ADR-0002)

Both implement the ``HydroSolver`` Protocol. SPEC §3.2 rejects BMI in 1.0
(ADR-0004) because two backends don't justify a 25-method standard interface.
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
from .schism import LTS_VERSION as SCHISM_LTS_VERSION
from .schism import SCHISMAdapter, SCHISMRunReport


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
    "SCHISM_LTS_VERSION",
    "Builtin1D",
    "CrossSection",
    "HydroSolver",
    "MANSQResult",
    "RunResult",
    "SCHISMAdapter",
    "SCHISMRunReport",
    "load_sections_from_parquet",
]
