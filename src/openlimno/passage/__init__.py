"""Fish passage module. SPEC §4.3, ADR-0007.

η = η_A × η_P decomposition. 1.0 computes only η_P (passage success rate);
η_A is user-supplied via case config (`attraction_efficiency.value`).

Public API:
    Culvert                — geometry + material + slope
    SwimmingModel          — burst/prolonged/sustained per stage / temp
    passage_success_rate   — deterministic and Monte Carlo η_P
    PassageResult          — result dataclass
"""

from __future__ import annotations

from .culvert import Culvert
from .passage import (
    PassageResult,
    SwimmingModel,
    load_swimming_model_from_parquet,
    passage_success_rate,
)

__all__ = [
    "Culvert",
    "PassageResult",
    "SwimmingModel",
    "load_swimming_model_from_parquet",
    "passage_success_rate",
]
