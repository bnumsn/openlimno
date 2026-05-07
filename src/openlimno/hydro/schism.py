"""SCHISM adapter — subprocess wrapper. SPEC §6.1, ADR-0002.

This adapter prepares SCHISM input files from a WEDM case, spawns the SCHISM
executable (or container), and reads ``schout_*.nc`` results back into WEDM.

LTS pin: SCHISM v5.11.0 (ADR-0002).

M3 scope (this iteration): full prepare/run/read_results lifecycle plus
``ol_mode='dry-run'`` that produces all input files but skips the actual
SCHISM invocation, useful for CI without SCHISM installed.

This skeleton is fully testable in environments WITHOUT SCHISM via dry-run.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

LTS_VERSION = "5.11.0"


@dataclass
class SCHISMRunReport:
    """Outcome of a SCHISM run."""

    work_dir: Path
    return_code: int
    duration_seconds: float
    schout_path: Path | None
    log_path: Path
    dry_run: bool = False


@dataclass
class SCHISMAdapter:
    """SCHISM subprocess wrapper.

    Parameters
    ----------
    executable
        Path to SCHISM binary (e.g. ``pschism_TVD-VL``). If None, will look
        for ``OPENLIMNO_SCHISM`` environment variable, then PATH.
    container_image
        OCI image (e.g. ``ghcr.io/openlimno/schism:5.11.0``). If set,
        overrides ``executable`` and runs SCHISM via ``docker run`` /
        ``apptainer run``.
    n_procs
        Number of MPI processes (default 1; SCHISM serial build).
    timeout_s
        Subprocess timeout in seconds. None = unlimited.
    """

    executable: str | None = None
    container_image: str | None = None
    container_runtime: Literal["docker", "apptainer", "podman"] = "docker"
    n_procs: int = 1
    timeout_s: float | None = None
    lts_version: str = LTS_VERSION

    _input_files: list[str] = field(
        default_factory=lambda: [
            "hgrid.gr3",
            "vgrid.in",
            "param.nml",
            "bctides.in",
        ]
    )

    # ------------------------------------------------------------------
    # HydroSolver Protocol
    # ------------------------------------------------------------------
    def prepare(
        self,
        case_yaml: str | Path,
        work_dir: str | Path,
        wedm_mesh_path: str | Path | None = None,
        param_overrides: dict[str, Any] | None = None,
    ) -> Path:
        """Stage SCHISM input files in ``work_dir``.

        If ``wedm_mesh_path`` points to a UGRID-2D NetCDF, generates a real
        ``hgrid.gr3`` derived from it. Otherwise writes a clearly-marked
        placeholder. Always writes a usable ``param.nml`` skeleton, single-
        layer ``vgrid.in`` (depth-averaged), and ``bctides.in`` stub.
        """
        work_dir = Path(work_dir).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)

        used_real_mesh = False
        if wedm_mesh_path is not None and Path(wedm_mesh_path).exists():
            try:
                _write_hgrid_from_ugrid(Path(wedm_mesh_path), work_dir / "hgrid.gr3")
                used_real_mesh = True
                logger.info("hgrid.gr3 generated from %s", wedm_mesh_path)
            except Exception as e:
                logger.warning(
                    "UGRID → hgrid.gr3 conversion failed: %s; using placeholder",
                    e,
                )

        if not used_real_mesh:
            (work_dir / "hgrid.gr3").write_text(
                "! OpenLimno SCHISM adapter — hgrid.gr3 placeholder.\n"
                "! Provide wedm_mesh_path= (UGRID-2D NetCDF) to generate a real grid.\n"
                "! 1D cross-section data is not directly compatible with SCHISM 2D.\n"
                "0 0\n"  # 0 elements, 0 nodes — runs will fail with clear error
            )

        # SCHISM main parameter file (real, runnable skeleton)
        (work_dir / "param.nml").write_text(_render_param_nml(param_overrides))
        # vgrid.in: single-layer (depth-averaged) — valid for 2D habitat runs
        (work_dir / "vgrid.in").write_text("2 !ivcor\n1 !nvrt\n1 1.0 -1.0\n")
        # bctides.in stub: no tidal forcing; user supplies BCs if needed
        (work_dir / "bctides.in").write_text(
            "! bctides.in — supply boundary conditions per your case\n"
            "0   ! ntip\n0   ! nbfr\n0   ! nope (open boundary segments)\n"
        )

        marker = work_dir / ".openlimno_prepared"
        marker.write_text(
            json.dumps(
                {
                    "case_yaml": str(case_yaml),
                    "lts_version": self.lts_version,
                    "input_files": self._input_files,
                    "real_mesh": used_real_mesh,
                    "wedm_mesh_path": str(wedm_mesh_path) if wedm_mesh_path else None,
                }
            )
        )
        logger.info("SCHISM work_dir prepared at %s (real_mesh=%s)", work_dir, used_real_mesh)
        return work_dir

    def run(
        self,
        work_dir: str | Path,
        dry_run: bool = False,
    ) -> SCHISMRunReport:
        """Spawn SCHISM in ``work_dir`` and capture its output.

        ``dry_run=True`` skips the subprocess and returns a synthesized report;
        useful for CI environments without SCHISM installed.
        """
        import time

        work_dir = Path(work_dir).resolve()
        marker = work_dir / ".openlimno_prepared"
        if not marker.exists():
            raise RuntimeError(f"work_dir {work_dir} not prepared; call prepare() first")

        log_path = work_dir / "schism.log"
        start = time.time()

        if dry_run:
            log_path.write_text("DRY RUN — SCHISM not invoked\n")
            return SCHISMRunReport(
                work_dir=work_dir,
                return_code=0,
                duration_seconds=0.0,
                schout_path=None,
                log_path=log_path,
                dry_run=True,
            )

        try:
            cmd = self._build_command(work_dir)
        except RuntimeError as e:
            log_path.write_text(f"SCHISM executable not found: {e}\n")
            return SCHISMRunReport(
                work_dir=work_dir,
                return_code=127,
                duration_seconds=0.0,
                schout_path=None,
                log_path=log_path,
                dry_run=False,
            )
        logger.info("Spawning SCHISM: %s (cwd=%s)", " ".join(cmd), work_dir)

        with log_path.open("w", encoding="utf-8") as logf:
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=work_dir,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    timeout=self.timeout_s,
                    check=False,
                )
                rc = proc.returncode
            except subprocess.TimeoutExpired:
                logger.error("SCHISM timeout after %s s", self.timeout_s)
                rc = 124
            except FileNotFoundError as e:
                logger.error("SCHISM executable not found: %s", e)
                rc = 127

        duration = time.time() - start
        schout = next(work_dir.glob("schout_*.nc"), None)
        return SCHISMRunReport(
            work_dir=work_dir,
            return_code=rc,
            duration_seconds=duration,
            schout_path=schout,
            log_path=log_path,
            dry_run=False,
        )

    def read_results(self, work_dir: str | Path) -> object:
        """Read schout_*.nc results into a WEDM-conformant xarray.Dataset.

        Returns an xarray.Dataset with CF-style variable names; the WEDM
        normalisation (translating SCHISM variables to ``water_depth`` /
        ``velocity_x`` etc.) is M3 beta.
        """
        import xarray as xr

        work_dir = Path(work_dir).resolve()
        schout_files = sorted(work_dir.glob("schout_*.nc"))
        if not schout_files:
            raise FileNotFoundError(f"No schout_*.nc found in {work_dir}; was the run successful?")
        # Open as multi-file dataset
        return xr.open_mfdataset(schout_files, combine="by_coords")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_command(self, work_dir: Path) -> list[str]:
        """Build the subprocess argv for the SCHISM run."""
        if self.container_image:
            # Container path
            mount = f"{work_dir}:/work"
            if self.container_runtime in ("docker", "podman"):
                return [
                    self.container_runtime,
                    "run",
                    "--rm",
                    "-v",
                    mount,
                    "-w",
                    "/work",
                    self.container_image,
                ]
            if self.container_runtime == "apptainer":
                return [
                    "apptainer",
                    "run",
                    "--bind",
                    mount,
                    self.container_image,
                ]
        # Native path
        exe = (
            self.executable
            or os.environ.get("OPENLIMNO_SCHISM")
            or shutil.which("pschism_TVD-VL")
            or shutil.which("schism")
        )
        if not exe:
            raise RuntimeError(
                "No SCHISM executable found. Set executable=, container_image=, "
                "or OPENLIMNO_SCHISM env var. ADR-0002 recommends the OCI container "
                "ghcr.io/openlimno/schism:5.11.0."
            )
        if self.n_procs > 1:
            return ["mpirun", "-n", str(self.n_procs), exe]
        return [exe]


def _render_param_nml(overrides: dict[str, Any] | None = None) -> str:
    """Render a SCHISM param.nml namelist with sensible OpenLimno defaults.

    Users can override any value via the ``param_overrides`` dict in
    ``SCHISMAdapter.prepare(..., param_overrides=...)``.
    """
    defaults: dict[str, Any] = {
        "ipre": 0,  # 0 = run, 1 = pre-process only
        "ibc": 0,  # baroclinic option (0 = barotropic)
        "rnday": 1.0,  # simulation length in days
        "dt": 100.0,  # time step in s
        "msc2": 24,
        "mdc2": 30,
        "ihot": 0,  # cold start
        "indvel": 1,
        "ihorcon": 0,
    }
    if overrides:
        defaults.update(overrides)

    lines = ["&CORE"]
    for k, v in defaults.items():
        if isinstance(v, bool):
            v = "T" if v else "F"
        lines.append(f"  {k} = {v}")
    lines.append("/")
    return "\n".join(lines) + "\n"


def _write_hgrid_from_ugrid(ugrid_path: Path, hgrid_path: Path) -> None:
    """Convert a UGRID-2D NetCDF mesh into a SCHISM hgrid.gr3 ASCII file.

    SCHISM's hgrid.gr3 format:

        line 1:  mesh name (free text)
        line 2:  ne np                      (n elements, n nodes)
        next np lines:  i x y z             (1-indexed nodes)
        next ne lines:  i type n1 n2 n3 [n4]
        (boundary blocks omitted; user can add)

    UGRID conventions: ``mesh2d_face_nodes`` with fill_value indicating
    "not a node" (typically -1 or NetCDF _FillValue).
    """
    import numpy as np
    import xarray as xr

    ds = xr.open_dataset(ugrid_path)
    try:
        # Try common UGRID variable names
        x_name = next((n for n in ("mesh2d_node_x", "node_x") if n in ds.variables), None)
        y_name = next((n for n in ("mesh2d_node_y", "node_y") if n in ds.variables), None)
        face_name = next(
            (n for n in ("mesh2d_face_nodes", "face_nodes") if n in ds.variables),
            None,
        )
        if x_name is None or y_name is None or face_name is None:
            raise ValueError("UGRID mesh missing required vars (mesh2d_node_x/y/face_nodes)")
        x = np.asarray(ds[x_name].values, dtype=float)
        y = np.asarray(ds[y_name].values, dtype=float)
        face_nodes = np.asarray(ds[face_name].values)

        # Bottom elevation (z): try several CF names; default 0
        z_name = next(
            (n for n in ("bottom_elevation", "depth", "node_z") if n in ds.variables),
            None,
        )
        z = np.asarray(ds[z_name].values, dtype=float) if z_name else np.zeros_like(x)

        # Detect fill value in face_nodes
        fill = ds[face_name].attrs.get("_FillValue", -1)
        # Convert to 1-indexed for SCHISM
        ne = face_nodes.shape[0]
        np_count = len(x)
    finally:
        ds.close()

    # Write
    with hgrid_path.open("w", encoding="utf-8") as f:
        f.write("OpenLimno UGRID-derived mesh\n")
        f.write(f"{ne} {np_count}\n")
        for i in range(np_count):
            f.write(f"{i + 1} {x[i]:.6f} {y[i]:.6f} {z[i]:.6f}\n")
        for i in range(ne):
            row = face_nodes[i]
            valid = [int(n) + 1 for n in row if int(n) != int(fill) and int(n) >= 0]
            t = len(valid)  # 3 = tri, 4 = quad
            f.write(f"{i + 1} {t} " + " ".join(str(n) for n in valid) + "\n")
        f.write("0 = number of open boundary segments\n")
        f.write("0 = number of land boundary segments\n")


__all__ = ["LTS_VERSION", "SCHISMAdapter", "SCHISMRunReport"]
