"""HABBY adapter stub (v2.2.0).

HABBY is the most tractable of the four reference platforms — pure
Python, LGPL, importable on Linux. v2.2.0 ships the contract +
``is_available`` detection; the actual XML-translation bridge is v3.x.
"""
from __future__ import annotations

import importlib
from pathlib import Path

from benchmarks._compare.adapter import ModelAdapter, ReferenceResult


class HabbyAdapter(ModelAdapter):
    @property
    def platform(self) -> str:
        return "habby"

    def is_available(self) -> bool:
        try:
            importlib.import_module("habby")
        except ImportError:
            return False
        return True

    def run(self, case_yaml: Path | str) -> ReferenceResult:
        raise NotImplementedError(
            "HABBY bridge is staged for v3.x; see "
            "benchmarks/habby/README.md for the XML-translation plan."
        )
