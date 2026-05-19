"""Case orchestrator. SPEC §8.1.

Loads a case YAML, validates it against WEDM, drives the configured solver,
runs habitat post-processing, and writes outputs + provenance.

M1 capability: builtin-1d hydraulics + WUA (cell-level) + WUA-Q sweep.
M2+ extends to SCHISM 2D, multi-scale aggregation, regulatory exports.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import socket
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias

import numpy as np
import pandas as pd
import yaml

from openlimno import __version__
from openlimno.habitat import (
    cell_wua,
    composite_csi,
    load_hsi_from_parquet,
    require_independence_ack,
)
from openlimno.habitat.hsi import HSICurve
from openlimno.hydro.builtin_1d import (
    Builtin1D,
    CrossSection,
    load_sections_from_parquet,
)
from openlimno.wedm import validate_case

if TYPE_CHECKING:
    from openlimno.habitat.composite import CompositeOverlay

PerCellCsiMap: TypeAlias = dict[
    tuple[float, str, str], tuple[np.ndarray, np.ndarray]
]


@dataclass
class CaseRunResult:
    """Container for end-to-end case results."""

    case_name: str
    case_dir: Path
    output_dir: Path
    sections: list[CrossSection]
    discharges_m3s: list[float]
    hydraulic_results: dict[float, list[Any]]  # Q -> list[MANSQResult]
    wua_q: pd.DataFrame  # columns: discharge_m3s, wua_m2_<sp>_<stage>, ...
    provenance_path: Path
    warnings: list[str] = field(default_factory=list)
    # v1.8.0 (review F7): composite WUA-Q DataFrame when at least one
    # scalar overlay (cover or thermal) was applied. None for v1.0.x-
    # style cases without fetched data. Notebook users can now access
    # composite values directly without round-tripping through
    # composite_wua_q.parquet.
    composite_wua_q: pd.DataFrame | None = None
    composite_summary: dict | None = None

    def summary(self) -> str:
        return (
            f"Case '{self.case_name}': {len(self.discharges_m3s)} flows × "
            f"{len(self.sections)} sections; outputs in {self.output_dir}"
        )


@dataclass
class Case:
    """End-to-end OpenLimno case driver."""

    config: dict[str, Any]
    case_yaml_path: Path

    @classmethod
    def from_yaml(cls, path: str | Path) -> Case:
        path = Path(path).resolve()
        errors = validate_case(path)
        if errors:
            raise ValueError("Case YAML failed schema validation:\n  - " + "\n  - ".join(errors))
        with path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return cls(config=config, case_yaml_path=path)

    @property
    def name(self) -> str:
        return self.config["case"]["name"]

    @property
    def case_dir(self) -> Path:
        return self.case_yaml_path.parent

    def run(
        self,
        discharges_m3s: list[float] | None = None,
        slope: float = 0.002,
        manning_n: float = 0.035,
        studyplan_path: str | Path | None = None,
        discharge_series_path: str | Path | None = None,
    ) -> CaseRunResult:
        """Drive the full 1.0 pipeline end-to-end.

        Stages:
            1. Load cross-sections + HSI curves + life_stage TUF defaults
            2. Optional studyplan (TUF override / acknowledged uncertainties)
            3. Hydraulics via HydroSolver Protocol (builtin-1d or schism)
            4. Habitat: cell-level WUA-Q + HMU multi-scale aggregation
            5. Drift egg evaluation (if metric=drifting-egg or species opts in)
            6. Regulatory exports (if `regulatory_export` in case YAML)
            7. Provenance + outputs (NetCDF/CSV/Parquet)
        """
        warnings: list[str] = []
        cfg = self.config
        case_dir = self.case_dir

        # Discharges
        if discharges_m3s is None:
            discharges_m3s = [float(q) for q in np.logspace(0, 1.5, 8)]

        # 1. Load cross-sections
        cross_section_path = self._resolve(
            cfg.get("data", {}).get("cross_section", "../../data/lemhi/cross_section.parquet")
        )
        sections = load_sections_from_parquet(cross_section_path, manning_n=manning_n)

        # 2. Load HSI curves
        hsi_path = self._resolve(
            cfg.get("data", {}).get("hsi_curve", "../../data/lemhi/hsi_curve.parquet")
        )
        hsi_curves = load_hsi_from_parquet(hsi_path)

        # 3. Run hydraulics (sweep) via HydroSolver Protocol
        backend = cfg["hydrodynamics"]["backend"]
        out_dir = self._resolve(cfg["output"]["dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        hydro_work = out_dir / f"hydro_work_{backend}"
        hydro_work.mkdir(parents=True, exist_ok=True)

        # Resolve + validate UGRID mesh if mesh.uri given. SCHISM needs it;
        # builtin-1d ignores it but a malformed mesh is still a project bug
        # we want flagged early.
        mesh_path = self._resolve_mesh_uri(cfg, warnings)

        if backend == "builtin-1d":
            solver = Builtin1D(slope=slope)
            solver.prepare(
                self.case_yaml_path,
                hydro_work,
                sections=sections,
                discharges_m3s=list(discharges_m3s),
            )
            solver.run(hydro_work)
            hydraulic_results = solver.read_results(hydro_work)
        elif backend == "schism":
            from openlimno.hydro import SCHISMAdapter

            schism_cfg = cfg["hydrodynamics"].get("schism", {})
            adapter = SCHISMAdapter(
                executable=schism_cfg.get("executable"),
                container_image=schism_cfg.get("container_image"),
                container_runtime=schism_cfg.get("container_runtime", "docker"),
                n_procs=schism_cfg.get("n_procs", 1),
                timeout_s=schism_cfg.get("timeout_s"),
            )
            adapter.prepare(
                self.case_yaml_path,
                hydro_work,
                wedm_mesh_path=mesh_path,
            )
            dry = bool(schism_cfg.get("dry_run", False))
            report = adapter.run(hydro_work, dry_run=dry)
            warnings.append(
                f"SCHISM run finished: rc={report.return_code}, "
                f"dry_run={report.dry_run}, log={report.log_path.name}"
            )
            if dry or report.return_code != 0:
                # Fall back to Builtin1D approximation so the rest of the
                # pipeline still produces output (useful for CI without SCHISM)
                solver = Builtin1D(slope=slope)
                solver.prepare(
                    self.case_yaml_path,
                    hydro_work,
                    sections=sections,
                    discharges_m3s=list(discharges_m3s),
                )
                solver.run(hydro_work)
                hydraulic_results = solver.read_results(hydro_work)
                warnings.append(
                    "SCHISM unavailable / dry-run — fell back to Builtin1D "
                    "for habitat post-processing"
                )
            else:
                # Real SCHISM result reading lands in M3 beta;
                # for now treat it as an approximation
                hydraulic_results = adapter.read_results(hydro_work)  # type: ignore[assignment]
        else:
            raise NotImplementedError(
                f"Unknown hydrodynamics backend '{backend}'. Supported: builtin-1d, schism."
            )

        # 4. Habitat (cell WUA-Q for each species/stage)
        habitat_cfg = cfg["habitat"]
        composite = habitat_cfg.get("composite", "geometric_mean")
        ack = bool(habitat_cfg.get("acknowledge_independence", False))
        # Hard guard before computing anything
        require_independence_ack(composite, ack)  # type: ignore[arg-type]

        species_list = habitat_cfg["species"]
        stage_list = habitat_cfg["stages"]
        # v2.4.0: capture per-cell CSI arrays alongside the reach
        # total so the geom_mean_per_cell composite path in
        # _maybe_run_composite_hsi can call apply_overlay_per_cell
        # directly. Memory overhead is negligible (one float array
        # per (Q, sp, stage) at section granularity).
        composite_overlay_method_for_capture = habitat_cfg.get(
            "composite_overlay_method", "product",
        )
        capture_per_cell = composite_overlay_method_for_capture == "geom_mean_per_cell"
        per_cell_csi: PerCellCsiMap = {}
        # v2.5.1 (R8-5): load optional pre-computed per-section thermal SI
        # array from ``data.thermal_si_per_section.uri`` (CSV with
        # ``station_m`` + ``thermal_si`` columns). Users build it via
        # ``openlimno.habitat.thermal_si_per_section(temperature_raster,
        # [section_geoms], ThermalRange)`` offline and reference it from
        # case.yaml — the Case.run pipeline then passes the array (not
        # a scalar broadcast) through to apply_overlay_per_cell, closing
        # the per-cell raster-overlay YAML path the v2.0.0 charter
        # promised.
        # v2.6.0 priority: try inline raster + section_locations first
        # (zero-step user path); fall back to v2.5.1 pre-computed CSV;
        # else None → scalar broadcast as before.
        per_section_thermal_si = self._maybe_compute_per_section_thermal_si_from_raster(
            cfg, sections, warnings,
        )
        # v2.6.1 (R9-4): treat empty arrays as "not present" so the
        # CSV fallback fires when the raster path silently produces
        # a zero-length result (edge case: 0 sections, malformed
        # CSV that loaded as empty, etc.). ``len()`` on numpy arrays
        # is well-defined for 1-D.
        if per_section_thermal_si is None or len(per_section_thermal_si) == 0:
            per_section_thermal_si = self._maybe_load_per_section_thermal_si(
                cfg, sections, warnings,
            )

        # v2.7.0: symmetric per-section cover SI pipeline (mirrors
        # the v2.6.0 thermal raster path). Priority order is the
        # same: inline LULC raster (zero-step) → pre-computed CSV →
        # scalar broadcast (the v1.5.0 watershed_cover_si path).
        per_section_cover_si = self._maybe_compute_per_section_cover_si_from_raster(
            cfg, sections, warnings,
        )
        if per_section_cover_si is None or len(per_section_cover_si) == 0:
            per_section_cover_si = self._maybe_load_per_section_cover_si(
                cfg, sections, warnings,
            )

        wua_records: list[dict[str, Any]] = []
        for Q in discharges_m3s:
            row: dict[str, Any] = {"discharge_m3s": Q}
            for species in species_list:
                for stage in stage_list:
                    if capture_per_cell:
                        csi_arr, area_arr = self._compute_cell_csi_and_area(
                            hydraulic_results[Q],
                            hsi_curves,
                            species,
                            stage,
                            composite=composite,
                            ack=ack,
                            warnings=warnings,
                        )
                        if csi_arr is None:
                            wua_value = 0.0
                        else:
                            per_cell_csi[(Q, species, stage)] = (csi_arr, area_arr)
                            wua_value = float(cell_wua(csi_arr, area_arr))
                    else:
                        wua_value = self._compute_cell_wua(
                            hydraulic_results[Q],
                            hsi_curves,
                            species,
                            stage,
                            composite=composite,
                            ack=ack,
                            warnings=warnings,
                        )
                    col = f"wua_m2_{species}_{stage}"
                    row[col] = wua_value
            wua_records.append(row)

        wua_df = pd.DataFrame(wua_records)

        # 4b. HMU multi-scale aggregation (SPEC §4.2.3.2-3)
        hmu_df = self._aggregate_hmu(
            hydraulic_results,
            hsi_curves,
            species_list,
            stage_list,
            composite=composite,
            ack=ack,
            warnings=warnings,
        )

        # 4c. StudyPlan TUF override (SPEC §4.4.1.1)
        sp_obj = self._load_studyplan(studyplan_path, warnings)

        # 4d. Drift egg evaluation (SPEC §4.2.6) - only if explicitly requested
        # (return value unused at this layer; auto-writes drift_egg.csv to out_dir)
        self._maybe_drift_egg(
            cfg,
            hydraulic_results,
            sections,
            out_dir,
            warnings,
        )

        # 5. Outputs
        formats = cfg["output"]["formats"]
        # Watermark header for tentative HSI (computed below; pass to writers)
        wua_quality_grade = self._compute_wua_quality(
            hsi_curves,
            species_list,
            stage_list,
            warnings,
        )
        watermark_header = self._wua_csv_header(wua_quality_grade) if "csv" in formats else None
        if "csv" in formats:
            self._write_csv_with_header(wua_df, out_dir / "wua_q.csv", watermark_header)
            if hmu_df is not None and len(hmu_df) > 0:
                self._write_csv_with_header(hmu_df, out_dir / "wua_hmu.csv", watermark_header)
        if "parquet" in formats:
            self._atomic_write(
                out_dir / "wua_q.parquet",
                lambda p: wua_df.to_parquet(p, index=False),
            )
            if hmu_df is not None and len(hmu_df) > 0:
                self._atomic_write(
                    out_dir / "wua_hmu.parquet",
                    lambda p: hmu_df.to_parquet(p, index=False),
                )
        if "netcdf" in formats:
            self._write_hydraulic_netcdf(hydraulic_results, sections, out_dir / "hydraulics.nc")

        # 5b. (Regulatory exports moved below 5c-5e in v1.7.0 so they can
        # see the composite WUA-Q overlay; this comment preserved as a
        # signpost for readers expecting the old order.)

        # 5c. Thermal habitat suitability (v1.1.1). If the case carries
        # both data.fishbase_traits + data.climate, evaluate a daily
        # thermal SI series + summary metrics — closes the
        # fetcher × habitat loop. Both blocks are optional; skip
        # silently if either is missing (v1.0.x cases without
        # fetched data still run unchanged).
        thermal_metrics_dict: dict | None = None
        try:
            thermal_metrics_dict = self._maybe_run_thermal_habitat(
                cfg, case_dir, out_dir, warnings,
            )
        except Exception as e:  # noqa: BLE001
            # Thermal is auxiliary — never fail the run; surface
            # the error as a warning so reviewers can investigate.
            warnings.append(
                f"thermal_habitat step failed: {e!r}. Skipping; "
                f"the WUA-Q pipeline remains valid."
            )

        # 5d. Cover habitat suitability (v1.5.0). If the case carries
        # both data.lulc + data.watershed, compute a watershed-mean
        # cover SI from the WorldCover raster — mirrors the v1.1.1
        # thermal pattern for the v1.3.0 cover SI module.
        cover_metrics_dict: dict | None = None
        try:
            cover_metrics_dict = self._maybe_run_cover_habitat(
                cfg, case_dir, out_dir, warnings,
            )
        except Exception as e:  # noqa: BLE001
            warnings.append(
                f"cover_habitat step failed: {e!r}. Skipping; "
                f"the WUA-Q pipeline remains valid."
            )

        # 5e. Multivariate HSI composite (v1.6.0; geom_mean added v1.10.0).
        # If at least one scalar overlay (cover or thermal) is available,
        # emit the composite WUA-Q overlay tables. Skipped silently when
        # neither overlay was computed.
        composite_overlay_method = habitat_cfg.get(
            "composite_overlay_method", "product",
        )
        composite_summary_dict: dict | None = None
        composite_df: pd.DataFrame | None = None
        # v2.6.1 (R9-7): if a per-section thermal SI array was loaded
        # (either inline raster path or v2.5.1 CSV path) but no scalar
        # ``thermal_metrics_dict`` was produced (no ``data.climate``),
        # synthesise a scalar mean so ``CompositeOverlay.from_metrics``
        # treats thermal as a present overlay. Without this, a
        # case carrying ``data.thermal_raster`` + ``data.section_locations``
        # but no ``data.climate`` would have
        # ``CompositeOverlay.from_metrics(None, ...)`` → overlay_si =
        # None → ``_maybe_run_composite_hsi`` returns early, silently
        # skipping the entire composite step — defeating the v2.6.0
        # charter promise that thermal_raster alone drives composite.
        effective_thermal_metrics = thermal_metrics_dict
        if (
            effective_thermal_metrics is None
            and per_section_thermal_si is not None
            and len(per_section_thermal_si) > 0
        ):
            effective_thermal_metrics = {
                "mean_SI": float(np.mean(per_section_thermal_si)),
                "source": "per_section_thermal_si (v2.6.1 R9-7 synth)",
            }
        # v2.7.0: symmetric synth for cover_metrics_dict so a case
        # carrying ``data.cover_raster`` + ``data.section_locations``
        # alone (no ``data.lulc`` + ``data.watershed``) still drives
        # the composite step. Same pattern as the v2.6.1 R9-7 thermal
        # synth.
        effective_cover_metrics = cover_metrics_dict
        if (
            effective_cover_metrics is None
            and per_section_cover_si is not None
            and len(per_section_cover_si) > 0
        ):
            effective_cover_metrics = {
                "mean_si": float(np.mean(per_section_cover_si)),
                "source": "per_section_cover_si (v2.7.0 synth)",
            }
        try:
            composite_summary_dict, composite_df = (
                self._maybe_run_composite_hsi(
                    wua_df,
                    effective_thermal_metrics,
                    effective_cover_metrics,
                    out_dir,
                    formats,
                    warnings,
                    method=composite_overlay_method,
                    per_cell_csi=per_cell_csi if capture_per_cell else None,
                    per_section_thermal_si=per_section_thermal_si,
                    per_section_cover_si=per_section_cover_si,
                )
            )
        except Exception as e:  # noqa: BLE001
            warnings.append(
                f"composite_hsi step failed: {e!r}. Skipping; the "
                f"WUA-Q pipeline remains valid."
            )

        # 5f. Regulatory exports (SPEC §4.2.4.2 / ADR-0009). Runs LAST
        # (was step 5b through v1.6.x) so it can see the composite
        # WUA-Q from step 5e and emit paired `<kind>_composite.csv`
        # variants alongside the base reports when overlays exist.
        reg_exports = cfg.get("regulatory_export", [])
        if reg_exports:
            self._run_regulatory_exports(
                reg_exports,
                wua_df,
                species_list,
                stage_list,
                out_dir,
                discharge_series_path,
                warnings,
                composite_df=composite_df,
                composite_summary=composite_summary_dict,
                wua_quality_grade=wua_quality_grade,
            )

        # 6. HSI watermarking warning (already computed above for CSV header)
        if wua_quality_grade == "C":
            warnings.append(
                "WUA computed using ≥1 C-grade HSI curve — outputs are TENTATIVE. "
                "Run `openlimno hsi upgrade` to improve metadata."
            )

        # 7. Provenance
        prov_path = out_dir / "provenance.json"
        provenance = self._build_provenance(
            discharges_m3s,
            sections,
            species_list,
            stage_list,
            warnings,
            studyplan=sp_obj,
            wua_quality_grade=wua_quality_grade,
            data_paths={
                "cross_section": cross_section_path,
                "hsi_curve": hsi_path,
            },
            thermal_metrics_dict=thermal_metrics_dict,
            cover_metrics_dict=cover_metrics_dict,
            composite_summary_dict=composite_summary_dict,
        )
        self._atomic_write(
            prov_path,
            lambda p: p.write_text(
                json.dumps(provenance, indent=2, default=str),
                encoding="utf-8",
            ),
        )

        return CaseRunResult(
            case_name=self.name,
            case_dir=case_dir,
            output_dir=out_dir,
            sections=sections,
            discharges_m3s=discharges_m3s,
            hydraulic_results=hydraulic_results,
            wua_q=wua_df,
            provenance_path=prov_path,
            warnings=warnings,
            composite_wua_q=composite_df,
            composite_summary=composite_summary_dict,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _resolve(self, p: str | Path) -> Path:
        """Resolve a path: absolute as-is, else relative to case YAML directory."""
        path = Path(p)
        if not path.is_absolute():
            path = (self.case_dir / path).resolve()
        return path

    # v2.11.0 path-safety sandbox (R11-4 prototype) — patched in
    # v2.11.1 per 12th-round review:
    #   R12-1: expanduser() so '~/openlimno-data' works as documented
    #   R12-2: normalize absolute candidates so /case/../secret.csv
    #          can't bypass the sandbox via lexical-only matching
    #   R12-3: explicit empty allowed_data_roots: [] now means
    #          "lock to case dir only" (NOT permissive)
    #   R12-7: dropped the dead except clause (Py >= 3.11 pinned)
    #   R12-8: URL-scheme URIs (http://, s3://, …) explicitly rejected
    #   R12-9: single source of truth for the config-traversal

    # URI-scheme detector (R12-8). Matches RFC 3986 §3.1 scheme syntax
    # plus the "//" authority marker, so Windows drive letters
    # (``C:\foo``) are NOT classified as URL schemes.
    _URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")

    def _get_allowed_data_roots_raw(self) -> list[Any] | None:
        """v2.11.1 R12-9: single source of truth for reading
        ``case.allowed_data_roots`` out of the config. Returns the
        raw list (with whatever YAML-supplied content) or ``None``
        when the user hasn't set the key at all.

        The distinction between ``None`` (key absent) and ``[]``
        (key explicitly empty) matters for R12-3: an empty list now
        means "lock to case dir only," not "use permissive mode."
        """
        case_section = self.config.get("case", {})
        if "allowed_data_roots" not in case_section:
            return None
        return case_section["allowed_data_roots"]

    def _allowed_data_roots(self) -> list[Path]:
        """v2.11.0/v2.11.1 path-safety sandbox helper. Return the
        absolute-resolved list of directories that ``_resolve_safe``
        will permit data URIs to point at.

        Always includes the case dir itself first (the implicit
        root). Entries from ``case.allowed_data_roots`` are appended;
        relative entries are anchored on the case dir, absolute
        entries (including ``~``-prefixed ones, which are expanded
        via ``Path.expanduser`` per R12-1) are taken verbatim.
        """
        roots = [self.case_dir.resolve()]
        raw = self._get_allowed_data_roots_raw() or []
        for entry in raw:
            p = Path(entry).expanduser()  # R12-1
            roots.append(
                p.resolve() if p.is_absolute()
                else (self.case_dir / p).resolve()
            )
        return roots

    def _resolve_safe(
        self,
        uri: str | Path,
        *,
        allow_outside_case: bool = False,
    ) -> Path:
        """Path-safety sandbox (R11-4 prototype, v2.11.0; tightened in v2.11.1).

        Resolve a YAML-supplied URI like ``_resolve``, BUT — when
        ``case.allowed_data_roots`` is declared in the YAML — reject
        any resolved path that escapes both the case directory and
        every entry in ``allowed_data_roots``.

        Args:
            uri: Path or URI string from the case YAML (the kind of
                value ``data.thermal_raster.uri`` or
                ``boundaries.upstream.series`` carries).
            allow_outside_case: Explicit per-call escape hatch for
                legitimate cases that need to reach outside the
                sandbox (e.g. a fetcher writing to a system temp
                dir). The caller still gets a normal resolved Path;
                the sandbox is skipped entirely. Default ``False``.

        Returns:
            Absolute, fully-resolved ``Path``.

        Raises:
            ValueError: when one of the following is true:
                (a) The URI is a URL-scheme string (``http://``,
                    ``s3://``, etc.) — these are out of scope for
                    the local-filesystem sandbox (R12-8); reject
                    eagerly with a clear message rather than treat
                    them as relative-path strings.
                (b) ``case.allowed_data_roots`` is declared (even as
                    an empty list, per R12-3) AND
                    ``allow_outside_case=False`` AND the fully-
                    resolved candidate path is outside every root.

        Back-compat: when ``case.allowed_data_roots`` is UNSET (key
        absent from the YAML), this method is exactly equivalent to
        ``_resolve(uri)``. v3.0 will route the existing ``_resolve``
        call sites through this wrapper and tighten the back-compat
        path. v2.11.x establishes the API surface AND, as of
        v2.11.1, sandbox-routes one real engine call site
        (``_resolve_mesh_uri``) so the API is no longer dead code.
        """
        # R12-8: reject URL-scheme URIs up front. Detecting these
        # before _resolve() prevents a downstream consumer from
        # silently treating ``http://attacker/x`` as a relative path
        # that gets joined onto the case dir.
        if isinstance(uri, str) and self._URL_SCHEME_RE.match(uri):
            raise ValueError(
                f"v2.11.0 path-safety: URI {uri!r} carries a URL "
                f"scheme (http/https/s3/etc.); this resolver only "
                f"handles local-filesystem paths. Either dereference "
                f"the URL outside the case YAML (download then point "
                f"at the local file) or wait for v3.x to add URL-"
                f"scheme handlers."
            )
        # R12-2: fully resolve the candidate path BEFORE the
        # containment check. _resolve() only calls .resolve() on
        # relative paths, so a YAML carrying an absolute URI with
        # ``..`` or symlink components (e.g.
        # ``/case_dir/../etc/passwd``) would otherwise be matched
        # lexically against the case dir and slip through.
        resolved = Path(self._resolve(uri)).resolve()
        if allow_outside_case:
            return resolved
        raw = self._get_allowed_data_roots_raw()
        if raw is None:
            # Sandbox is opt-in: the YAML didn't declare any roots
            # → back-compat permissive resolution. v3.0 may change
            # this default. R12-3: this is the ONLY permissive path
            # now; an explicit empty list falls through to the
            # strict branch below (case dir only).
            return resolved
        roots = self._allowed_data_roots()
        for root in roots:
            if resolved.is_relative_to(root):
                return resolved
        raise ValueError(
            f"v2.11.0 path-safety: URI {uri!r} resolved to "
            f"{resolved} which is outside every entry in "
            f"case.allowed_data_roots. Allowed roots (case dir + "
            f"configured): {[str(r) for r in roots]}. Either move "
            f"the data inside one of these roots, add the directory "
            f"to case.allowed_data_roots, or pass "
            f"allow_outside_case=True at the call site if this URI "
            f"is intentionally extra-case (e.g. a system temp dir "
            f"or write target)."
        )

    def _resolve_mesh_uri(self, cfg: dict[str, Any], warnings: list[str]) -> Path | None:
        """Resolve and validate ``cfg["mesh"]["uri"]`` (UGRID-2D NetCDF).

        Returns the resolved path on success, ``None`` if mesh missing or
        invalid (warnings recorded). Always non-fatal — builtin-1d does not
        require a mesh, and SCHISM falls back to a placeholder grid.
        """
        mesh_cfg = cfg.get("mesh", {})
        uri = mesh_cfg.get("uri")
        if not uri:
            return None
        # v2.11.1 R12-4: route through _resolve_safe so the v2.11.0
        # sandbox API isn't dead logic. With case.allowed_data_roots
        # unset (every shipped fixture), this falls through to the
        # same _resolve() call _resolve_safe wraps — zero behavior
        # change. Cases that DO opt in now get sandboxing on the
        # mesh URI for free, and we have at least one real engine
        # call site exercising the API.
        try:
            path = self._resolve_safe(uri)
        except ValueError as e:
            warnings.append(
                f"mesh.uri rejected by path-safety sandbox: {e}"
            )
            return None
        if not path.exists():
            warnings.append(f"mesh.uri does not exist: {path}")
            return None
        try:
            from openlimno.preprocess import validate_ugrid_mesh

            report = validate_ugrid_mesh(path)
        except Exception as e:
            warnings.append(f"mesh validation failed: {e}")
            return path
        if not report.is_valid:
            warnings.append("UGRID mesh validation FAILED: " + "; ".join(report.errors))
            return None
        if report.warnings:
            warnings.append(f"UGRID mesh warnings ({path.name}): " + "; ".join(report.warnings))
        warnings.append(f"Mesh OK: {report.n_nodes} nodes, {report.n_faces} faces ({path.name})")
        return path

    def _aggregate_hmu(
        self,
        hydraulic_results: dict[float, list[Any]],
        hsi_curves: dict[tuple[str, str, str], HSICurve],
        species_list: list[str],
        stage_list: list[str],
        composite: str,
        ack: bool,
        warnings: list[str],
    ) -> pd.DataFrame | None:
        """Aggregate WUA by HMU type at each Q (SPEC §4.2.3.2)."""
        from openlimno.habitat import (
            aggregate_wua_by_hmu,
            classify_reach,
            composite_csi,
        )

        rows: list[dict[str, Any]] = []
        for Q, results in hydraulic_results.items():
            depths = np.array([r.depth_mean_m for r in results])
            velocities = np.array([r.velocity_mean_ms for r in results])
            areas = np.array([r.area_m2 for r in results])
            labels = classify_reach(velocities, depths)

            for species in species_list:
                for stage in stage_list:
                    suits = {}
                    for var, vals in [("depth", depths), ("velocity", velocities)]:
                        key = (species, stage, var)
                        if key in hsi_curves:
                            suits[var] = hsi_curves[key].evaluate(vals)
                    if not suits:
                        continue
                    csi = composite_csi(suits, method=composite)  # type: ignore[arg-type]
                    hmu_df = aggregate_wua_by_hmu(csi, areas, labels)
                    for _, h in hmu_df.iterrows():
                        rows.append(
                            {
                                "discharge_m3s": float(Q),
                                "species": species,
                                "life_stage": stage,
                                "hmu_type": h["hmu_type"],
                                "wua_m2": float(h["wua_m2"]),
                                "n_sections": int(h["n_sections"]),
                            }
                        )
        return pd.DataFrame(rows) if rows else None

    def _load_studyplan(
        self, studyplan_path: str | Path | None, warnings: list[str]
    ) -> object | None:
        """Load a StudyPlan if path provided. Errors converted to warnings."""
        if studyplan_path is None:
            return None
        try:
            from openlimno.studyplan import StudyPlan

            sp = StudyPlan.from_yaml(self._resolve(studyplan_path))
            warnings.append(f"StudyPlan loaded with {len(sp.tuf_overrides())} TUF overrides")
            return sp
        except Exception as e:
            warnings.append(f"StudyPlan load failed: {e}")
            return None

    def _maybe_drift_egg(
        self,
        cfg: dict,
        hydraulic_results: dict[float, list[Any]],
        sections: list[CrossSection],
        out_dir: Path,
        warnings: list[str],
    ) -> pd.DataFrame | None:
        """Run drift-egg evaluation if requested by case config (SPEC §4.2.6).

        Triggered when ``habitat.metric == "drifting-egg"`` and a
        ``habitat.drifting_egg`` block is present (see case.schema.json).
        Writes ``drift_egg.csv`` to ``out_dir``.
        """
        habitat_cfg = cfg.get("habitat", {})
        if habitat_cfg.get("metric") != "drifting-egg":
            return None
        de_cfg = habitat_cfg.get("drifting_egg")
        if de_cfg is None:
            warnings.append(
                "metric='drifting-egg' but no habitat.drifting_egg block; "
                "skipping (see case.schema.json)"
            )
            return None

        from openlimno.habitat import (
            evaluate_drifting_egg,
            load_drifting_egg_params,
        )

        species = de_cfg["species"]
        params_path = self._resolve(de_cfg["params"])
        spawning_station_m = float(de_cfg["spawning_station_m"])
        max_drift_km = float(de_cfg.get("max_drift_km", 200.0))
        dt_s = float(de_cfg.get("dt_s", 600.0))

        try:
            params = load_drifting_egg_params(params_path, species)
        except Exception as e:
            warnings.append(f"drift-egg params load failed: {e}")
            return None

        # Temperature forcing: constant or CSV
        T_forcing = de_cfg.get("temperature_forcing", {"type": "constant", "value_C": 20.0})
        stations = np.array([s.station_m for s in sections])
        T_field = self._build_temperature_field(T_forcing, stations, warnings)
        if T_field is None:
            return None

        # One drift run per discharge, using that Q's section-mean velocities as u(x)
        rows: list[dict[str, Any]] = []
        for Q in sorted(hydraulic_results.keys()):
            results = hydraulic_results[Q]
            u_field = {
                float(s.station_m): float(r.velocity_mean_ms)
                for s, r in zip(sections, results, strict=False)
            }
            if max(u_field.values()) <= 0:
                warnings.append(f"drift-egg: all-zero velocities at Q={Q}; skipping that discharge")
                continue
            try:
                res = evaluate_drifting_egg(
                    species=species,
                    spawning_station_m=spawning_station_m,
                    velocity_along_reach=u_field,
                    temperature_along_reach=T_field,
                    hatch_temp_days_curve=params["hatch_temp_days_curve"],  # type: ignore[arg-type]
                    mortality_velocity_threshold_ms=params["mortality_velocity_threshold_ms"],  # type: ignore[arg-type]
                    dt_s=dt_s,
                    max_drift_km=max_drift_km,
                )
            except Exception as e:
                warnings.append(f"drift-egg eval failed at Q={Q}: {e}")
                continue
            rows.append(
                {
                    "discharge_m3s": float(Q),
                    "species": res.species,
                    "spawning_station_m": res.spawning_station_m,
                    "hatch_station_m": res.hatch_station_m,
                    "drift_distance_km": res.drift_distance_km,
                    "hatch_temp_C_mean": res.hatch_temp_C_mean,
                    "mortality_fraction": res.mortality_fraction,
                    "success": bool(res.success),
                }
            )

        if not rows:
            return None
        df = pd.DataFrame(rows)
        self._atomic_write(
            out_dir / "drift_egg.csv",
            lambda p: df.to_csv(p, index=False),
        )
        return df

    def _build_temperature_field(
        self,
        forcing: dict[str, Any],
        stations: np.ndarray,
        warnings: list[str],
    ) -> dict[float, float] | None:
        """Resolve a temperature_forcing block to a station→temp_C mapping."""
        kind = forcing.get("type", "constant")
        if kind == "constant":
            T = float(forcing.get("value_C", 20.0))
            return {float(s): T for s in stations}
        if kind == "csv":
            csv_path = self._resolve(forcing["csv"])
            try:
                df = pd.read_csv(csv_path)
            except Exception as e:
                warnings.append(f"drift-egg temperature CSV load failed: {e}")
                return None
            scol = forcing.get("station_column", "station_m")
            tcol = forcing.get("temp_column", "temp_C")
            if scol not in df.columns or tcol not in df.columns:
                warnings.append(f"drift-egg temperature CSV missing columns {scol!r} or {tcol!r}")
                return None
            xs = df[scol].to_numpy(dtype=float)
            ts = df[tcol].to_numpy(dtype=float)
            interp = np.interp(stations, xs, ts, left=ts[0], right=ts[-1])
            return {float(s): float(t) for s, t in zip(stations, interp, strict=True)}
        warnings.append(f"drift-egg: unknown temperature_forcing.type={kind}")
        return None

    def _run_regulatory_exports(
        self,
        export_list: list[str],
        wua_q: pd.DataFrame,
        species_list: list[str],
        stage_list: list[str],
        out_dir: Path,
        discharge_series_path: str | Path | None,
        warnings: list[str],
        composite_df: pd.DataFrame | None = None,
        composite_summary: dict | None = None,
        wua_quality_grade: str = "A",
    ) -> None:
        """Auto-invoke regulatory_export submodules when listed in case
        YAML. When ``composite_df`` is provided (v1.7.0), each report is
        ALSO emitted as a ``<kind>_composite.csv`` variant carrying
        cover × thermal overlay annotations in its header.

        v1.7.1 (review F3): ``wua_quality_grade`` is now propagated and
        every regulatory CSV — base AND composite — receives the same
        HSI quality watermark used by ``wua_q.csv`` (TENTATIVE for
        C-grade, source-note for B-grade). Without this, a downstream
        consumer could cite a C-grade flow recommendation without ever
        seeing the quality warning.
        """
        if not species_list or not stage_list:
            return
        species = species_list[0]
        stage = stage_list[0]
        if discharge_series_path is None:
            # Use Lemhi discharge from the data dir as a default if available
            cfg_data = self.config.get("data", {})
            for k in ("rating_curve",):
                if k in cfg_data:
                    discharge_series_path = self._resolve(cfg_data[k])
                    break
        if discharge_series_path is None:
            warnings.append(
                "regulatory_export requested but no discharge_series available; "
                "supply discharge_series_path or set data.rating_curve in case.yaml"
            )
            return

        # Try to read discharge series; tolerate either CSV or Parquet
        ds_path = Path(discharge_series_path)
        if ds_path.suffix == ".parquet":
            Q = pd.read_parquet(ds_path)
        else:
            Q = pd.read_csv(ds_path)
        if "time" not in Q.columns or "discharge_m3s" not in Q.columns:
            warnings.append(
                f"discharge_series at {ds_path} lacks time/discharge_m3s; "
                "skipping regulatory export"
            )
            return

        # If a composite was produced, build a sibling DataFrame whose
        # `wua_m2_<sp>_<stage>` columns hold the composite values, so the
        # compute_* functions (which look up that exact column name)
        # operate on the composite without any signature change.
        composite_view = (
            self._composite_view(composite_df) if composite_df is not None
            else None
        )
        overlay_note = self._composite_header_lines(composite_summary)
        # v1.7.1 (review F3): HSI quality-grade watermark line shared by
        # both base and composite regulatory CSVs.
        quality_watermark = self._wua_csv_header(wua_quality_grade)

        for export_kind in export_list:
            try:
                if export_kind == "CN-SL712":
                    from openlimno.habitat.regulatory_export import cn_sl712

                    res = cn_sl712.compute_sl712(Q, wua_q, species, stage)
                    self._emit_regulatory_csv(
                        res, out_dir / "sl712.csv",
                        quality_watermark=quality_watermark,
                    )
                    if composite_view is not None:
                        comp = cn_sl712.compute_sl712(
                            Q, composite_view, species, stage,
                        )
                        self._emit_regulatory_csv(
                            comp, out_dir / "sl712_composite.csv",
                            quality_watermark=quality_watermark,
                            overlay_note=overlay_note,
                        )
                elif export_kind == "US-FERC-4e":
                    from openlimno.habitat.regulatory_export import us_ferc_4e

                    res = us_ferc_4e.compute_ferc_4e(Q, wua_q, species, stage)
                    self._emit_regulatory_csv(
                        res, out_dir / "ferc_4e.csv",
                        quality_watermark=quality_watermark,
                    )
                    if composite_view is not None:
                        comp = us_ferc_4e.compute_ferc_4e(
                            Q, composite_view, species, stage,
                        )
                        self._emit_regulatory_csv(
                            comp, out_dir / "ferc_4e_composite.csv",
                            quality_watermark=quality_watermark,
                            overlay_note=overlay_note,
                        )
                elif export_kind == "EU-WFD":
                    from openlimno.habitat.regulatory_export import eu_wfd

                    res = eu_wfd.compute_wfd(Q, wua_q, species, stage)
                    self._emit_regulatory_csv(
                        res, out_dir / "eu_wfd.csv",
                        quality_watermark=quality_watermark,
                    )
                    if composite_view is not None:
                        comp = eu_wfd.compute_wfd(
                            Q, composite_view, species, stage,
                        )
                        self._emit_regulatory_csv(
                            comp, out_dir / "eu_wfd_composite.csv",
                            quality_watermark=quality_watermark,
                            overlay_note=overlay_note,
                        )
                else:
                    warnings.append(f"Unknown regulatory_export kind: {export_kind}")
            except Exception as e:
                warnings.append(f"regulatory_export[{export_kind}] failed: {e}")

    @staticmethod
    def _composite_view(composite_df: pd.DataFrame) -> pd.DataFrame:
        """Build a regulatory-export-compatible DataFrame from a composite
        WUA-Q table. Renames each ``wua_m2_composite_<sp>_<stage>`` column
        to ``wua_m2_<sp>_<stage>`` and drops the original base columns
        (which would otherwise shadow the composite values during the
        ``wua_m2_{species}_{life_stage}`` lookup performed by every
        compute_* function).
        """
        cols_to_drop = [
            c for c in composite_df.columns
            if c.startswith("wua_m2_") and not c.startswith("wua_m2_composite_")
        ]
        view = composite_df.drop(columns=cols_to_drop).copy()
        rename_map = {
            c: c.replace("wua_m2_composite_", "wua_m2_", 1)
            for c in view.columns
            if c.startswith("wua_m2_composite_")
        }
        return view.rename(columns=rename_map)

    @staticmethod
    def _composite_header_lines(summary: dict | None) -> list[str]:
        """Build the ``# OpenLimno composite overlay …`` header
        block prepended to every ``*_composite.csv`` artefact so a
        reviewer reading the file in isolation can see exactly which
        cover/thermal factors were applied.

        v1.8.2 (3rd-review M4): docstring corrected — the actual emitted
        line dropped its ``v1.7.0`` stamp in v1.8.1 (review N5), but
        this docstring still mentioned the old literal. The historical
        references in surrounding comments are intentionally kept as
        per-feature provenance trails.
        """
        if summary is None:
            return []
        cover = summary.get("cover_si")
        thermal = summary.get("thermal_si")
        overlay = summary.get("overlay_si")
        # v1.10.0: surface the combination rule on its own header line so
        # reviewers reading e.g. ``sl712_composite.csv`` know whether the
        # numbers came out of the multiplicative product or the four-way
        # geometric mean. Falls back to ``product`` for old summaries
        # produced by v1.6.0—v1.9.x (no ``method`` key emitted).
        method = summary.get("method", "product")
        lines = [
            # v1.8.1 (2nd-review N5): drop the hard-coded "v1.7.0" stamp;
            # historical version labels in output files mislead readers
            # into thinking the LABEL is the producing software version.
            "# OpenLimno composite overlay applied to this report:",
            f"#   method={method}",
            (
                f"#   cover_si={cover if cover is not None else 'n/a'}"
                f"   thermal_si={thermal if thermal is not None else 'n/a'}"
                f"   overlay_si={overlay if overlay is not None else 'n/a'}"
            ),
            (
                "#   WUA values below are depth × velocity × cover × thermal"
                if (cover is not None and thermal is not None)
                else "#   WUA values below are depth × velocity × "
                + (
                    "cover only (no thermal overlay)" if cover is not None
                    else "thermal only (no cover overlay)"
                )
            ),
        ]
        # v1.8.0 (review F9): include the base → composite scaling per
        # species/stage so a reviewer reading e.g. ``eu_wfd_composite.csv``
        # can see "reference_wua_m2=137.18 was scaled from base 520.00"
        # directly in the header, without having to cross-reference
        # ``eu_wfd.csv`` or ``composite_hsi.json``.
        #
        # v1.8.1 (2nd-review N2 + N4): wrap each per-series formatting in
        # defensive try/except so a malformed future summary entry
        # (NaN / non-numeric / missing fields) drops only THAT line
        # instead of aborting the whole regulatory-export step before
        # any base CSV is written. NaN ratio is filtered out so the
        # header doesn't render an ugly ``(×nan)``.
        for series in summary.get("by_species_stage", []) or []:
            # v1.8.2 (3rd-review M2): an entry that is not a mapping
            # (None, float, str, list inserted by a malformed upstream
            # producer) would raise AttributeError on .get(), which
            # the original (TypeError, ValueError) catch did not
            # cover — that AttributeError escaped _composite_header_lines
            # entirely and aborted the regulatory_export step BEFORE
            # the per-export try/except. Skip non-mapping entries up
            # front and widen the catch.
            if not hasattr(series, "get"):
                continue
            try:
                base_max = series.get("wua_m2_base_max")
                comp_max = series.get("wua_m2_composite_max")
                ratio = series.get("composite_to_base_ratio")
                name = series.get("species_stage", "?")
                if base_max is None or comp_max is None:
                    continue
                # Reject NaN magnitudes too (a numeric-format would
                # produce 'nan' which is even worse than no annotation).
                if math.isnan(float(base_max)) or math.isnan(
                    float(comp_max)
                ):
                    continue
                ratio_part = ""
                if ratio is not None and not math.isnan(float(ratio)):
                    ratio_part = f" (×{float(ratio):.5f})"
                lines.append(
                    f"#   {name}: base_max={float(base_max):.2f} m² → "
                    f"composite_max={float(comp_max):.2f} m²{ratio_part}"
                )
            except (TypeError, ValueError, AttributeError):
                # Malformed series — skip this entry; keep emitting
                # the others rather than aborting the entire header.
                continue
        return lines

    @staticmethod
    def _emit_regulatory_csv(
        result: pd.DataFrame,
        path: Path,
        *,
        quality_watermark: str | None = None,
        overlay_note: list[str] | None = None,
    ) -> None:
        """v1.7.1 (unified) / v1.8.1 (atomic): regulatory-export CSV
        writer that publishes the final file in a single atomic
        rename.

        Layered prefix order (top → bottom):

        1. The HSI ``quality_watermark`` line (TENTATIVE for C-grade)
           — mirrors what ``wua_q.csv`` carries. Closes review F3:
           regulatory recommendations cannot be cited without the
           HSI-quality warning a downstream reader would see on the
           base WUA CSV.
        2. The composite ``overlay_note`` block (composite reports
           only) — cover/thermal scaling factors so a reviewer opening
           the file in isolation sees the multiplicative overlay
           immediately.
        3. The report's own ``# OpenLimno …`` header block — survives
           intact below the prefix.

        v1.8.1 (2nd-review N1): the previous implementation wrote the
        unprefixed CSV first, then re-opened the same path to prepend
        the watermark + overlay block. A concurrent reader (or a crash
        between the two operations) could observe a regulatory CSV
        missing its TENTATIVE warning — an audit-trail hazard for
        water-rights work. This version renders to a sibling tempfile,
        assembles the full prefixed body in memory, then publishes via
        ``os.replace`` (atomic on the same filesystem). The target
        ``path`` either does not exist or carries the fully-prefixed
        content; there is no observable intermediate state.

        v1.8.2 (3rd-review M1): tempfile names previously used fixed
        ``.inprogress`` / ``.publishtmp`` suffixes derived from the
        target path. Two concurrent writers (retry wrappers, parallel
        test runs in the same output dir, two case runs pointed at
        the same ``output.dir``) would collide on those names — one
        publisher could overwrite or unlink the other's body, or
        ``os.replace`` the wrong content. Now uses ``tempfile.mkstemp``
        with a per-call random suffix in the target's directory, and
        guards the publish tempfile with try/finally so a crash or
        ``os.replace`` failure can't leave a fully-written tempfile
        behind.
        """
        import tempfile as _tempfile
        prefix_lines: list[str] = []
        if quality_watermark:
            # _wua_csv_header returns a string ending in '\n' already.
            prefix_lines.append(quality_watermark.rstrip("\n"))
        if overlay_note:
            prefix_lines.extend(overlay_note)

        # v1.9.0: render the report into a unique body tempfile, then
        # delegate publish (atomicity + perms) to the shared
        # ``_atomic_write`` helper. The body tempfile uses mkstemp too
        # so concurrent same-path publishes still don't collide on
        # body-stage filenames.
        body_fd, body_path_str = _tempfile.mkstemp(
            prefix=f".{path.name}.body.", suffix=".inprogress",
            dir=path.parent,
        )
        os.close(body_fd)
        body_path = Path(body_path_str)
        try:
            result.to_csv(body_path)
            body = body_path.read_text(encoding="utf-8")
        finally:
            body_path.unlink(missing_ok=True)

        if prefix_lines:
            content = "\n".join(prefix_lines) + "\n" + body
        else:
            content = body

        Case._atomic_write(
            path, lambda p: p.write_text(content, encoding="utf-8"),
        )

    def _wua_csv_header(self, quality_grade: str) -> str | None:
        """Build a comment-prefix header line for WUA CSV outputs.

        Reflects SPEC §4.2.2.1 / ADR-0006: tentative results are clearly marked.
        """
        if quality_grade == "A":
            return None  # No watermark for high-confidence
        if quality_grade == "B":
            return (
                "# OpenLimno WUA — HSI quality grade B "
                "(neighboring-basin transferred curves; SPEC §4.2.2)\n"
            )
        return (
            "# OpenLimno WUA — TENTATIVE (HSI quality grade C; "
            "run `openlimno hsi upgrade` to improve metadata; SPEC §4.2.2.3)\n"
        )

    def _maybe_run_thermal_habitat(
        self, cfg: dict, case_dir: Path, out_dir: Path,
        warnings: list[str],
    ) -> dict | None:
        """v1.1.1: detect WEDM v0.2 `data.fishbase_traits` +
        `data.climate` in the case and evaluate per-day thermal SI.

        Writes `thermal_hsi.csv` to ``out_dir`` and returns the
        summary metrics dict (or ``None`` if either input is missing
        so the run remains valid for v1.0.x cases without fetched
        data).
        """
        data_block = cfg.get("data", {}) or {}
        fb = data_block.get("fishbase_traits")
        clim = data_block.get("climate")
        if not isinstance(fb, dict) or not isinstance(clim, dict):
            return None
        # Require the FishBase traits to carry a usable preferred range.
        t_min = fb.get("temperature_min_C")
        t_max = fb.get("temperature_max_C")
        if t_min is None or t_max is None:
            warnings.append(
                "data.fishbase_traits missing temperature_min_C / "
                "temperature_max_C — skipping thermal_habitat step."
            )
            return None
        clim_uri = clim.get("uri")
        if not clim_uri:
            warnings.append(
                "data.climate.uri missing — skipping thermal_habitat step."
            )
            return None

        clim_path = (case_dir / clim_uri).resolve()
        if not clim_path.is_file():
            warnings.append(
                f"data.climate.uri ({clim_uri}) not found at "
                f"{clim_path} — skipping thermal_habitat step."
            )
            return None

        from openlimno.habitat.thermal import (
            ThermalRange,
            thermal_metrics,
            thermal_suitability_series,
        )
        clim_df = pd.read_csv(clim_path)
        if "T_water_C_stefan" not in clim_df.columns:
            warnings.append(
                f"climate CSV {clim_path.name} lacks T_water_C_stefan "
                f"column — skipping thermal_habitat step. (cols: "
                f"{list(clim_df.columns)})"
            )
            return None

        tr = ThermalRange.from_fishbase(
            float(t_min), float(t_max),
            source=(
                f"FishBase via data.fishbase_traits "
                f"({fb.get('scientific_name', '?')})"
            ),
        )
        thermal_df = thermal_suitability_series(clim_df, tr)
        self._atomic_write(
            out_dir / "thermal_hsi.csv",
            lambda p: thermal_df.to_csv(p, index=False),
        )
        return thermal_metrics(thermal_df)

    def _maybe_run_cover_habitat(
        self, cfg: dict, case_dir: Path, out_dir: Path,
        warnings: list[str],
    ) -> dict | None:
        """v1.5.0: detect WEDM v0.2 `data.lulc` + `data.watershed` and
        compute a watershed-mean cover SI using the v1.3.0
        `habitat.cover` module. Mirrors the v1.1.1 thermal pattern.

        Writes a small ``cover_si.json`` to ``out_dir`` (mean_si +
        class histograms keyed by integer LCCS code, plus area_km2
        per class derived from `data.lulc.class_km2` when available)
        and returns the metrics dict — or ``None`` if either input
        block is missing so v1.0.x cases without fetched data still
        run unchanged.
        """
        data_block = cfg.get("data", {}) or {}
        lulc = data_block.get("lulc")
        ws = data_block.get("watershed")
        if not isinstance(lulc, dict) or not isinstance(ws, dict):
            return None
        lulc_uri = lulc.get("uri")
        ws_uri = ws.get("uri")
        if not lulc_uri or not ws_uri:
            warnings.append(
                "data.lulc.uri or data.watershed.uri missing — "
                "skipping cover_habitat step."
            )
            return None
        lulc_path = (case_dir / lulc_uri).resolve()
        ws_path = (case_dir / ws_uri).resolve()
        if not lulc_path.is_file():
            warnings.append(
                f"data.lulc.uri ({lulc_uri}) not found at {lulc_path} "
                f"— skipping cover_habitat step."
            )
            return None
        if not ws_path.is_file():
            warnings.append(
                f"data.watershed.uri ({ws_uri}) not found at "
                f"{ws_path} — skipping cover_habitat step."
            )
            return None

        from openlimno.habitat.cover import (
            DEFAULT_RIPARIAN_COVER_SI,
            watershed_cover_si,
        )
        mean_si, class_pixels = watershed_cover_si(lulc_path, ws_path)
        # Fold area_km2 per class from data.lulc.class_km2 when the
        # case carries it (v0.3.4 CLI does); otherwise leave km² null.
        class_km2_source = lulc.get("class_km2") or {}
        # class_km2 keys come from JSON as strings; coerce to int.
        class_km2 = {
            int(k): float(v) for k, v in class_km2_source.items()
        }
        # int-keyed dicts are NOT JSON-serialisable directly; flatten
        # to a list of records for round-trip stability.
        payload = {
            "mean_si": float(mean_si),
            "n_classes": len(class_pixels),
            "classes": [
                {
                    "class_code": int(code),
                    "pixel_count": int(class_pixels[code]),
                    "cover_si": float(
                        DEFAULT_RIPARIAN_COVER_SI.get(int(code), 0.0)
                    ),
                    "area_km2": class_km2.get(int(code)),
                }
                for code in sorted(class_pixels)
            ],
        }
        self._atomic_write(
            out_dir / "cover_si.json",
            lambda p: p.write_text(
                json.dumps(payload, indent=2), encoding="utf-8",
            ),
        )
        return {
            "mean_si": float(mean_si),
            "n_classes": len(class_pixels),
            "total_pixels": int(sum(class_pixels.values())),
        }

    def _maybe_run_per_cell_composite(
        self,
        wua_df: pd.DataFrame,
        overlay: CompositeOverlay,
        per_cell_csi: PerCellCsiMap | None,
        warnings: list[str],
        *,
        per_section_thermal_si: np.ndarray | None = None,
        per_section_cover_si: np.ndarray | None = None,
    ) -> tuple[pd.DataFrame | None, dict[str, object] | None]:
        """v2.4.0: per-cell geometric-mean composite path.

        Consumes the ``per_cell_csi`` arrays captured during step 4
        and runs :func:`apply_overlay_per_cell` per (Q, species,
        stage) cell. Returns a paired ``composite_df`` with the same
        column shape the column-level path emits (so the regulatory
        export step needs no special-casing) plus a ``summary`` dict
        with ``method="geom_mean_per_cell"`` and per-series stats.

        Note: cover/thermal SI are still basin-wide scalars at the
        v2.4.0 fetch surface, so we broadcast them across all cells.
        The per-cell **engine** is fully wired for true per-cell
        arrays once a spatial cover/thermal fetcher lands (v3.x).
        """
        from openlimno.habitat.composite import apply_overlay_per_cell

        if not per_cell_csi:
            warnings.append(
                "composite_hsi: geom_mean_per_cell requested but no "
                "per-cell CSI arrays were captured. Skipping."
            )
            return None, None

        base_cols = [
            c for c in wua_df.columns
            if c.startswith("wua_m2_")
            and not c.startswith("wua_m2_composite_")
        ]

        out_rows: list[dict[str, Any]] = []
        by_series_stats: dict[str, dict[str, Any]] = {
            c[len("wua_m2_"):]: {
                "base_max": 0.0, "comp_max": 0.0, "q_at_max": None,
            }
            for c in base_cols
        }

        # v2.5.1 (R8-1): build a suffix → (species, stage) lookup from
        # the actual per_cell_csi keys. Previously
        # ``suffix.rsplit("_", 1)`` mis-split species/stage when either
        # contained underscores (e.g. species ``salmo_trutta`` + stage
        # ``juvenile_winter`` collapsed into a non-existent key,
        # silently falling back to base WUA).
        suffix_to_pair: dict[str, tuple[str, str]] = {}
        for (_q_key, sp, st) in per_cell_csi:
            suffix_to_pair[f"{sp}_{st}"] = (sp, st)

        for _, row in wua_df.iterrows():
            Q = float(row["discharge_m3s"])
            out_row: dict[str, Any] = {"discharge_m3s": Q}
            for col in base_cols:
                out_row[col] = row[col]
                suffix = col[len("wua_m2_"):]
                pair = suffix_to_pair.get(suffix)
                if pair is None:
                    # No HSI vars resolved → fall back to base value.
                    composite_wua = float(row[col])
                else:
                    species, stage = pair
                    key = (Q, species, stage)
                    if key not in per_cell_csi:
                        composite_wua = float(row[col])
                    else:
                        csi_arr, area_arr = per_cell_csi[key]
                        # v2.5.1 (R8-5): when a per-section thermal SI
                        # array was loaded from
                        # ``data.thermal_si_per_section.uri``, pass it
                        # cell-wise to ``apply_overlay_per_cell``
                        # instead of the basin-scalar ``overlay.thermal_si``
                        # — closes the YAML-driven per-cell raster
                        # overlay path the v2.0.0 charter promised.
                        # The per-section array length is validated
                        # against ``len(sections)`` at load time
                        # (``_maybe_load_per_section_thermal_si``).
                        thermal_arg: object | None
                        if (
                            per_section_thermal_si is not None
                            and per_section_thermal_si.shape == csi_arr.shape
                        ):
                            thermal_arg = per_section_thermal_si
                        else:
                            thermal_arg = overlay.thermal_si
                        # v2.7.0: per-section cover SI mirrors the
                        # v2.5.1 R8-5 thermal contract. When the array
                        # is present and matches the section count,
                        # pass it cell-wise; else fall back to the
                        # basin-wide scalar.
                        cover_arg: object | None
                        if (
                            per_section_cover_si is not None
                            and per_section_cover_si.shape == csi_arr.shape
                        ):
                            cover_arg = per_section_cover_si
                        else:
                            cover_arg = overlay.cover_si
                        result = apply_overlay_per_cell(
                            csi_arr,
                            area_arr,
                            cover_si_per_cell=cover_arg,
                            thermal_si_per_cell=thermal_arg,
                            method="geom_mean",
                        )
                        composite_wua = float(result["wua_composite_m2"])
                comp_col = f"wua_m2_composite_{suffix}"
                out_row[comp_col] = composite_wua
                stats = by_series_stats[suffix]
                base_v = float(row[col])
                if base_v > stats["base_max"]:
                    stats["base_max"] = base_v
                if composite_wua > stats["comp_max"]:
                    stats["comp_max"] = composite_wua
                    stats["q_at_max"] = Q
            out_rows.append(out_row)

        composite_df = pd.DataFrame(out_rows)
        by_series: list[dict[str, object]] = []
        for suffix, stats in by_series_stats.items():
            base_max = stats["base_max"]
            comp_max = stats["comp_max"]
            by_series.append({
                "species_stage": suffix,
                "wua_m2_base_max": base_max,
                "wua_m2_composite_max": comp_max,
                "discharge_m3s_at_composite_max": stats["q_at_max"],
                "composite_to_base_ratio": (
                    comp_max / base_max if base_max > 0 else None
                ),
            })

        summary: dict[str, object] = {
            "method": "geom_mean_per_cell",
            "cover_si": overlay.cover_si,
            "thermal_si": overlay.thermal_si,
            "overlay_si": overlay.overlay_si,
            "n_overlays": overlay.n_overlays,
            "n_discharges": int(len(wua_df)),
            "by_species_stage": by_series,
        }
        return composite_df, summary

    def _maybe_compute_per_section_thermal_si_from_raster(
        self,
        cfg: dict,
        sections: list[Any],
        warnings: list[str],
    ) -> np.ndarray | None:
        """v2.6.0: inline raster → per-section thermal SI.

        When ``data.thermal_raster.uri`` and ``data.section_locations.uri``
        are both present in the case, this method:

        1. Loads the section_locations CSV (columns ``station_m``,
           ``lon``, ``lat``; one row per cross-section in the same
           order as ``data.cross_section``).
        2. Builds per-section geometries — either point samples
           (default) or buffered circles when ``buffer_m > 0``.
        3. Pulls the ``ThermalRange`` from ``data.fishbase_traits``
           (same path the v1.1.1 scalar thermal_metrics uses) so the
           inline path is consistent with the basin-scalar fallback.
        4. Calls :func:`openlimno.habitat.thermal_si_per_section` on
           the raster to produce the per-section SI array.

        Returns ``None`` when any required block is missing or the
        data is inconsistent (length mismatch, missing FishBase
        traits, etc.) — caller then falls back to the v2.5.1 offline
        CSV path, and finally to the scalar broadcast.
        """
        data_block = cfg.get("data", {}) or {}
        raster = data_block.get("thermal_raster")
        locs = data_block.get("section_locations")
        if not (isinstance(raster, dict) and isinstance(locs, dict)):
            return None
        raster_uri = raster.get("uri")
        locs_uri = locs.get("uri")
        if not (raster_uri and locs_uri):
            return None

        raster_path = (self.case_dir / raster_uri).resolve()
        locs_path = (self.case_dir / locs_uri).resolve()
        if not raster_path.is_file() or not locs_path.is_file():
            warnings.append(
                "data.thermal_raster or data.section_locations file "
                "missing — falling back from inline raster path."
            )
            return None

        try:
            locs_df = pd.read_csv(locs_path)
        except Exception as e:  # noqa: BLE001
            warnings.append(
                f"section_locations CSV read failed: {e!r}. "
                f"Falling back from inline raster path."
            )
            return None
        required_cols = {"station_m", "lon", "lat"}
        if not required_cols.issubset(locs_df.columns):
            warnings.append(
                f"section_locations CSV {locs_path.name} missing "
                f"required columns {sorted(required_cols)}; got "
                f"{list(locs_df.columns)}. Falling back."
            )
            return None
        if len(locs_df) != len(sections):
            warnings.append(
                f"section_locations length {len(locs_df)} != number "
                f"of sections {len(sections)}. Falling back."
            )
            return None

        # FishBase traits drive the ThermalRange. Reuse the same
        # extraction the v1.1.1 thermal_habitat path uses so the
        # inline raster SI matches the scalar SI for uniform rasters.
        fb = data_block.get("fishbase_traits")
        if not isinstance(fb, dict):
            warnings.append(
                "data.fishbase_traits missing — cannot build "
                "ThermalRange for inline thermal_raster path. "
                "Falling back."
            )
            return None
        t_min = fb.get("temperature_min_C")
        t_max = fb.get("temperature_max_C")
        if t_min is None or t_max is None:
            warnings.append(
                "data.fishbase_traits.temperature_{min,max}_C missing — "
                "cannot build ThermalRange. Falling back."
            )
            return None

        from openlimno.habitat.thermal import (
            ThermalRange,
            thermal_hsi,
            thermal_si_per_section,
        )
        try:
            from shapely.geometry import Point
        except ImportError as e:
            warnings.append(
                f"shapely not importable for inline raster path: "
                f"{e!r}. Falling back."
            )
            return None

        tr = ThermalRange.from_fishbase(
            float(t_min), float(t_max),
            source=(
                f"FishBase via data.fishbase_traits "
                f"({fb.get('scientific_name', '?')})"
            ),
        )

        raw_buffer_m = locs.get("buffer_m", 0.0)
        if raw_buffer_m is None:
            raw_buffer_m = 0.0
        try:
            buffer_m = float(raw_buffer_m)
        except (TypeError, ValueError):
            warnings.append(
                f"section_locations.buffer_m must be a number, got "
                f"{raw_buffer_m!r}. Falling back."
            )
            return None
        # v2.6.1 (R9-5): refuse negative buffers loudly. The schema
        # already declares minimum: 0, but a manually-edited case.yaml
        # could slip through.
        if buffer_m < 0.0:
            warnings.append(
                f"section_locations.buffer_m must be ≥ 0, got "
                f"{buffer_m}. Falling back."
            )
            return None
        band = int(raster.get("band", 1) or 1)

        # v2.6.1 (R9-1): validate / reproject coordinates so the
        # rasterio.sample / thermal_si_per_section call sees coords
        # in the RASTER's CRS, not whatever the section_locations CSV
        # declares. Without this, a UTM raster + EPSG:4326 sections
        # silently sample wildly wrong pixels.
        import rasterio
        locs_crs_str = str(locs.get("crs", "EPSG:4326"))
        try:
            with rasterio.open(raster_path) as src:
                raster_crs = src.crs
                raster_nodata = src.nodata
                raster_bounds = src.bounds
        except Exception as e:  # noqa: BLE001
            warnings.append(
                f"rasterio.open({raster_path}) failed: {e!r}. "
                f"Falling back from inline raster path."
            )
            return None
        if raster_crs is None:
            warnings.append(
                f"thermal_raster {raster_path.name} has no CRS "
                f"declared; cannot safely sample. Falling back."
            )
            return None
        try:
            from rasterio.crs import CRS
            locs_crs = CRS.from_user_input(locs_crs_str)
        except Exception as e:  # noqa: BLE001
            warnings.append(
                f"section_locations.crs={locs_crs_str!r} parse failed: "
                f"{e!r}. Falling back."
            )
            return None

        # Collect raw (lon, lat) and reproject to raster CRS if needed.
        raw_xs = locs_df["lon"].astype(float).to_numpy()
        raw_ys = locs_df["lat"].astype(float).to_numpy()
        if locs_crs == raster_crs:
            xs, ys = raw_xs, raw_ys
        else:
            try:
                from rasterio.warp import transform as warp_transform
                xs_list, ys_list = warp_transform(
                    locs_crs, raster_crs,
                    raw_xs.tolist(), raw_ys.tolist(),
                )
                xs = np.asarray(xs_list, dtype=float)
                ys = np.asarray(ys_list, dtype=float)
            except Exception as e:  # noqa: BLE001
                warnings.append(
                    f"CRS reprojection {locs_crs_str} → "
                    f"{raster_crs.to_string()} failed: {e!r}. "
                    f"Falling back."
                )
                return None

        if buffer_m <= 0.0:
            # Point-sample path. coords are now in raster CRS.
            coords = list(zip(xs.tolist(), ys.tolist(), strict=True))
            try:
                with rasterio.open(raster_path) as src:
                    samples = list(src.sample(coords, indexes=band))
            except Exception as e:  # noqa: BLE001
                warnings.append(
                    f"rasterio.sample failed: {e!r}. Falling back "
                    f"from inline raster path."
                )
                return None
            t_vals = np.array(
                [float(s[0]) for s in samples], dtype=float,
            )
            # v2.6.1 (R9-2): rasterio.sample returns the raster's
            # nodata value (or 0 when nodata is None) for points
            # outside bounds. ``np.isfinite`` accepts those finite
            # sentinels and silently converts them into SI values.
            # Use explicit outside-bounds check + nodata comparison.
            min_x, min_y, max_x, max_y = raster_bounds
            in_bounds = (
                (xs >= min_x) & (xs <= max_x)
                & (ys >= min_y) & (ys <= max_y)
            )
            valid = np.isfinite(t_vals) & in_bounds
            if raster_nodata is not None and np.isfinite(raster_nodata):
                valid &= np.abs(t_vals - float(raster_nodata)) > 1e-9
            if not np.all(valid):
                bad = np.where(~valid)[0].tolist()
                warnings.append(
                    f"Section indices {bad} sampled outside the "
                    f"thermal raster bounds or hit the nodata "
                    f"sentinel. Falling back from inline raster path."
                )
                return None
            si = np.asarray(thermal_hsi(t_vals, tr), dtype=float)
            return np.clip(si, 0.0, 1.0)

        # Buffered path: build per-section polygon in raster CRS.
        # When raster CRS is geographic (EPSG:4326), convert buffer_m
        # → degrees via cosine-latitude (≤1% accurate to ~10° lat; see
        # v3.x research-route for projected-CRS buffering).
        # When raster CRS is projected (units = m), use buffer_m directly.
        geoms: list[Any] = []
        raster_is_geographic = bool(getattr(raster_crs, "is_geographic", False))
        for x, y in zip(xs, ys, strict=True):
            if raster_is_geographic:
                # y is in degrees latitude in the raster CRS.
                cos_lat = max(abs(np.cos(np.radians(float(y)))), 1e-6)
                deg_per_m_lon = 1.0 / (111_320.0 * cos_lat)
                deg_per_m_lat = 1.0 / 110_540.0
                buf_radius = buffer_m * min(deg_per_m_lon, deg_per_m_lat)
            else:
                # Projected CRS in metres — buffer in raster units directly.
                buf_radius = buffer_m
            geoms.append(Point(float(x), float(y)).buffer(buf_radius))

        try:
            arr = thermal_si_per_section(
                raster_path, geoms, tr, band=band,
                # v2.6.1 (R9-6): the inline buffered path can produce
                # sub-pixel geometries (≤ a few hundred metres in
                # degree space at typical Open-Meteo resolution);
                # all_touched=True ensures the geometry still captures
                # the pixel(s) it overlaps.
                all_touched=True,
            )
        except Exception as e:  # noqa: BLE001
            warnings.append(
                f"thermal_si_per_section failed: {e!r}. "
                f"Falling back from inline raster path."
            )
            return None
        return np.clip(arr.astype(float), 0.0, 1.0)

    def _maybe_load_per_section_thermal_si(
        self,
        cfg: dict,
        sections: list[Any],
        warnings: list[str],
    ) -> np.ndarray | None:
        """v2.5.1 (R8-5): load ``data.thermal_si_per_section.uri`` (a
        CSV with ``station_m`` and ``thermal_si`` columns) into a
        per-section thermal-SI array aligned with ``sections``.

        Returns ``None`` when the block is absent (preserves v1.x
        behaviour). Returns ``None`` + warning when the CSV is
        present but invalid (length mismatch, missing columns, out-of-
        range values) so the run degrades to scalar thermal overlay
        rather than aborting.
        """
        data_block = cfg.get("data", {}) or {}
        block = data_block.get("thermal_si_per_section")
        if not isinstance(block, dict):
            return None
        uri = block.get("uri")
        if not uri:
            return None
        path = (self.case_dir / uri).resolve()
        if not path.is_file():
            warnings.append(
                f"data.thermal_si_per_section.uri ({uri}) not found at "
                f"{path} — falling back to scalar thermal overlay."
            )
            return None
        try:
            df = pd.read_csv(path)
        except Exception as e:  # noqa: BLE001
            warnings.append(
                f"data.thermal_si_per_section CSV read failed: {e!r}. "
                f"Falling back to scalar thermal overlay."
            )
            return None
        if "thermal_si" not in df.columns:
            warnings.append(
                f"data.thermal_si_per_section CSV {path.name} lacks a "
                f"'thermal_si' column; falling back to scalar."
            )
            return None
        if len(df) != len(sections):
            warnings.append(
                f"data.thermal_si_per_section length {len(df)} != "
                f"number of sections {len(sections)}. Falling back to "
                f"scalar thermal overlay."
            )
            return None
        arr = df["thermal_si"].astype(float).to_numpy()
        if (arr < -1e-9).any() or (arr > 1.0 + 1e-9).any():
            warnings.append(
                f"data.thermal_si_per_section values out of [0, 1] "
                f"(min={arr.min()}, max={arr.max()}); falling back to "
                f"scalar."
            )
            return None
        return np.clip(arr, 0.0, 1.0)

    def _maybe_compute_per_section_cover_si_from_raster(
        self,
        cfg: dict,
        sections: list[Any],
        warnings: list[str],
    ) -> np.ndarray | None:
        """v2.7.0: inline LULC raster → per-section cover SI.

        Symmetric to :meth:`_maybe_compute_per_section_thermal_si_from_raster`
        (v2.6.0). When ``data.cover_raster.uri`` and
        ``data.section_locations.uri`` are both present:

        1. Parse section_locations CSV (validated to match
           ``len(sections)`` and to carry ``station_m``, ``lon``,
           ``lat`` columns).
        2. Reproject coordinates from ``section_locations.crs``
           (defaults to EPSG:4326) to the raster CRS if needed —
           v2.6.1 R9-1 fix applies symmetrically to LULC rasters.
        3. ``buffer_m == 0`` (default): sample the single LULC pixel
           code at each section point and look up
           :data:`openlimno.habitat.cover.DEFAULT_RIPARIAN_COVER_SI`
           to get the per-section SI.
        4. ``buffer_m > 0``: build per-section polygons (cosine-lat
           in geographic raster CRS; direct metres in projected) and
           delegate to :func:`openlimno.habitat.cover_si_per_section`,
           which takes the pixel-weighted mean inside each polygon.

        Returns ``None`` with a warning when any block is missing
        or inconsistent — caller then falls back to the v2.7.0 CSV
        path, then to the v1.5.0 basin-wide scalar.
        """
        data_block = cfg.get("data", {}) or {}
        raster = data_block.get("cover_raster")
        locs = data_block.get("section_locations")
        if not (isinstance(raster, dict) and isinstance(locs, dict)):
            return None
        raster_uri = raster.get("uri")
        locs_uri = locs.get("uri")
        if not (raster_uri and locs_uri):
            return None

        raster_path = (self.case_dir / raster_uri).resolve()
        locs_path = (self.case_dir / locs_uri).resolve()
        if not raster_path.is_file() or not locs_path.is_file():
            warnings.append(
                "data.cover_raster or data.section_locations file "
                "missing — falling back from inline cover-raster path."
            )
            return None

        try:
            locs_df = pd.read_csv(locs_path)
        except Exception as e:  # noqa: BLE001
            warnings.append(
                f"section_locations CSV read failed: {e!r}. "
                f"Falling back from inline cover-raster path."
            )
            return None
        required_cols = {"station_m", "lon", "lat"}
        if not required_cols.issubset(locs_df.columns):
            warnings.append(
                f"section_locations CSV {locs_path.name} missing "
                f"required columns {sorted(required_cols)}. Falling back."
            )
            return None
        if len(locs_df) != len(sections):
            warnings.append(
                f"section_locations length {len(locs_df)} != number "
                f"of sections {len(sections)}. Falling back from "
                f"inline cover-raster path."
            )
            return None

        raw_buffer_m = locs.get("buffer_m", 0.0)
        if raw_buffer_m is None:
            raw_buffer_m = 0.0
        try:
            buffer_m = float(raw_buffer_m)
        except (TypeError, ValueError):
            warnings.append(
                f"section_locations.buffer_m must be a number, got "
                f"{raw_buffer_m!r}. Falling back."
            )
            return None
        if buffer_m < 0.0:
            warnings.append(
                f"section_locations.buffer_m must be ≥ 0, got "
                f"{buffer_m}. Falling back."
            )
            return None
        band = int(raster.get("band", 1) or 1)

        import rasterio
        locs_crs_str = str(locs.get("crs", "EPSG:4326"))
        try:
            with rasterio.open(raster_path) as src:
                raster_crs = src.crs
                raster_nodata = src.nodata
                raster_bounds = src.bounds
        except Exception as e:  # noqa: BLE001
            warnings.append(
                f"rasterio.open({raster_path}) failed: {e!r}. "
                f"Falling back from inline cover-raster path."
            )
            return None
        if raster_crs is None:
            warnings.append(
                f"cover_raster {raster_path.name} has no CRS "
                f"declared; cannot safely sample. Falling back."
            )
            return None
        try:
            from rasterio.crs import CRS
            locs_crs = CRS.from_user_input(locs_crs_str)
        except Exception as e:  # noqa: BLE001
            warnings.append(
                f"section_locations.crs={locs_crs_str!r} parse failed: "
                f"{e!r}. Falling back."
            )
            return None

        raw_xs = locs_df["lon"].astype(float).to_numpy()
        raw_ys = locs_df["lat"].astype(float).to_numpy()
        if locs_crs == raster_crs:
            xs, ys = raw_xs, raw_ys
        else:
            try:
                from rasterio.warp import transform as warp_transform
                xs_list, ys_list = warp_transform(
                    locs_crs, raster_crs,
                    raw_xs.tolist(), raw_ys.tolist(),
                )
                xs = np.asarray(xs_list, dtype=float)
                ys = np.asarray(ys_list, dtype=float)
            except Exception as e:  # noqa: BLE001
                warnings.append(
                    f"CRS reprojection {locs_crs_str} → "
                    f"{raster_crs.to_string()} failed: {e!r}. "
                    f"Falling back."
                )
                return None

        from openlimno.habitat.cover import (
            DEFAULT_RIPARIAN_COVER_SI,
            cover_si_per_section,
        )

        if buffer_m <= 0.0:
            # Point-sample path: read the single LULC pixel code at
            # each section and map via the cover-SI table. LULC
            # rasters are categorical (uint8), so we round to the
            # nearest int after sampling.
            coords = list(zip(xs.tolist(), ys.tolist(), strict=True))
            try:
                with rasterio.open(raster_path) as src:
                    samples = list(src.sample(coords, indexes=band))
            except Exception as e:  # noqa: BLE001
                warnings.append(
                    f"rasterio.sample (cover) failed: {e!r}. "
                    f"Falling back."
                )
                return None
            codes = np.array(
                [int(round(float(s[0]))) for s in samples], dtype=int,
            )
            min_x, min_y, max_x, max_y = raster_bounds
            in_bounds = (
                (xs >= min_x) & (xs <= max_x)
                & (ys >= min_y) & (ys <= max_y)
            )
            valid = in_bounds.copy()
            if raster_nodata is not None and np.isfinite(raster_nodata):
                valid &= codes != int(round(float(raster_nodata)))
            # v2.7.1 (R10-1): the buffered path treats LULC codes
            # missing from DEFAULT_RIPARIAN_COVER_SI as INVALID (it
            # raises RuntimeError when every pixel is unmapped), so
            # point-sample must do the same — otherwise the same
            # section can return SI=0 (point-sample default) or fail
            # loud (buffered) depending on buffer_m, which is a real
            # internal inconsistency.
            mapped = np.array(
                [int(code) in DEFAULT_RIPARIAN_COVER_SI for code in codes],
                dtype=bool,
            )
            valid &= mapped
            if not np.all(valid):
                bad = np.where(~valid)[0].tolist()
                unmapped_codes = sorted({
                    int(codes[i]) for i in bad
                    if in_bounds[i]
                    and (
                        raster_nodata is None
                        or not np.isfinite(raster_nodata)
                        or int(codes[i]) != int(round(float(raster_nodata)))
                    )
                    and int(codes[i]) not in DEFAULT_RIPARIAN_COVER_SI
                })
                # v2.7.1 (R10-2): unmapped codes typically mean the
                # user pointed at a continuous-value raster (e.g.
                # NDVI 0..1, ESA WorldCover stored as float32). Fail
                # loud rather than silently return SI=0 everywhere.
                hint = (
                    f" (unmapped codes: {unmapped_codes}; valid "
                    f"codes per DEFAULT_RIPARIAN_COVER_SI are "
                    f"{sorted(DEFAULT_RIPARIAN_COVER_SI)}. Did you "
                    f"point cover_raster at a continuous-value "
                    f"raster instead of an LULC class raster?)"
                    if unmapped_codes
                    else ""
                )
                warnings.append(
                    f"Section indices {bad} sampled outside the "
                    f"cover raster bounds, hit the nodata sentinel, "
                    f"or sampled an LULC code not in "
                    f"DEFAULT_RIPARIAN_COVER_SI{hint}. Falling back "
                    f"from inline cover-raster path."
                )
                return None
            si = np.array(
                [
                    float(DEFAULT_RIPARIAN_COVER_SI.get(int(code), 0.0))
                    for code in codes
                ],
                dtype=float,
            )
            return np.clip(si, 0.0, 1.0)

        # Buffered path: per-section polygon → pixel-weighted mean SI.
        try:
            from shapely.geometry import Point
        except ImportError as e:
            warnings.append(
                f"shapely not importable for cover-raster path: "
                f"{e!r}. Falling back."
            )
            return None
        geoms: list[Any] = []
        raster_is_geographic = bool(
            getattr(raster_crs, "is_geographic", False)
        )
        for x, y in zip(xs, ys, strict=True):
            if raster_is_geographic:
                cos_lat = max(abs(np.cos(np.radians(float(y)))), 1e-6)
                deg_per_m_lon = 1.0 / (111_320.0 * cos_lat)
                deg_per_m_lat = 1.0 / 110_540.0
                buf_radius = buffer_m * min(deg_per_m_lon, deg_per_m_lat)
            else:
                buf_radius = buffer_m
            geoms.append(Point(float(x), float(y)).buffer(buf_radius))
        try:
            arr = cover_si_per_section(
                raster_path, geoms,
                # v2.7.0: same sub-pixel-buffer rationale as the
                # v2.6.1 R9-6 inline thermal raster path.
                all_touched=True,
            )
        except Exception as e:  # noqa: BLE001
            warnings.append(
                f"cover_si_per_section failed: {e!r}. Falling back "
                f"from inline cover-raster path."
            )
            return None
        return np.clip(arr.astype(float), 0.0, 1.0)

    def _maybe_load_per_section_cover_si(
        self,
        cfg: dict,
        sections: list[Any],
        warnings: list[str],
    ) -> np.ndarray | None:
        """v2.7.0: load ``data.cover_si_per_section.uri`` (CSV with
        ``station_m`` + ``cover_si``) into a per-section array.
        Symmetric to ``_maybe_load_per_section_thermal_si`` (v2.5.1).
        """
        data_block = cfg.get("data", {}) or {}
        block = data_block.get("cover_si_per_section")
        if not isinstance(block, dict):
            return None
        uri = block.get("uri")
        if not uri:
            return None
        path = (self.case_dir / uri).resolve()
        if not path.is_file():
            warnings.append(
                f"data.cover_si_per_section.uri ({uri}) not found at "
                f"{path} — falling back to scalar cover overlay."
            )
            return None
        try:
            df = pd.read_csv(path)
        except Exception as e:  # noqa: BLE001
            warnings.append(
                f"data.cover_si_per_section CSV read failed: {e!r}. "
                f"Falling back to scalar cover overlay."
            )
            return None
        if "cover_si" not in df.columns:
            warnings.append(
                f"data.cover_si_per_section CSV {path.name} lacks a "
                f"'cover_si' column; falling back to scalar."
            )
            return None
        if len(df) != len(sections):
            warnings.append(
                f"data.cover_si_per_section length {len(df)} != "
                f"number of sections {len(sections)}. Falling back."
            )
            return None
        arr = df["cover_si"].astype(float).to_numpy()
        if (arr < -1e-9).any() or (arr > 1.0 + 1e-9).any():
            warnings.append(
                f"data.cover_si_per_section values out of [0, 1] "
                f"(min={arr.min()}, max={arr.max()}); falling back."
            )
            return None
        return np.clip(arr, 0.0, 1.0)

    def _maybe_run_composite_hsi(
        self,
        wua_df: pd.DataFrame,
        thermal_metrics_dict: dict | None,
        cover_metrics_dict: dict | None,
        out_dir: Path,
        formats: list[str],
        warnings: list[str],
        method: str = "product",
        per_cell_csi: PerCellCsiMap | None = None,
        per_section_thermal_si: np.ndarray | None = None,
        per_section_cover_si: np.ndarray | None = None,
    ) -> tuple[dict[str, Any] | None, pd.DataFrame | None]:
        """v1.6.0: combine the per-cell depth × velocity WUA with the
        v1.1.1 thermal scalar and v1.5.0 cover scalar overlays into a
        single composite WUA-Q table.

        Returns ``(None, None)`` (silently skipped) when neither overlay
        was produced — preserving v1.5.x semantics for cases without
        fetched climate or LULC. When at least one overlay is present,
        writes:

        * ``composite_wua_q.parquet`` and/or ``composite_wua_q.csv``
          (paired ``wua_m2_composite_<sp>_<stage>`` columns alongside
          the base ``wua_m2_*`` columns).
        * ``composite_hsi.json`` (overlay factors + per-series max WUA
          ratios for review).

        v1.7.0: also returns the resolved ``composite_df`` so the
        downstream regulatory_export step (5f) can emit paired
        composite reports without recomputing.
        """
        from openlimno.habitat.composite import (
            CompositeOverlay,
            apply_overlay,
            composite_summary,
        )

        overlay = CompositeOverlay.from_metrics(
            thermal_metrics_dict, cover_metrics_dict,
            warnings=warnings,
        )
        if overlay.overlay_si is None:
            return None, None

        # v1.7.1 (review F8): refuse to write composite artefacts when
        # there are no `wua_m2_*` base columns — apply_overlay would
        # silently produce a parquet with no composite columns, which
        # is more misleading than no parquet at all.
        base_cols = [
            c for c in wua_df.columns
            if c.startswith("wua_m2_")
            and not c.startswith("wua_m2_composite_")
        ]
        if not base_cols:
            warnings.append(
                "composite_hsi: wua_df carries no `wua_m2_*` columns; "
                "skipping composite emission."
            )
            return None, None

        # v1.7.1 (review F5): an overlay_si of exactly zero produces
        # downstream failures in WFD (reference WUA = 0) and degenerate
        # SL-712 / FERC recommendations. Surface this loudly and skip
        # the composite emission rather than ship reports a regulator
        # can't act on.
        if overlay.overlay_si == 0.0:
            warnings.append(
                f"composite_hsi: overlay_si=0 (cover_si={overlay.cover_si}, "
                f"thermal_si={overlay.thermal_si}). Habitat is fully "
                f"unavailable under at least one constraint — composite "
                f"artefacts are not emitted to avoid degenerate "
                f"regulatory recommendations."
            )
            return None, None

        # v1.7.1 (review F1): compute the summary BEFORE writing any
        # files. If summary computation raises (e.g. malformed wua_df),
        # we leave the output directory clean instead of producing a
        # parquet/csv pair with no matching composite_hsi.json.
        if method == "geom_mean_per_cell":
            composite_df, summary = self._maybe_run_per_cell_composite(
                wua_df, overlay, per_cell_csi, warnings,
                per_section_thermal_si=per_section_thermal_si,
                per_section_cover_si=per_section_cover_si,
            )
            if composite_df is None:
                return None, None
        else:
            composite_df = apply_overlay(wua_df, overlay, method=method)
            summary = composite_summary(wua_df, overlay, method=method)
        if "parquet" in formats:
            self._atomic_write(
                out_dir / "composite_wua_q.parquet",
                lambda p: composite_df.to_parquet(p, index=False),
            )
        if "csv" in formats:
            self._atomic_write(
                out_dir / "composite_wua_q.csv",
                lambda p: composite_df.to_csv(p, index=False),
            )
        self._atomic_write(
            out_dir / "composite_hsi.json",
            lambda p: p.write_text(
                json.dumps(summary, indent=2, default=str),
                encoding="utf-8",
            ),
        )

        if overlay.cover_si is None:
            warnings.append(
                "composite_hsi: thermal-only overlay (cover SI unavailable)."
            )
        elif overlay.thermal_si is None:
            warnings.append(
                "composite_hsi: cover-only overlay (thermal SI unavailable)."
            )
        return summary, composite_df

    @staticmethod
    def _atomic_write(target: Path, writer: Callable[[Path], None]) -> None:
        """v1.9.0: generalized atomic-publish helper.

        Hand any ``writer(tmp_path)`` callable that takes a Path and
        writes to it; this helper:

        1. Allocates a unique sibling tempfile via ``tempfile.mkstemp``
           (random suffix → concurrent-write safe; replaces the fixed
           ``.publishtmp`` suffix from v1.8.2 which collided when two
           writers raced the same target).
        2. Invokes ``writer(publish_path)`` to render the content.
        3. Atomically publishes via ``os.replace(publish_path, target)``
           — POSIX/NTFS guarantee atomicity for paths on the same
           filesystem. Any reader either sees the previous content (or
           a missing file) or the fully-written new content; no
           intermediate state is observable.
        4. Restores umask-respecting permissions (``0o666 & ~umask``)
           because ``tempfile.mkstemp`` creates 0600 files by default —
           the v1.8.3 fix carried over from ``_emit_regulatory_csv``.
        5. On any exception during render or replace, removes the
           orphan tempfile so the output directory stays clean.

        Generalizes the atomic-publish pattern that
        ``_emit_regulatory_csv`` proved in v1.7.1-v1.8.3; round-4 review
        flagged the rest of OpenLimno's output writers as a "contract
        uneven-ness" — every Case.run output now goes through this
        same path.
        """
        import tempfile as _tempfile
        target_dir = target.parent
        base = target.name
        pub_fd, pub_path_str = _tempfile.mkstemp(
            prefix=f".{base}.publish.", suffix=".tmp", dir=target_dir,
        )
        os.close(pub_fd)
        publish = Path(pub_path_str)
        try:
            writer(publish)
            # v1.9.1 (5th-review R5-1): chmod the publish tempfile BEFORE
            # os.replace so content and umask-respecting permissions
            # become visible to readers atomically together. Previously
            # (v1.8.3 → v1.9.0) chmod ran after os.replace, leaving a
            # narrow window where a concurrent non-owner reader could
            # observe the published file as 0o600 (mkstemp default) and
            # fail before chmod restored 0o644. Both codex and gemini
            # flagged this in the 5th-pass review.
            try:
                current_umask = os.umask(0)
                os.umask(current_umask)
                os.chmod(publish, 0o666 & ~current_umask)
            except OSError:
                # chmod can fail on filesystems that don't support
                # permission bits (some FAT mounts). Continue to
                # os.replace anyway; the file is still published.
                pass
            os.replace(publish, target)
        except BaseException:
            publish.unlink(missing_ok=True)
            raise

    @staticmethod
    def _write_csv_with_header(df: pd.DataFrame, path: Path, header_line: str | None) -> None:
        """v1.9.0: routes through ``_atomic_write`` so wua_q.csv and
        wua_hmu.csv inherit the same atomicity + umask semantics as the
        regulatory CSVs from the v1.7.1/v1.8.3 chain."""
        def _render(tmp: Path) -> None:
            if header_line:
                with tmp.open("w", encoding="utf-8") as f:
                    f.write(header_line)
                    df.to_csv(f, index=False)
            else:
                df.to_csv(tmp, index=False)
        Case._atomic_write(path, _render)

    def _compute_wua_quality(
        self,
        hsi_curves: dict[tuple[str, str, str], HSICurve],
        species_list: list[str],
        stage_list: list[str],
        warnings: list[str],
    ) -> str:
        """Determine the worst quality_grade among curves used by this case.

        SPEC §4.2.2.1 / ADR-0006: A → high confidence, C → tentative.
        Result drives output watermarking.
        """
        rank = {"A": 3, "B": 2, "C": 1}
        worst = "A"
        for species in species_list:
            for stage in stage_list:
                for var in ("depth", "velocity"):
                    key = (species, stage, var)
                    if key in hsi_curves:
                        g = hsi_curves[key].quality_grade
                        if rank[g] < rank[worst]:
                            worst = g
        return worst

    def _compute_cell_wua(
        self,
        results: list[Any],
        hsi_curves: dict[tuple[str, str, str], HSICurve],
        species: str,
        stage: str,
        composite: str,
        ack: bool,
        warnings: list[str],
    ) -> float:
        csi, areas = self._compute_cell_csi_and_area(
            results, hsi_curves, species, stage, composite, ack, warnings,
        )
        if csi is None:
            return 0.0
        return float(cell_wua(csi, areas))

    def _compute_cell_csi_and_area(
        self,
        results: list[Any],
        hsi_curves: dict[tuple[str, str, str], HSICurve],
        species: str,
        stage: str,
        composite: str,
        ack: bool,
        warnings: list[str],
    ) -> tuple[np.ndarray | None, np.ndarray]:
        """v2.4.0: per-cell CSI + per-cell area for a given (Q, species,
        stage). Lifted out of :meth:`_compute_cell_wua` so the
        per-cell composite path in :meth:`_maybe_run_composite_hsi`
        can call :func:`apply_overlay_per_cell` directly without
        re-running the hydraulic evaluation.

        Returns ``(csi_per_cell, area_per_cell)`` — ``csi_per_cell``
        is ``None`` when no HSI variables resolved (preserves the
        original ``_compute_cell_wua`` warning behaviour). The
        column-level path always sums the product to get the
        reach-total WUA; the per-cell path consumes the arrays
        directly.
        """
        depths = np.array([r.depth_mean_m for r in results])
        velocities = np.array([r.velocity_mean_ms for r in results])
        areas = np.array([r.area_m2 for r in results])

        suits: dict[str, np.ndarray] = {}
        for var, vals in [("depth", depths), ("velocity", velocities)]:
            key = (species, stage, var)
            if key in hsi_curves:
                curve = hsi_curves[key]
                suits[var] = curve.evaluate(vals)
            else:
                warnings.append(f"No HSI curve for ({species}, {stage}, {var}); skipped variable")

        if not suits:
            warnings.append(f"No HSI vars resolved for ({species}, {stage})")
            return None, areas

        csi = composite_csi(suits, method=composite)  # type: ignore[arg-type]
        return csi, areas

    def _write_hydraulic_netcdf(
        self, results: dict[float, list[Any]], sections: list[CrossSection], path: Path
    ) -> None:
        import xarray as xr

        Qs = sorted(results.keys())
        stations = [s.station_m for s in sections]
        depth = np.zeros((len(Qs), len(sections)))
        velocity = np.zeros_like(depth)
        wse = np.zeros_like(depth)
        area = np.zeros_like(depth)

        for i, Q in enumerate(Qs):
            for j, r in enumerate(results[Q]):
                depth[i, j] = r.depth_mean_m
                velocity[i, j] = r.velocity_mean_ms
                wse[i, j] = r.water_surface_m
                area[i, j] = r.area_m2

        ds = xr.Dataset(
            data_vars={
                "water_depth": (
                    ("discharge", "station"),
                    depth,
                    {
                        "standard_name": "water_depth",
                        "units": "m",
                    },
                ),
                "velocity_magnitude": (
                    ("discharge", "station"),
                    velocity,
                    {
                        "long_name": "section-averaged velocity magnitude",
                        "units": "m s-1",
                    },
                ),
                "water_surface": (
                    ("discharge", "station"),
                    wse,
                    {
                        "long_name": "water surface elevation",
                        "units": "m",
                    },
                ),
                "wetted_area": (
                    ("discharge", "station"),
                    area,
                    {
                        "long_name": "cross-section wetted area",
                        "units": "m2",
                    },
                ),
            },
            coords={
                "discharge": ("discharge", Qs, {"units": "m3 s-1"}),
                "station": ("station", stations, {"units": "m"}),
            },
            attrs={
                "Conventions": "CF-1.8",
                "title": f"OpenLimno Builtin1D hydraulic results for case '{self.name}'",
                "openlimno_version": __version__,
                "openlimno_wedm_version": "0.1",
            },
        )
        # v1.9.2 (5th-review R5-3): atomic publish for hydraulics.nc.
        # netcdf4's `to_netcdf(path)` writes directly to the path and
        # doesn't accept a file-like buffer; route via Case._atomic_write
        # so the target appears with full content + umask perms in a
        # single atomic step. The writer just calls to_netcdf on the
        # sibling tempfile the helper allocates.
        Case._atomic_write(
            path,
            lambda p: ds.to_netcdf(p, engine="netcdf4"),
        )

    def _build_provenance(
        self,
        discharges: list[float],
        sections: list[CrossSection],
        species: list[str],
        stages: list[str],
        warnings: list[str],
        studyplan: object | None = None,
        wua_quality_grade: str = "A",
        data_paths: dict[str, Path] | None = None,
        thermal_metrics_dict: dict | None = None,
        cover_metrics_dict: dict | None = None,
        composite_summary_dict: dict | None = None,
    ) -> dict[str, Any]:
        case_yaml_text = self.case_yaml_path.read_bytes()
        case_sha = hashlib.sha256(case_yaml_text).hexdigest()

        try:
            git_sha = (
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],
                    stderr=subprocess.DEVNULL,
                    cwd=self.case_yaml_path.parent,
                )
                .decode()
                .strip()
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            git_sha = "unknown"

        # Hash input data files (SPEC §1 P7 — input data SHA-256)
        input_data_sha: dict[str, str] = {}
        for label, p in (data_paths or {}).items():
            try:
                input_data_sha[label] = hashlib.sha256(Path(p).read_bytes()).hexdigest()
            except OSError:
                input_data_sha[label] = "unreadable"

        # v0.3 P0: external-source sidecar (auto-fetched datasets from
        # USGS NWIS / Copernicus DEM / etc.). Carries source URL +
        # fetch_time + SHA-256 so `openlimno reproduce` can verify
        # auto-fetched data hasn't been mutated.
        external_sources: list[dict] = []
        try:
            from openlimno.preprocess.fetch.sidecar import (
                SidecarCorruptedError,
                read_sidecar,
            )
            external_sources = read_sidecar(self.case_yaml_path.parent)
        except ImportError:
            # fetch module optional in case of stripped install
            pass
        except SidecarCorruptedError as e:
            # Surface in run warnings so the user knows the provenance
            # trail is broken — but don't crash the run (the science
            # results are still valid; only the audit trail is lost).
            warnings.append(
                f"external-source sidecar corrupted: {e}. "
                f"provenance.external_sources will be empty for this run."
            )

        # Hash pixi.lock if present (dependency lock fingerprint)
        pixi_lock_sha = None
        for candidate in [
            self.case_yaml_path.parent.parent / "pixi.lock",
            Path.cwd() / "pixi.lock",
        ]:
            if candidate.exists():
                pixi_lock_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
                break

        # v0.6: surface WEDM v0.2 fetch-system data blocks in provenance.
        # This is descriptive metadata — the source-of-truth for re-use
        # remains the sidecar's per-record SHA. fetch_summary lets a
        # human reader see at a glance which fetched layers backed
        # this run, without joining sidecar to case.yaml manually.
        import yaml as _yaml_v06
        try:
            _case_doc = _yaml_v06.safe_load(case_yaml_text) or {}
        except Exception:  # noqa: BLE001
            _case_doc = {}
        fetch_summary: dict[str, dict] = {}
        case_data_block = _case_doc.get("data", {}) or {}
        for key in (
            "dem", "lulc", "soil", "watershed",
            "species_occurrences", "climate",
        ):
            block = case_data_block.get(key)
            if isinstance(block, dict):
                # Whitelist primitive scalars only — large arrays
                # (class_km2 with 11 entries is OK; the histogram lives
                # in the sidecar too anyway).
                fetch_summary[key] = {
                    k: v for k, v in block.items()
                    if isinstance(v, (str, int, float, bool, list, dict))
                }
            elif isinstance(block, str):
                fetch_summary[key] = {"uri": block}

        # v0.6: species-match validation — surface a loud warning when
        # the GBIF taxon match for the case species was NONE (the user
        # wrote a name GBIF couldn't resolve). Anything but NONE is fine
        # for provenance; downstream habitat scientific work needs the
        # canonical name + family which are already in fetch_summary.
        sp_block = fetch_summary.get("species_occurrences", {})
        if sp_block.get("match_type") == "NONE":
            warnings.append(
                f"GBIF could not match species "
                f"{sp_block.get('scientific_name', '?')!r} (match_type=NONE). "
                f"The downstream habitat / HSI results assume this species "
                f"identity is valid — verify the spelling before publishing."
            )
        # v1.1.2: layered occurrence-density warnings + density class
        # tag for reporting. The thresholds bracket what's reasonable
        # for inferring "the habitat model is being run in territory
        # the species actually inhabits":
        #   * 0           — see v0.6 warning above (full miss)
        #   * 1..9        — "sparse": modelled habitat is extrapolation,
        #                   not validation. Worth flagging loudly.
        #   * 10..99      — "thin": OK but acknowledge data limitation.
        #   * 100+        — "dense": confidence-building cross-check.
        sp_total = sp_block.get("occurrence_count_total")
        if sp_total == 0:
            density_class = "absent"
            warnings.append(
                f"Species {sp_block.get('scientific_name', '?')!r} has "
                f"ZERO GBIF occurrences inside the case bbox. The "
                f"habitat/HSI model is being run for a species with "
                f"no observed records in the area — confirm this is "
                f"intentional (e.g., restoration / introduction case)."
            )
        elif isinstance(sp_total, int) and sp_total < 10:
            density_class = "sparse"
            warnings.append(
                f"Species {sp_block.get('scientific_name', '?')!r} has "
                f"only {sp_total} GBIF occurrence(s) inside the case "
                f"bbox — the habitat / HSI results are extrapolating "
                f"beyond observed range. Treat any quantitative "
                f"recommendation downstream as TENTATIVE."
            )
        elif isinstance(sp_total, int) and sp_total < 100:
            density_class = "thin"
        elif isinstance(sp_total, int):
            density_class = "dense"
        else:
            density_class = "unknown"
        # Tag the species block in fetch_summary so downstream
        # reporting / dashboard rendering can colour-code without
        # re-thresholding.
        fetch_summary.setdefault("species_occurrences", {})[
            "density_class"
        ] = density_class

        # Parameter fingerprint = sha256(yaml + studyplan + sorted discharges)
        param_blob = case_yaml_text + b"\n"
        if studyplan is not None and hasattr(studyplan, "config"):
            import json as _json

            param_blob += _json.dumps(studyplan.config, sort_keys=True).encode("utf-8")
        param_blob += repr(sorted(discharges)).encode("utf-8")
        parameter_fingerprint = hashlib.sha256(param_blob).hexdigest()

        return {
            "openlimno_version": __version__,
            "wedm_version": "0.1",
            "schema": "openlimno-provenance/0.1",
            "run_at": datetime.now(UTC).isoformat(),
            "case": {
                "name": self.name,
                "yaml_path": str(self.case_yaml_path),
                "yaml_sha256": case_sha,
            },
            "git_sha": git_sha,
            "machine": {
                "host": socket.gethostname(),
                "platform": platform.platform(),
                "python": sys.version,
            },
            "inputs": {
                "n_sections": len(sections),
                "discharges_m3s": discharges,
                "species": species,
                "stages": stages,
                "input_data_sha256": input_data_sha,  # SPEC §1 P7
            },
            "external_sources": external_sources,  # v0.3 P0
            "fetch_summary": fetch_summary,  # v0.6 (WEDM v0.2 data blocks)
            "thermal_metrics": thermal_metrics_dict,  # v1.1.1 (None if no climate × FishBase)
            "cover_metrics": cover_metrics_dict,  # v1.5.0 (None if no lulc × watershed)
            "composite_summary": composite_summary_dict,  # v1.6.0 (None unless ≥1 overlay present)
            "dependencies": {
                "pixi_lock_sha256": pixi_lock_sha,
                "container_image_sha": None,  # M3 beta: extract from SCHISM run
            },
            "parameter_fingerprint": parameter_fingerprint,
            "studyplan_present": studyplan is not None,
            "wua_quality_grade": wua_quality_grade,
            "warnings": warnings,
        }


__all__ = ["Case", "CaseRunResult"]
