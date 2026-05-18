"""FishXing reference adapter.

FishXing 3.0 is a no-longer-maintained JVM application from USDA
Forest Service. OpenLimno compares against archived FishXing report
exports from ``FISHXING_REPORT_DIR``; the adapter normalizes velocity
tables into the shared reference-result surface.
"""
from __future__ import annotations

import os
from pathlib import Path

from benchmarks._compare.adapter import ModelAdapter, ReferenceResult
from benchmarks.fishxing.parser import read_fishxing_report

_REFERENCE_SUFFIXES = (".csv", ".tsv", ".tab", ".xlsx", ".xls")


def _reference_dir() -> Path | None:
    raw = os.environ.get("FISHXING_REPORT_DIR")
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


class FishXingAdapter(ModelAdapter):
    @property
    def platform(self) -> str:
        return "fishxing"

    def is_available(self) -> bool:
        return _reference_dir() is not None

    def run(self, case_yaml: Path | str) -> ReferenceResult:
        reference_file = _find_reference_file(case_yaml)
        if reference_file is None:
            raise FileNotFoundError(
                "FishXing reference report not found. Set FISHXING_REPORT_DIR "
                "to a directory containing <case-stem>.csv/.xlsx, or a "
                "single FishXing velocity report export."
            )
        return read_fishxing_report(reference_file)
