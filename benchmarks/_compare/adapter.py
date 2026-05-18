"""ModelAdapter contract for the 3.x multi-model comparison harness.

Each reference platform (PHABSIM / River2D / HABBY / FishXing) exposes
an adapter that, given the *same* hydraulic + HSI inputs as an
OpenLimno case, returns a normalised :class:`ReferenceResult` for
comparison. The :func:`compare_against` driver runs both sides and
emits a :class:`WUAComparison` that includes per-discharge maximum
absolute and relative error.

Designed so that:

* OpenLimno's own outputs need no special treatment — they go through
  the same adapter contract, with :class:`OpenLimnoSelfAdapter`
  delegating to :meth:`openlimno.case.Case.run`.
* Reference adapters live in sibling packages
  (``benchmarks.phabsim_bovee1997``, ``benchmarks.river2d``,
  ``benchmarks.habby``, ``benchmarks.fishxing``) — each carrying its
  own README about how to obtain the reference binary, the licence
  constraints, and the equivalence threshold.
* The harness is **declarative**. Acceptance thresholds (typically
  ``1e-3`` for closed-form references and ``5%`` for empirically
  validated codes) live in YAML alongside each benchmark, not in
  Python literals, so v3.x research-route work can tighten / loosen
  thresholds without touching the harness.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class ReferenceResult:
    """Normalised output from a single platform run.

    Attributes:
        platform: identifier such as ``"openlimno"``, ``"phabsim"``,
            ``"river2d"``, ``"habby"``, ``"fishxing"``.
        wua_q: DataFrame with columns ``discharge_m3s`` and one or
            more ``wua_m2_<species>_<stage>`` columns. Per-discharge
            rows. (For platforms that emit additional fish-passage
            outputs — FishXing — those columns are also included; the
            comparison harness ignores columns the reference platform
            doesn't share.)
        provenance: free-form provenance dict (platform version,
            input hashes, run timestamp) for the audit trail.
    """

    platform: str
    wua_q: pd.DataFrame
    provenance: dict


@dataclass(frozen=True)
class WUAComparison:
    """Result of comparing two :class:`ReferenceResult` instances.

    Attributes:
        platform_a, platform_b: identifiers from the inputs.
        max_abs_error_m2: maximum |WUA_a − WUA_b| across all
            (discharge, species/stage) cells the two share.
        max_rel_error: ``max_abs_error_m2 / max(WUA_a)`` over the
            same shared cells. ``None`` if the reference is identically
            zero (in which case ``max_abs_error_m2`` is the only
            meaningful figure).
        n_compared: number of (discharge, species/stage) cells that
            were compared (intersection of the two tables).
        passed: whether the comparison passed its YAML-declared
            acceptance threshold.
        threshold: the YAML-declared threshold that was applied
            (a dict like ``{"max_abs_m2": 1e-3, "max_rel": 0.05}``).
    """

    platform_a: str
    platform_b: str
    max_abs_error_m2: float
    max_rel_error: float | None
    n_compared: int
    passed: bool
    threshold: dict


class ModelAdapter(ABC):
    """Each reference platform implements this contract.

    The adapter is responsible for:

    1. Taking an OpenLimno case YAML (the canonical input format) and
       translating it to whatever the reference platform expects.
    2. Running the reference platform on the translated inputs.
    3. Reading back the reference output and normalising it into a
       :class:`ReferenceResult`.

    Adapters that need an external binary (PHABSIM under Wine, River2D
    on Windows) raise ``ModuleNotFoundError`` from
    :meth:`is_available` rather than failing inside :meth:`run` — the
    harness skips comparisons whose adapter is unavailable on the
    current platform, recording the skip in provenance.
    """

    @property
    @abstractmethod
    def platform(self) -> str:
        """Stable identifier, e.g. ``"river2d"``."""

    @abstractmethod
    def is_available(self) -> bool:
        """Whether this adapter can run on the current host.

        Implementations should NOT raise — return ``False`` and let
        the harness skip cleanly.
        """

    @abstractmethod
    def run(self, case_yaml: Path | str) -> ReferenceResult:
        """Run the reference platform on the given OpenLimno case."""


def compare_against(
    openlimno_result: ReferenceResult,
    reference_result: ReferenceResult,
    *,
    threshold: dict,
) -> WUAComparison:
    """Pair-wise compare two :class:`ReferenceResult` instances.

    The comparison is the intersection of (discharge_m3s,
    species/stage) cells the two tables share. Cells missing from
    one platform are silently skipped (FishXing won't have WUA at
    high discharges; River2D won't have it at very low ones — the
    comparison reports only what both platforms can compute).

    Args:
        openlimno_result: the v2.x OpenLimno output.
        reference_result: the reference platform's normalised output.
        threshold: ``{"max_abs_m2": <float>, "max_rel": <float>}``.
            Both keys are required; the result ``passed`` iff
            ``max_abs_error_m2 <= max_abs_m2`` AND
            ``max_rel_error <= max_rel`` (relative ignored when
            reference is zero).

    Returns:
        :class:`WUAComparison`.
    """
    a, b = openlimno_result, reference_result

    a_discharges = set(a.wua_q["discharge_m3s"])
    b_discharges = set(b.wua_q["discharge_m3s"])
    common_q = sorted(a_discharges & b_discharges)

    a_cols = {c for c in a.wua_q.columns if c.startswith("wua_m2_")}
    b_cols = {c for c in b.wua_q.columns if c.startswith("wua_m2_")}
    common_cols = sorted(a_cols & b_cols)

    if not common_q or not common_cols:
        return WUAComparison(
            platform_a=a.platform,
            platform_b=b.platform,
            max_abs_error_m2=0.0,
            max_rel_error=None,
            n_compared=0,
            passed=False,
            threshold=threshold,
        )

    a_indexed = a.wua_q.set_index("discharge_m3s")
    b_indexed = b.wua_q.set_index("discharge_m3s")

    max_abs = 0.0
    max_rel: float | None = None
    n = 0
    for q in common_q:
        for col in common_cols:
            n += 1
            val_a = float(a_indexed.loc[q, col])
            val_b = float(b_indexed.loc[q, col])
            err = abs(val_a - val_b)
            max_abs = max(max_abs, err)
            denom = max(abs(val_a), abs(val_b))
            if denom > 0:
                rel = err / denom
                if max_rel is None or rel > max_rel:
                    max_rel = rel

    passed = max_abs <= threshold["max_abs_m2"]
    if max_rel is not None and "max_rel" in threshold:
        passed = passed and max_rel <= threshold["max_rel"]

    return WUAComparison(
        platform_a=a.platform,
        platform_b=b.platform,
        max_abs_error_m2=float(max_abs),
        max_rel_error=max_rel,
        n_compared=n,
        passed=passed,
        threshold=threshold,
    )


class OpenLimnoSelfAdapter(ModelAdapter):
    """Adapter that wraps OpenLimno's own :class:`Case.run` output.

    Used as the "side A" of every benchmark comparison — every
    reference platform is compared against this.
    """

    @property
    def platform(self) -> str:
        return "openlimno"

    def is_available(self) -> bool:
        return True

    def run(self, case_yaml: Path | str) -> ReferenceResult:
        import numpy as _np

        from openlimno import __version__
        from openlimno.case import Case

        case = Case.from_yaml(Path(case_yaml))
        # Default sweep — benchmark YAMLs override via their own scripts.
        result = case.run(
            discharges_m3s=list(_np.linspace(1.0, 30.0, 12)),
            slope=0.002,
            manning_n=0.035,
        )
        return ReferenceResult(
            platform="openlimno",
            wua_q=result.wua_q,
            provenance={
                "openlimno_version": __version__,
                "case_name": case.name,
                "n_discharges": len(result.discharges_m3s),
            },
        )
