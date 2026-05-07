"""HSI curve representation and evaluation. SPEC §4.2.2.

Implements:
- ``HSICurve`` — piecewise-linear with mandatory category/transferability/quality
- ``composite_csi`` — geometric/arithmetic/min/weighted-geometric
- ``require_independence_ack`` — hard guard for geom/arith per ADR-0006
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt

CompositeMethod = Literal[
    "geometric_mean",
    "arithmetic_mean",
    "min",
    "weighted_geometric",
]


@dataclass
class HSICurve:
    """A piecewise-linear HSI curve. SPEC §4.2.2."""

    species: str
    life_stage: str
    variable: Literal["depth", "velocity", "substrate", "cover", "temperature"]
    points: list[tuple[float, float]]
    category: Literal["I", "II", "III"]
    geographic_origin: str
    transferability_score: float
    quality_grade: Literal["A", "B", "C"]
    independence_tested: bool = False
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError("HSI curve needs at least one (x, suitability) point")
        xs = [p[0] for p in self.points]
        ss = [p[1] for p in self.points]
        if any(np.diff(xs) < 0):
            raise ValueError(f"HSI curve x must be non-decreasing for {self.variable}")
        if any(s < 0 or s > 1 for s in ss):
            raise ValueError("HSI suitability must be in [0, 1]")

    def evaluate(self, values: npt.ArrayLike) -> np.ndarray:
        """Evaluate the curve on an array of input values.

        Below first x: returns first suitability.
        Above last x: returns last suitability.
        Values are linearly interpolated between control points.
        """
        v = np.asarray(values, dtype=float)
        xs = np.array([p[0] for p in self.points])
        ss = np.array([p[1] for p in self.points])
        return np.interp(v, xs, ss, left=ss[0], right=ss[-1])

    def transferability_warning(self, case_basin: str | None) -> str | None:
        """Return a warning string if score < 0.5 and basin differs, else None."""
        if (
            self.transferability_score < 0.5
            and case_basin
            and case_basin != self.geographic_origin
        ):
            return (
                f"HSI {self.species}/{self.life_stage}/{self.variable} has "
                f"transferability_score={self.transferability_score:.2f} from "
                f"basin '{self.geographic_origin}' applied in '{case_basin}'."
            )
        return None


# ---------------------------------------------------------------------
# Composite suitability
# ---------------------------------------------------------------------
def require_independence_ack(method: CompositeMethod, acknowledged: bool) -> None:
    """Hard guard per ADR-0006 / SPEC §4.2.2.2.

    For geometric/arithmetic mean (which assume variable independence),
    user must explicitly set ``acknowledge_independence: true`` in case config.
    """
    if method in ("geometric_mean", "arithmetic_mean") and not acknowledged:
        raise ValueError(
            f"composite='{method}' assumes HSI variable independence "
            "(see Mathur 1985 / Lancaster & Downes 2010 critique). "
            "You must set 'acknowledge_independence: true' in case config "
            "with a written rationale. SPEC §4.2.2.2 / ADR-0006."
        )


def composite_csi(
    suits: dict[str, np.ndarray],
    method: CompositeMethod = "geometric_mean",
    weights: dict[str, float] | None = None,
) -> np.ndarray:
    """Combine per-variable suitabilities into a single CSI per cell.

    Parameters
    ----------
    suits
        Mapping of variable name -> per-cell suitability array; all arrays
        must have identical shape.
    method
        Composite function. ``geometric_mean`` and ``arithmetic_mean`` require
        a separate ``require_independence_ack`` call.
    weights
        Required for ``weighted_geometric``. Defaults to equal weighting otherwise.
    """
    if not suits:
        raise ValueError("composite_csi: empty suits dict")
    arrs = list(suits.values())
    shape = arrs[0].shape
    for k, a in suits.items():
        if a.shape != shape:
            raise ValueError(f"suits['{k}'] shape {a.shape} != {shape}")

    n = len(arrs)
    stack = np.stack(arrs, axis=0)  # (n_vars, ...cells)

    if method == "min":
        return stack.min(axis=0)
    if method == "arithmetic_mean":
        return stack.mean(axis=0)
    if method == "geometric_mean":
        # Equivalent: nth root of product. Avoid log(0) using clip.
        return np.exp(np.log(np.clip(stack, 1e-12, 1.0)).mean(axis=0))
    if method == "weighted_geometric":
        if weights is None:
            weights = dict.fromkeys(suits, 1.0 / n)
        keys = list(suits.keys())
        w = np.array([weights[k] for k in keys])
        w = w / w.sum()
        log_stack = np.log(np.clip(stack, 1e-12, 1.0))
        return np.exp((w[:, None] * log_stack).sum(axis=0))
    raise ValueError(f"Unknown composite method: {method}")


# ---------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------
def load_hsi_from_parquet(path: str | Path) -> dict[tuple[str, str, str], HSICurve]:
    """Load HSI curves from a WEDM ``hsi_curve.parquet`` file."""
    import pandas as pd

    df = pd.read_parquet(path)
    out: dict[tuple[str, str, str], HSICurve] = {}
    for _, row in df.iterrows():
        # 'points' column may come back as numpy array of arrays or list of lists
        raw = row["points"]
        points = [(float(x), float(s)) for x, s in raw]
        curve = HSICurve(
            species=row["species"],
            life_stage=row["life_stage"],
            variable=row["variable"],
            points=points,
            category=row["category"],
            geographic_origin=row["geographic_origin"],
            transferability_score=float(row["transferability_score"]),
            quality_grade=row["quality_grade"],
            independence_tested=bool(row.get("independence_tested", False)),
            evidence=list(row.get("evidence", []) or []),
        )
        out[(curve.species, curve.life_stage, curve.variable)] = curve
    return out
