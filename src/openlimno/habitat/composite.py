"""Multivariate HSI composite (v1.6.0).

Combines four habitat suitability dimensions into a single composite WUA
per discharge:

* **depth × velocity** — per-cell CSI from HSI curves, already aggregated
  into ``wua_m2`` by :mod:`openlimno.habitat.wua` (geometric-mean composite
  by default; SPEC §4.2.2.2).
* **thermal** — basin-wide scalar :math:`SI_T \\in [0, 1]`, the period-mean
  of :func:`openlimno.habitat.thermal.thermal_suitability_series` against
  FishBase preferred range.
* **cover** — basin-wide scalar :math:`SI_C \\in [0, 1]`, the watershed-mean
  cover SI from :func:`openlimno.habitat.cover.watershed_cover_si`.

The composite treats temporal and landscape suitabilities as **scalar
multiplicative overlays** on the per-cell hydraulic habitat:

.. math::

    \\mathrm{WUA}_\\mathrm{composite}(Q)
      = \\mathrm{WUA}_{dv}(Q) \\cdot SI_T \\cdot SI_C

This matches the formula already documented in
:mod:`openlimno.habitat.thermal`::

    HSI_total(t, x) = HSI_geom(t, x) × thermal_SI(t)

and extends it with the v1.3.0 cover-SI overlay. The two overlays are
multiplicatively independent — combine semantics is `multiply`, not a
geometric mean — because cover represents *landscape-scale* refuge while
thermal represents a *temporal* viability window; both must hold for
habitat to be usable.

**Context vs. other tools** (v1.7.1, review F4): the multiplicative
product is the **product** option in HABBY's three-method menu (product,
geometric mean, arithmetic mean — see HABBY's habitat-calculation
reference). PHABSIM's life-stage HSI tradition allows several
combination methods too (Bovee 1986). This module picks *product*
deliberately for the basin-scale cover/thermal overlay case (both
factors are scalars over the reach, not per-cell suitabilities), but
does **not** claim that "the PHABSIM/HABBY convention" mandates this
choice. Users who want a per-cell four-variable geometric mean
:math:`(d \\times v \\times c \\times t)^{1/4}` need cover and thermal
exposed as per-cell rasters first — out of scope for v1.6.0/v1.7.x;
flagged for future research.

Cases that lack one overlay (e.g. thermal because no FishBase traits) get
that factor folded out — composite uses only the present overlay. Cases
that lack both overlays return ``None`` (composite step is silently
skipped, just like v1.1.1 thermal and v1.5.0 cover).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class CompositeOverlay:
    """Resolved scalar overlay carrying provenance for reporting.

    Attributes:
        cover_si: Basin-wide cover suitability ∈ [0, 1], or ``None`` if
            the cover_habitat step was skipped.
        thermal_si: Period-mean thermal suitability ∈ [0, 1], or ``None``
            if the thermal_habitat step was skipped.
        overlay_si: Combined scalar :math:`SI_T \\cdot SI_C` (or single
            factor if only one overlay is present). ``None`` if both
            are absent.
    """

    cover_si: float | None
    thermal_si: float | None
    overlay_si: float | None

    @property
    def n_overlays(self) -> int:
        return int(self.cover_si is not None) + int(self.thermal_si is not None)

    @classmethod
    def from_metrics(
        cls,
        thermal_metrics: dict | None,
        cover_metrics: dict | None,
        warnings: list[str] | None = None,
    ) -> CompositeOverlay:
        """Resolve a :class:`CompositeOverlay` from the
        ``thermal_metrics`` / ``cover_metrics`` dicts produced by the
        :meth:`openlimno.case.Case._maybe_run_thermal_habitat` and
        :meth:`openlimno.case.Case._maybe_run_cover_habitat` steps.

        v1.7.1 (review F6): when ``warnings`` is supplied (pipeline
        path), out-of-range cover or thermal values degrade
        independently — the invalid overlay is dropped and a warning
        is appended, but a valid sibling overlay is preserved. When
        ``warnings`` is ``None`` (programmatic API), out-of-range
        values still raise ``ValueError`` for fail-loud semantics.
        """
        def _reject(label: str, value: float) -> None:
            msg = f"{label}={value} outside [0, 1]"
            if warnings is None:
                raise ValueError(msg)
            warnings.append(
                f"composite_hsi: dropped invalid {label} ({value}); "
                f"falling back to the other overlay if available."
            )

        cover_si: float | None = None
        if isinstance(cover_metrics, dict) and "mean_si" in cover_metrics:
            raw_cover = cover_metrics["mean_si"]
            if raw_cover == raw_cover and raw_cover is not None:  # NaN-safe
                cover_si = float(raw_cover)
                if not 0.0 <= cover_si <= 1.0:
                    _reject("cover_metrics.mean_si", cover_si)
                    cover_si = None

        thermal_si: float | None = None
        if isinstance(thermal_metrics, dict) and "mean_SI" in thermal_metrics:
            raw = thermal_metrics["mean_SI"]
            # thermal_metrics may emit NaN when the climate window held
            # zero rows; treat that as "no overlay" rather than NaN-poisoning
            # the composite.
            if raw == raw and raw is not None:  # NaN-safe
                thermal_si = float(raw)
                if not 0.0 <= thermal_si <= 1.0:
                    _reject("thermal_metrics.mean_SI", thermal_si)
                    thermal_si = None

        if cover_si is None and thermal_si is None:
            return cls(cover_si=None, thermal_si=None, overlay_si=None)

        overlay = 1.0
        if cover_si is not None:
            overlay *= cover_si
        if thermal_si is not None:
            overlay *= thermal_si
        return cls(
            cover_si=cover_si,
            thermal_si=thermal_si,
            overlay_si=float(overlay),
        )


def apply_overlay(
    wua_q: pd.DataFrame,
    overlay: CompositeOverlay,
) -> pd.DataFrame:
    """Apply the scalar overlay to a base depth × velocity WUA-Q table.

    Args:
        wua_q: DataFrame with columns ``discharge_m3s`` and one or more
            ``wua_m2_<species>_<stage>`` columns from
            :func:`openlimno.habitat.wua.wua_q_curve` /
            :meth:`Case._compute_cell_wua`.
        overlay: Resolved :class:`CompositeOverlay`. If
            ``overlay.overlay_si is None``, a copy of ``wua_q`` is
            returned unchanged (no overlay applied) plus a
            ``wua_m2_composite_*`` column equal to the base.

    Returns:
        New DataFrame with columns ``discharge_m3s``,
        ``wua_m2_<sp>_<stage>`` (unchanged), and a paired
        ``wua_m2_composite_<sp>_<stage>`` = base × overlay_si for each
        species/stage present in ``wua_q``.
    """
    out = wua_q.copy()
    factor = 1.0 if overlay.overlay_si is None else overlay.overlay_si
    for col in wua_q.columns:
        if not col.startswith("wua_m2_") or col.startswith("wua_m2_composite_"):
            continue
        suffix = col[len("wua_m2_"):]
        out[f"wua_m2_composite_{suffix}"] = wua_q[col].astype(float) * factor
    return out


def composite_summary(
    wua_q: pd.DataFrame,
    overlay: CompositeOverlay,
) -> dict:
    """Build the ``composite_hsi.json`` payload.

    The summary reports both the **base** (depth × velocity only) and the
    **composite** maxima per species/stage, plus the overlay factor — so
    a reviewer can see how much the seasonal / landscape constraints
    knocked WUA down from its hydraulic optimum.
    """
    if len(wua_q) == 0:
        # v1.7.1 (review F1): empty wua_q would crash idxmax below.
        # Return the overlay-only payload so callers see a valid summary
        # even when the hydraulic sweep produced zero rows.
        return {
            "cover_si": overlay.cover_si,
            "thermal_si": overlay.thermal_si,
            "overlay_si": overlay.overlay_si,
            "n_overlays": overlay.n_overlays,
            "n_discharges": 0,
            "by_species_stage": [],
        }
    composite = apply_overlay(wua_q, overlay)
    base_cols = [
        c for c in wua_q.columns
        if c.startswith("wua_m2_") and not c.startswith("wua_m2_composite_")
    ]
    by_series: list[dict] = []
    for col in base_cols:
        suffix = col[len("wua_m2_"):]
        comp_col = f"wua_m2_composite_{suffix}"
        base_max = float(wua_q[col].max())
        comp_max = float(composite[comp_col].max())
        # Identify the discharge at which the composite WUA peaks. For a
        # pure multiplicative overlay this is identical to the base
        # argmax — but the join with the base table is computed
        # explicitly so future overlays that aren't constant-in-Q remain
        # consistent.
        argmax_idx = composite[comp_col].idxmax()
        q_at_max = float(composite.loc[argmax_idx, "discharge_m3s"])
        by_series.append({
            "species_stage": suffix,
            "wua_m2_base_max": base_max,
            "wua_m2_composite_max": comp_max,
            "discharge_m3s_at_composite_max": q_at_max,
            "composite_to_base_ratio": (
                comp_max / base_max if base_max > 0 else None
            ),
        })
    return {
        "cover_si": overlay.cover_si,
        "thermal_si": overlay.thermal_si,
        "overlay_si": overlay.overlay_si,
        "n_overlays": overlay.n_overlays,
        "n_discharges": int(len(wua_q)),
        "by_species_stage": by_series,
    }
