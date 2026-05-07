"""Case orchestrator. SPEC §8.1.

Loads a case YAML, validates it against WEDM, drives the configured solver,
runs habitat post-processing, and writes outputs + provenance.

M1 capability: builtin-1d hydraulics + WUA (cell-level) + WUA-Q sweep.
M2+ extends to SCHISM 2D, multi-scale aggregation, regulatory exports.
"""

from __future__ import annotations

import hashlib
import json
import platform
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


@dataclass
class CaseRunResult:
    """Container for end-to-end case results."""

    case_name: str
    case_dir: Path
    output_dir: Path
    sections: list[CrossSection]
    discharges_m3s: list[float]
    hydraulic_results: dict[float, list[Any]]  # Q -> list[MANSQResult]
    wua_q: pd.DataFrame                          # columns: discharge_m3s, wua_m2_<sp>_<stage>, ...
    provenance_path: Path
    warnings: list[str] = field(default_factory=list)

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
    def from_yaml(cls, path: str | Path) -> "Case":
        path = Path(path).resolve()
        errors = validate_case(path)
        if errors:
            raise ValueError(
                f"Case YAML failed schema validation:\n  - "
                + "\n  - ".join(errors)
            )
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
        cross_section_path = self._resolve(cfg.get("data", {}).get(
            "cross_section",
            "../../data/lemhi/cross_section.parquet"
        ))
        sections = load_sections_from_parquet(cross_section_path, manning_n=manning_n)

        # 2. Load HSI curves
        hsi_path = self._resolve(cfg.get("data", {}).get(
            "hsi_curve",
            "../../data/lemhi/hsi_curve.parquet"
        ))
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
            solver.prepare(self.case_yaml_path, hydro_work,
                           sections=sections, discharges_m3s=list(discharges_m3s))
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
                self.case_yaml_path, hydro_work,
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
                solver.prepare(self.case_yaml_path, hydro_work,
                               sections=sections, discharges_m3s=list(discharges_m3s))
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
                f"Unknown hydrodynamics backend '{backend}'. "
                "Supported: builtin-1d, schism."
            )

        # 4. Habitat (cell WUA-Q for each species/stage)
        habitat_cfg = cfg["habitat"]
        composite = habitat_cfg.get("composite", "geometric_mean")
        ack = bool(habitat_cfg.get("acknowledge_independence", False))
        # Hard guard before computing anything
        require_independence_ack(composite, ack)  # type: ignore[arg-type]

        species_list = habitat_cfg["species"]
        stage_list = habitat_cfg["stages"]

        wua_records: list[dict[str, Any]] = []
        for Q in discharges_m3s:
            row: dict[str, Any] = {"discharge_m3s": Q}
            for species in species_list:
                for stage in stage_list:
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
            hydraulic_results, hsi_curves, species_list, stage_list,
            composite=composite, ack=ack, warnings=warnings,
        )

        # 4c. StudyPlan TUF override (SPEC §4.4.1.1)
        sp_obj = self._load_studyplan(studyplan_path, warnings)

        # 4d. Drift egg evaluation (SPEC §4.2.6) - only if explicitly requested
        drift_results = self._maybe_drift_egg(
            cfg, hydraulic_results, sections, out_dir, warnings,
        )

        # 5. Outputs
        formats = cfg["output"]["formats"]
        # Watermark header for tentative HSI (computed below; pass to writers)
        wua_quality_grade = self._compute_wua_quality(
            hsi_curves, species_list, stage_list, warnings,
        )
        watermark_header = (
            self._wua_csv_header(wua_quality_grade) if "csv" in formats else None
        )
        if "csv" in formats:
            self._write_csv_with_header(wua_df, out_dir / "wua_q.csv", watermark_header)
            if hmu_df is not None and len(hmu_df) > 0:
                self._write_csv_with_header(hmu_df, out_dir / "wua_hmu.csv",
                                             watermark_header)
        if "parquet" in formats:
            wua_df.to_parquet(out_dir / "wua_q.parquet", index=False)
            if hmu_df is not None and len(hmu_df) > 0:
                hmu_df.to_parquet(out_dir / "wua_hmu.parquet", index=False)
        if "netcdf" in formats:
            self._write_hydraulic_netcdf(
                hydraulic_results, sections, out_dir / "hydraulics.nc"
            )

        # 5b. Regulatory exports (SPEC §4.2.4.2)
        reg_exports = cfg.get("regulatory_export", [])
        if reg_exports:
            self._run_regulatory_exports(
                reg_exports, wua_df, species_list, stage_list,
                out_dir, discharge_series_path, warnings,
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
            discharges_m3s, sections, species_list, stage_list, warnings,
            studyplan=sp_obj, wua_quality_grade=wua_quality_grade,
            data_paths={
                "cross_section": cross_section_path,
                "hsi_curve": hsi_path,
            },
        )
        prov_path.write_text(json.dumps(provenance, indent=2, default=str))

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

    def _resolve_mesh_uri(
        self, cfg: dict[str, Any], warnings: list[str]
    ) -> Path | None:
        """Resolve and validate ``cfg["mesh"]["uri"]`` (UGRID-2D NetCDF).

        Returns the resolved path on success, ``None`` if mesh missing or
        invalid (warnings recorded). Always non-fatal — builtin-1d does not
        require a mesh, and SCHISM falls back to a placeholder grid.
        """
        mesh_cfg = cfg.get("mesh", {})
        uri = mesh_cfg.get("uri")
        if not uri:
            return None
        path = self._resolve(uri)
        if not path.exists():
            warnings.append(f"mesh.uri does not exist: {path}")
            return None
        try:
            from openlimno.preprocess import validate_ugrid_mesh
            report = validate_ugrid_mesh(path)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"mesh validation failed: {e}")
            return path
        if not report.is_valid:
            warnings.append(
                "UGRID mesh validation FAILED: "
                + "; ".join(report.errors)
            )
            return None
        if report.warnings:
            warnings.append(
                f"UGRID mesh warnings ({path.name}): "
                + "; ".join(report.warnings)
            )
        warnings.append(
            f"Mesh OK: {report.n_nodes} nodes, {report.n_faces} faces "
            f"({path.name})"
        )
        return path

    def _aggregate_hmu(
        self,
        hydraulic_results: dict[float, list[Any]],
        hsi_curves: dict[tuple[str, str, str], "HSICurve"],
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
                        rows.append({
                            "discharge_m3s": float(Q),
                            "species": species,
                            "life_stage": stage,
                            "hmu_type": h["hmu_type"],
                            "wua_m2": float(h["wua_m2"]),
                            "n_sections": int(h["n_sections"]),
                        })
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
            warnings.append(
                f"StudyPlan loaded with {len(sp.tuf_overrides())} TUF overrides"
            )
            return sp
        except Exception as e:  # noqa: BLE001
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
        except Exception as e:  # noqa: BLE001
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
                warnings.append(
                    f"drift-egg: all-zero velocities at Q={Q}; skipping that discharge"
                )
                continue
            try:
                res = evaluate_drifting_egg(
                    species=species,
                    spawning_station_m=spawning_station_m,
                    velocity_along_reach=u_field,
                    temperature_along_reach=T_field,
                    hatch_temp_days_curve=params["hatch_temp_days_curve"],  # type: ignore[arg-type]
                    mortality_velocity_threshold_ms=params[
                        "mortality_velocity_threshold_ms"
                    ],  # type: ignore[arg-type]
                    dt_s=dt_s,
                    max_drift_km=max_drift_km,
                )
            except Exception as e:  # noqa: BLE001
                warnings.append(f"drift-egg eval failed at Q={Q}: {e}")
                continue
            rows.append({
                "discharge_m3s": float(Q),
                "species": res.species,
                "spawning_station_m": res.spawning_station_m,
                "hatch_station_m": res.hatch_station_m,
                "drift_distance_km": res.drift_distance_km,
                "hatch_temp_C_mean": res.hatch_temp_C_mean,
                "mortality_fraction": res.mortality_fraction,
                "success": bool(res.success),
            })

        if not rows:
            return None
        df = pd.DataFrame(rows)
        df.to_csv(out_dir / "drift_egg.csv", index=False)
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
            except Exception as e:  # noqa: BLE001
                warnings.append(f"drift-egg temperature CSV load failed: {e}")
                return None
            scol = forcing.get("station_column", "station_m")
            tcol = forcing.get("temp_column", "temp_C")
            if scol not in df.columns or tcol not in df.columns:
                warnings.append(
                    f"drift-egg temperature CSV missing columns {scol!r} or {tcol!r}"
                )
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
    ) -> None:
        """Auto-invoke regulatory_export submodules when listed in case YAML."""
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

        for export_kind in export_list:
            try:
                if export_kind == "CN-SL712":
                    from openlimno.habitat.regulatory_export import cn_sl712
                    res = cn_sl712.compute_sl712(Q, wua_q, species, stage)
                    res.to_csv(out_dir / "sl712.csv")
                elif export_kind == "US-FERC-4e":
                    from openlimno.habitat.regulatory_export import us_ferc_4e
                    res = us_ferc_4e.compute_ferc_4e(Q, wua_q, species, stage)
                    res.to_csv(out_dir / "ferc_4e.csv")
                elif export_kind == "EU-WFD":
                    from openlimno.habitat.regulatory_export import eu_wfd
                    res = eu_wfd.compute_wfd(Q, wua_q, species, stage)
                    res.to_csv(out_dir / "eu_wfd.csv")
                else:
                    warnings.append(f"Unknown regulatory_export kind: {export_kind}")
            except Exception as e:  # noqa: BLE001
                warnings.append(
                    f"regulatory_export[{export_kind}] failed: {e}"
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

    @staticmethod
    def _write_csv_with_header(
        df: pd.DataFrame, path: Path, header_line: str | None
    ) -> None:
        if header_line:
            with path.open("w", encoding="utf-8") as f:
                f.write(header_line)
                df.to_csv(f, index=False)
        else:
            df.to_csv(path, index=False)

    def _compute_wua_quality(
        self,
        hsi_curves: dict[tuple[str, str, str], "HSICurve"],
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
                warnings.append(
                    f"No HSI curve for ({species}, {stage}, {var}); skipped variable"
                )

        if not suits:
            warnings.append(f"No HSI vars resolved for ({species}, {stage})")
            return 0.0

        csi = composite_csi(suits, method=composite)  # type: ignore[arg-type]
        return float(cell_wua(csi, areas))

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
                "water_depth": (("discharge", "station"), depth, {
                    "standard_name": "water_depth",
                    "units": "m",
                }),
                "velocity_magnitude": (("discharge", "station"), velocity, {
                    "long_name": "section-averaged velocity magnitude",
                    "units": "m s-1",
                }),
                "water_surface": (("discharge", "station"), wse, {
                    "long_name": "water surface elevation",
                    "units": "m",
                }),
                "wetted_area": (("discharge", "station"), area, {
                    "long_name": "cross-section wetted area",
                    "units": "m2",
                }),
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
        ds.to_netcdf(path, engine="netcdf4")

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
    ) -> dict[str, Any]:
        case_yaml_text = self.case_yaml_path.read_bytes()
        case_sha = hashlib.sha256(case_yaml_text).hexdigest()

        try:
            git_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL,
                cwd=self.case_yaml_path.parent,
            ).decode().strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            git_sha = "unknown"

        # Hash input data files (SPEC §1 P7 — input data SHA-256)
        input_data_sha: dict[str, str] = {}
        for label, p in (data_paths or {}).items():
            try:
                input_data_sha[label] = hashlib.sha256(
                    Path(p).read_bytes()
                ).hexdigest()
            except OSError:
                input_data_sha[label] = "unreadable"

        # Hash pixi.lock if present (dependency lock fingerprint)
        pixi_lock_sha = None
        for candidate in [
            self.case_yaml_path.parent.parent / "pixi.lock",
            Path.cwd() / "pixi.lock",
        ]:
            if candidate.exists():
                pixi_lock_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
                break

        # Parameter fingerprint = sha256(yaml + studyplan + sorted discharges)
        param_blob = case_yaml_text + b"\n"
        if studyplan is not None and hasattr(studyplan, "config"):
            import json as _json
            param_blob += _json.dumps(
                studyplan.config, sort_keys=True
            ).encode("utf-8")
        param_blob += repr(sorted(discharges)).encode("utf-8")
        parameter_fingerprint = hashlib.sha256(param_blob).hexdigest()

        return {
            "openlimno_version": __version__,
            "wedm_version": "0.1",
            "schema": "openlimno-provenance/0.1",
            "run_at": datetime.now(timezone.utc).isoformat(),
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
