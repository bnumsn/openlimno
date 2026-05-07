# ADR-0002: SCHISM integration: subprocess wrapper with LTS pin

- **Status**: **Accepted** — promoted from Proposed on 2026-05-07 after upstream survey
- **Date**: 2026-05-07
- **SPEC sections**: §1 P2, §2.3, §6.1
- **Tags**: hydro, schism, dependency, accepted

## Context

SPEC §1 P2 mandates SCHISM as the sole 2D backend in 1.0 (rejecting "solver supermarket"). Question: how do we integrate?

Three sub-questions:
1. **Linkage**: in-process (linked library) vs out-of-process (subprocess)
2. **Version**: track upstream master vs pin LTS
3. **Inputs**: text-template generation vs structured (`pyschism`)

Gemini round 2 review (recorded in SPEC Appendix B): SCHISM input files (`hgrid.gr3`, `param.nml`) are version-sensitive and brittle if parsed via regex / log scraping. This is the highest under-recognized risk in v0.2.

## M0 upstream survey (2026-05-07)

| Source | Result |
|---|---|
| GitHub releases | Latest **v5.11.0** (2025-02-07); previous v5.9.0 (2022-05-11). Slow cadence: ~3 years between releases. |
| conda-forge | **NOT packaged**. Users cannot `conda install schism`. |
| PyPI | `pyschism` 0.1.15 available (Python pre/post-processing helpers, no solver) |
| Source build | CMake + Fortran (gfortran ≥ 9 / Intel) + MPI (OpenMPI / MPICH) + HDF5 / NetCDF-Fortran |

**Implication**: The conda-forge primary path assumed in v0 of this ADR is **not feasible**. We must distribute via container or document source-build.

## Decision

1. **Subprocess wrapper, not in-process linkage.** OpenLimno launches SCHISM as a child process and communicates via files (NetCDF result, log for diagnostics only).
2. **LTS pin: SCHISM v5.11.0.** Sole supported version for OpenLimno 1.0. Upgrade to a future v5.12+ is a deliberate PR + full regression. Despite "LTS" being aspirational (SCHISM doesn't formally label LTS releases), v5.11.0's two-year stability and active community position it as the de facto LTS.
3. **Use `pyschism` 0.1.x** for input file generation (`hgrid.gr3`, `param.nml`, `bctides.in`). Where `pyschism` lacks a field, contribute upstream rather than fork.
4. **Distribution (primary)**: **OCI container `ghcr.io/openlimno/schism:5.11.0`** built from source via CI; multi-arch (linux/amd64, linux/arm64). User runs OpenLimno → spawns container → SCHISM executes inside.
5. **Distribution (secondary)**: documented source-build instructions in `docs/getting_started/install.md` for HPC users who can't use containers.
6. **No conda-forge in 1.0.** If SCHISM lands on conda-forge later, this ADR will be superseded.

## Alternatives considered

### A: Link SCHISM as a library (rejected)
SCHISM is Fortran, MPI-aware, complex build. Linkage forces our build chain to depend on a Fortran/MPI/HDF5 toolchain on every platform. Maintenance cost too high for 1.0.

### B: Track upstream master (rejected)
Schema/file-format drift between SCHISM versions is real. Tracking master means our regression suite can break weekly with no indication. LTS pin gives us a stable target.

### C: Custom text-template input writer (rejected)
Reproduces work `pyschism` already does, plus loses upstream bug fixes.

## Consequences

### Positive
- Clean separation: SCHISM team owns numerical correctness; OpenLimno owns ecological wrapping
- LTS pin gives a fixed target for benchmarks
- Container distribution avoids per-user Fortran/MPI build pain
- Multi-arch (amd64 + arm64) container supports Apple Silicon Macs

### Negative
- Cross-process IO has overhead (acceptable; SCHISM runs are minutes-to-hours, not interactive)
- LTS upgrade is a deliberate event (independent PR + full regression), not automatic

### Acknowledged trade-offs
- We do not exploit fast in-process coupling (e.g., shared memory). Acceptable for 1.0; reconsider if §13.1 self-built backend lands.

## Implementation notes

- `src/openlimno/hydro/schism.py` exposes `class SCHISMAdapter` (M3 deliverable)
- Subprocess spawn via `subprocess.Popen` with stdin/stdout/stderr piped, OR via `docker run` against the LTS container
- Timeout, signal handling, log roll
- Failure: package work_dir into a debug zip for issue submission
- Schema-driven config validation before spawning subprocess (don't run a 6-hour SCHISM job to discover a typo)

### Container Dockerfile sketch (M0 deliverable extension; PR target)

```dockerfile
FROM ubuntu:24.04 AS builder
RUN apt-get update && apt-get install -y \
    cmake gfortran libopenmpi-dev libhdf5-dev libnetcdf-dev libnetcdff-dev \
    git build-essential wget
WORKDIR /src
RUN git clone --depth 1 --branch v5.11.0 https://github.com/schism-dev/schism.git
WORKDIR /src/schism
RUN mkdir build && cd build && cmake .. && make -j

FROM ubuntu:24.04
RUN apt-get update && apt-get install -y \
    libopenmpi3 libhdf5-103 libnetcdf19 libnetcdff7 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /src/schism/build/bin/pschism_TVD-VL /usr/local/bin/schism
ENTRYPOINT ["/usr/local/bin/schism"]
```

(Exact commands subject to upstream build system. CI pushes `ghcr.io/openlimno/schism:5.11.0` for amd64+arm64.)

## References

- SCHISM: https://schism-dev.github.io/
- pyschism: https://github.com/schism-dev/pyschism
- SPEC v0.5 §6.1
