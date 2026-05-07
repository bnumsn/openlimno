"""Workflow module. SPEC §3.5.

Provides Snakemake-friendly orchestration helpers + a built-in scipy-based
calibration loop. PEST++ deep integration lands in 1.x.
"""

from __future__ import annotations

from .calibrate import CalibrationResult, calibrate_manning_n

__all__ = ["CalibrationResult", "calibrate_manning_n"]
