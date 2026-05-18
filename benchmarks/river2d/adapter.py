"""River2D adapter stub (v2.2.0).

Implements the :class:`benchmarks._compare.ModelAdapter` contract for
River2D 0.95 (Steffler & Blackburn 2002). Currently a stub: returns
``is_available() = False`` everywhere; the actual Wine + River2D
binary harness lands in v3.x. See ``benchmarks/river2d/README.md``.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from benchmarks._compare.adapter import ModelAdapter, ReferenceResult


class River2DAdapter(ModelAdapter):
    @property
    def platform(self) -> str:
        return "river2d"

    def is_available(self) -> bool:
        # v3.x: detect bundled Wine + River2D.exe under
        # benchmarks/river2d/bin/. v2.2.0 reports unavailable.
        return shutil.which("River2D.exe") is not None

    def run(self, case_yaml: Path | str) -> ReferenceResult:
        raise NotImplementedError(
            "River2D adapter is staged for v3.x; see "
            "benchmarks/river2d/README.md for the binary + Wine "
            "harness requirements."
        )
