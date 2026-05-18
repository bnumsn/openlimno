"""Multi-model comparison harness (v2.2.0).

The v2.0.0 charter committed OpenLimno's "3.x research route" to
benchmark equivalence against four reference platforms:

* **PHABSIM** — already exercised by ``benchmarks/phabsim_bovee1997/``
  with a closed-form analytic case (Bovee 1986 / 1997 / Stalnaker 1995).
* **River2D** — Steffler & Blackburn (2002); validation case is the
  Lemhi River (used as OpenLimno's primary example since v0.6).
* **HABBY** — Le Coarer et al. (Irstea/INRAE Lyon); the open-source
  reference for the multi-method per-cell composite (product /
  geometric-mean / arithmetic-mean) that v1.6.0 — v2.1.0 built on.
* **FishXing** — Furniss & Love (USDA Forest Service); fish-passage
  velocity-time-distance reference, complementary to the WUA/IFIM
  pipeline.

This package defines the **abstract contract** every reference adapter
must implement so a single harness can drive the comparison. It does
NOT bundle PHABSIM / River2D / HABBY / FishXing binaries — those each
have their own licence and platform constraints (Wine for PHABSIM,
Windows-only for River2D, Linux/Python for HABBY, dead-but-public for
FishXing). v2.2.0 ships the **contract + scaffolding**; v3.x research
ships the actual reference runs.
"""
from __future__ import annotations

from .adapter import (
    ModelAdapter,
    OpenLimnoSelfAdapter,
    ReferenceResult,
    WUAComparison,
    compare_against,
    load_acceptance_threshold,
)

__all__ = [
    "ModelAdapter",
    "OpenLimnoSelfAdapter",
    "ReferenceResult",
    "WUAComparison",
    "compare_against",
    "load_acceptance_threshold",
]
