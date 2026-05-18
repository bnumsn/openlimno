"""Workflow module. SPEC §3.5.

Provides Snakemake-friendly orchestration helpers, a built-in scipy-based
calibration loop, and PEST++ GLM workspace/run helpers for environments
where an external ``pestpp-glm`` binary is installed.
"""

from __future__ import annotations

from .calibrate import (
    CalibrationResult,
    PestppRunResult,
    PestppWorkspace,
    build_pestpp_glm_workspace,
    calibrate_manning_n,
    run_pestpp_glm_workspace,
)

__all__ = [
    "CalibrationResult",
    "PestppRunResult",
    "PestppWorkspace",
    "build_pestpp_glm_workspace",
    "calibrate_manning_n",
    "run_pestpp_glm_workspace",
]
