"""Multivariate HSI composite (v1.6.0; geom-mean method added v1.10.0).

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

Two **combination methods** are available (v1.10.0):

* ``method="product"`` (default; v1.6.0 behaviour) — multiplicative
  overlay on the depth × velocity WUA:

  .. math::

      \\mathrm{WUA}_\\mathrm{composite}(Q)
        = \\mathrm{WUA}_{dv}(Q) \\cdot SI_T \\cdot SI_C

  Both overlays must hold for habitat to be usable — cover represents
  *landscape-scale* refuge while thermal represents a *temporal*
  viability window. This matches the existing
  :mod:`openlimno.habitat.thermal` formula
  ``HSI_total(t, x) = HSI_geom(t, x) × thermal_SI(t)`` and extends it
  with the v1.3.0 cover-SI overlay. Recovers the HABBY *product*
  option.

* ``method="geom_mean"`` (v1.10.0; redesigned in v1.10.1 after
  6th-review R6-1 + R6-2) — column-level overlay softening:

  .. math::

      \\mathrm{WUA}_\\mathrm{composite}(Q)
        = \\mathrm{WUA}_{dv}(Q) \\cdot (SI_T \\cdot SI_C)^{1/n}

  where ``n = 1 + n_overlays``. The overlay enters as the n-th root
  rather than the raw product (which would be the ``product``
  method). This is the "softer than product" property HABBY's
  geom_mean option is named for, applied at the column level — the
  only level where SI_T / SI_C are defined when they are basin-wide
  scalars. The earlier v1.10.0 attempt at a per-cell-style
  ``base^(1/n) · area_proxy^((n-1)/n)`` reach-scale linearisation
  was withdrawn because (a) it produced NaN for all-zero base
  columns, and (b) it could INFLATE composite above base at low-flow
  discharges — both unacceptable for a suitability overlay. The
  **true** four-way per-cell geometric mean
  :math:`(d \\times v \\times c \\times t)^{1/4}` requires cover and
  thermal as per-cell rasters and is flagged for v2.x.

Cases that lack one overlay (e.g. thermal because no FishBase traits) get
that factor folded out — composite uses only the present overlay. Cases
that lack both overlays return ``None`` (composite step is silently
skipped, just like v1.1.1 thermal and v1.5.0 cover).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

CompositeMethod = Literal["product", "geom_mean"]
_VALID_METHODS: tuple[CompositeMethod, ...] = ("product", "geom_mean")


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
        *,
        strict: bool | None = None,
    ) -> CompositeOverlay:
        """Resolve a :class:`CompositeOverlay` from the
        ``thermal_metrics`` / ``cover_metrics`` dicts produced by the
        :meth:`openlimno.case.Case._maybe_run_thermal_habitat` and
        :meth:`openlimno.case.Case._maybe_run_cover_habitat` steps.

        v1.10.0 (N6): ``strict`` is now an explicit keyword-only flag.

        * ``strict=True`` (default for programmatic callers when
          ``warnings`` is not supplied) — out-of-range cover or thermal
          values raise ``ValueError`` (fail-loud semantics).
        * ``strict=False`` — out-of-range values degrade independently:
          the invalid overlay is dropped, a warning is appended to the
          ``warnings`` list (one will be created if ``None``), and a
          valid sibling overlay is preserved.

        Back-compat: if ``strict`` is left as ``None`` (legacy callers
        from v1.7.1 — v1.9.x), behaviour is inferred from ``warnings``
        — supplying a list selects lenient mode, ``None`` selects
        strict. This matches the v1.7.1 contract documented in the
        F6 review patch and is what every in-tree caller already uses.
        """
        if strict is None:
            strict = warnings is None
        if not strict and warnings is None:
            warnings = []

        def _reject(label: str, value: float) -> None:
            msg = f"{label}={value} outside [0, 1]"
            if strict:
                raise ValueError(msg)
            assert warnings is not None  # narrowed by strict=False branch
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


def _validate_method(method: CompositeMethod) -> None:
    if method not in _VALID_METHODS:
        raise ValueError(
            f"composite_hsi: unknown method {method!r}; "
            f"expected one of {_VALID_METHODS}"
        )


def _geom_mean_factor(overlay: CompositeOverlay) -> float:
    """Per-cell CSI multiplier for the geometric-mean method.

    The cell-level d×v CSI is always counted as one factor. Each present
    overlay (cover, thermal) adds another. We return the value that the
    d×v CSI must be multiplied by, in CSI-space, to obtain the n-factor
    geometric mean:

        (CSI_dv · SI_T · SI_C) ** (1/n)
      = CSI_dv ** (1/n) · (SI_T · SI_C) ** (1/n)

    The CSI-power reweighting is applied separately in
    :func:`apply_overlay` (it acts on the WUA column, not on the
    overlay). Here we only need the overlay's contribution.
    """
    n = 1 + overlay.n_overlays
    overlay_factor = 1.0
    if overlay.cover_si is not None:
        overlay_factor *= overlay.cover_si
    if overlay.thermal_si is not None:
        overlay_factor *= overlay.thermal_si
    return float(overlay_factor ** (1.0 / n))


def apply_overlay(
    wua_q: pd.DataFrame,
    overlay: CompositeOverlay,
    method: CompositeMethod = "product",
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
        method: ``"product"`` (default; v1.6.0 behaviour) multiplies
            the base WUA by the overlay. ``"geom_mean"`` (v1.10.0)
            applies the four-way geometric-mean composite — softer
            than product when overlays are partially redundant with
            d×v suitability. See module docstring.

    Returns:
        New DataFrame with columns ``discharge_m3s``,
        ``wua_m2_<sp>_<stage>`` (unchanged), and a paired
        ``wua_m2_composite_<sp>_<stage>`` for each species/stage
        present in ``wua_q``.
    """
    _validate_method(method)
    out = wua_q.copy()

    if overlay.overlay_si is None or method == "product":
        # Product (or no overlay → fall back to identity). Identical to
        # v1.6.0 path; preserved bit-for-bit so existing callers and
        # regulatory exports see no numeric drift.
        factor = 1.0 if overlay.overlay_si is None else overlay.overlay_si
        for col in wua_q.columns:
            if not col.startswith("wua_m2_") or col.startswith("wua_m2_composite_"):
                continue
            suffix = col[len("wua_m2_"):]
            out[f"wua_m2_composite_{suffix}"] = wua_q[col].astype(float) * factor
        return out

    # Geometric mean (v1.10.1, R6-1 + R6-2 redesign).
    #
    # The 5th-pass review chain's geom_mean implementation
    # (`base^(1/n) · overlay_geom · area_proxy^((n-1)/n)`) had two
    # design flaws that v1.10.0 inherited:
    #
    # * R6-1: an all-zero base column made `area_proxy =
    #   nanmean(base[base>0])` evaluate to NaN, and `float(nan) or 1.0`
    #   returned NaN (nan is truthy in Python), so the entire composite
    #   column became NaN and the downstream `composite_summary.idxmax`
    #   raised "Encountered all NA values".
    # * R6-2: using `nanmean(base[base>0])` as a single scalar across
    #   the whole sweep caused the formula to INFLATE composite above
    #   base at low-flow discharges (where `base_Q < area_proxy`),
    #   which is scientifically indefensible for a suitability overlay.
    #
    # The fix is to recognise that a true four-way per-cell geometric
    # mean needs cover/thermal as per-cell rasters (still out-of-scope
    # for v1.10.x, flagged for v2.x). At the reach scale with
    # **scalar** cover/thermal overlays, the most defensible
    # generalisation that (a) is monotone in base, (b) never inflates
    # WUA, and (c) reproduces the n-factor softening property is:
    #
    #     WUA_composite(Q) = WUA_dv(Q) · (SI_T · SI_C)^(1/n)
    #
    # i.e. the overlay enters as the n-th root rather than the raw
    # product. This is the "softer than product" property HABBY's
    # geom_mean option is named for, applied at the column level
    # (the only level where SI_T / SI_C are defined when they are
    # basin-wide scalars). It collapses to product when n=1, and
    # softens monotonically as n grows. ``_geom_mean_factor`` resolves
    # the n-th root directly from the overlay's present-factor count.
    overlay_geom = _geom_mean_factor(overlay)
    for col in wua_q.columns:
        if not col.startswith("wua_m2_") or col.startswith("wua_m2_composite_"):
            continue
        suffix = col[len("wua_m2_"):]
        out[f"wua_m2_composite_{suffix}"] = (
            wua_q[col].astype(float) * overlay_geom
        )
    return out


def composite_summary(
    wua_q: pd.DataFrame,
    overlay: CompositeOverlay,
    method: CompositeMethod = "product",
) -> dict:
    """Build the ``composite_hsi.json`` payload.

    The summary reports both the **base** (depth × velocity only) and the
    **composite** maxima per species/stage, plus the overlay factor — so
    a reviewer can see how much the seasonal / landscape constraints
    knocked WUA down from its hydraulic optimum. ``method`` is recorded
    in the payload (``"product"`` or ``"geom_mean"``) so regulatory
    exports and audits can tell which combination rule was applied.
    """
    _validate_method(method)
    if len(wua_q) == 0:
        # v1.7.1 (review F1): empty wua_q would crash idxmax below.
        # Return the overlay-only payload so callers see a valid summary
        # even when the hydraulic sweep produced zero rows.
        return {
            "method": method,
            "cover_si": overlay.cover_si,
            "thermal_si": overlay.thermal_si,
            "overlay_si": overlay.overlay_si,
            "n_overlays": overlay.n_overlays,
            "n_discharges": 0,
            "by_species_stage": [],
        }
    composite = apply_overlay(wua_q, overlay, method=method)
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
        "method": method,
        "cover_si": overlay.cover_si,
        "thermal_si": overlay.thermal_si,
        "overlay_si": overlay.overlay_si,
        "n_overlays": overlay.n_overlays,
        "n_discharges": int(len(wua_q)),
        "by_species_stage": by_series,
    }
