"""FishXing adapter stub (v2.2.0).

FishXing 3.0 is a no-longer-maintained JVM application from USDA
Forest Service. v2.2.0 ships the contract + file-presence detection;
the actual .fx3 report parser is v3.x.
"""
from __future__ import annotations

import os
from pathlib import Path

from benchmarks._compare.adapter import ModelAdapter, ReferenceResult


class FishXingAdapter(ModelAdapter):
    @property
    def platform(self) -> str:
        return "fishxing"

    def is_available(self) -> bool:
        # v3.x: detect bundled FishXing report fixtures under
        # benchmarks/fishxing/fixtures/. v2.2.0 looks for an env var
        # so a developer can opt-in by pointing at a local archive.
        return bool(os.environ.get("FISHXING_REPORT_DIR"))

    def run(self, case_yaml: Path | str) -> ReferenceResult:
        raise NotImplementedError(
            "FishXing parser is staged for v3.x; see "
            "benchmarks/fishxing/README.md for the .fx3 archive plan."
        )
