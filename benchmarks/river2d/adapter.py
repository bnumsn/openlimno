"""River2D reference adapter.

Implements the :class:`benchmarks._compare.ModelAdapter` contract for
River2D 0.95 (Steffler & Blackburn 2002). OpenLimno does not bundle the
Windows-only binary; point ``RIVER2D_REFERENCE_DIR`` at exported River2D
WUA CSV/TSV/Parquet tables to run comparisons against archived results.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from benchmarks._compare.adapter import ModelAdapter, ReferenceResult
from benchmarks._compare.exchange import reference_result_from_habitat_file

_REFERENCE_SUFFIXES = (".csv", ".tsv", ".tab", ".parquet")


def _reference_dir() -> Path | None:
    raw = os.environ.get("RIVER2D_REFERENCE_DIR")
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def _find_reference_file(case_yaml: Path | str) -> Path | None:
    directory = _reference_dir()
    if directory is None:
        return None
    stem = Path(case_yaml).stem
    for suffix in _REFERENCE_SUFFIXES:
        candidate = directory / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate
    files = sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in _REFERENCE_SUFFIXES
    )
    return files[0] if len(files) == 1 else None


class River2DAdapter(ModelAdapter):
    @property
    def platform(self) -> str:
        return "river2d"

    def is_available(self) -> bool:
        return _reference_dir() is not None or shutil.which("River2D.exe") is not None

    def run(self, case_yaml: Path | str) -> ReferenceResult:
        reference_file = _find_reference_file(case_yaml)
        if reference_file is None:
            raise FileNotFoundError(
                "River2D reference output not found. Set RIVER2D_REFERENCE_DIR "
                "to a directory containing <case-stem>.csv/.tsv/.parquet, or "
                "a single River2D WUA export file."
            )
        result = reference_result_from_habitat_file(
            reference_file,
            platform=self.platform,
            source_key="river2d-reference",
        )
        return result
