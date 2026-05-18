"""HABBY reference adapter.

HABBY is the most tractable of the four reference platforms — pure
Python, LGPL, importable on Linux. OpenLimno can compare against HABBY
by reading exported HABBY/CASiMiR-style WUA tables from
``HABBY_REFERENCE_DIR``. A full HABBY project XML writer can be layered
on top without changing the adapter contract.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path

from benchmarks._compare.adapter import ModelAdapter, ReferenceResult
from benchmarks._compare.exchange import reference_result_from_habitat_file

_REFERENCE_SUFFIXES = (".csv", ".tsv", ".tab", ".parquet")


def _reference_dir() -> Path | None:
    raw = os.environ.get("HABBY_REFERENCE_DIR")
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


class HabbyAdapter(ModelAdapter):
    @property
    def platform(self) -> str:
        return "habby"

    def is_available(self) -> bool:
        if _reference_dir() is not None:
            return True
        try:
            importlib.import_module("habby")
        except ImportError:
            return False
        return True

    def run(self, case_yaml: Path | str) -> ReferenceResult:
        reference_file = _find_reference_file(case_yaml)
        if reference_file is None:
            raise FileNotFoundError(
                "HABBY reference output not found. Set HABBY_REFERENCE_DIR "
                "to a directory containing <case-stem>.csv/.tsv/.parquet, "
                "or a single HABBY WUA export file."
            )
        return reference_result_from_habitat_file(
            reference_file,
            platform=self.platform,
            source_key="habby-reference",
        )
