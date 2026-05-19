# PHABSIM Fortran-77 container — R-PHABSIM-REAL track
#
# Status: PLACEHOLDER (2026-05-20). The actual USFWS PHABSIM source
# tarball is not yet acquired/pinned (license verification pending,
# see README.md "USFWS PHABSIM source — license + acquisition").
# This Dockerfile documents the build strategy so the next person
# picking up the track has a starting point. It will NOT build a
# working PHABSIM binary as-is; the `ADD` line and the `make` step
# are guarded so an accidental `docker build .` produces a clear
# error rather than a silently broken image.
#
# Mirrors ADR-0002's SCHISM containerisation pattern:
#   1. Pin one build of the Fortran binary
#   2. Distribute via OCI registry (target: ghcr.io/openlimno/phabsim:1986)
#   3. OpenLimno shells out via subprocess; the container is opaque
#      to the Python side.

FROM debian:12-slim AS builder

# Build deps for Fortran 77 + NCAR-era Makefiles.
# We pin Debian 12 because:
#   - gfortran 12.x handles legacy F77 dialect cleanly (auto -std=legacy)
#   - libgfortran5 is stable for ~5 years (matches our LTS posture)
#   - apt history is reproducible against snapshot.debian.org
RUN apt-get update && apt-get install -y --no-install-recommends \
        gfortran \
        gfortran-12 \
        make \
        ca-certificates \
        unzip \
        wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# PLACEHOLDER: replace with the verified USFWS PHABSIM source archive.
# Tarball URL must be checksummed (SHA-256 pin) and license-verified
# (see README.md). The placeholder file below makes `docker build`
# fail with a clear message rather than producing a phantom image.
RUN echo "ERROR: USFWS PHABSIM source tarball not pinned." >&2 \
    && echo "       Acquire the archive (license-verified) and replace this layer with:" >&2 \
    && echo "         ADD --checksum=sha256:<HASH> https://<URL>/phabsim.tar.gz /build/" >&2 \
    && echo "       See benchmarks/phabsim_real/README.md § 'USFWS PHABSIM source'." >&2 \
    && exit 1

# When the source is pinned, the build proceeds with the steps below.
# The exact commands depend on the source archive layout; the comment
# block records the canonical PHABSIM build invocation.
#
# RUN tar xf phabsim.tar.gz
# WORKDIR /build/IFG4
# RUN make
# WORKDIR /build/HABTAE
# RUN make
# WORKDIR /build/HABEF
# RUN make
#
# The three binaries IFG4, HABTAE, HABEF together drive the
# hydraulics + habitat pipeline that test_real_run_matches.py will
# invoke via run_phabsim.sh.

# ----------------------------------------------------------------------
# Final image — minimal runtime
# ----------------------------------------------------------------------
FROM debian:12-slim AS runtime

# Runtime deps only (no compiler in the final image).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgfortran5 \
    && rm -rf /var/lib/apt/lists/*

# When the builder produces real binaries, this COPY puts them on PATH.
# COPY --from=builder /build/IFG4/ifg4 /usr/local/bin/
# COPY --from=builder /build/HABTAE/habtae /usr/local/bin/
# COPY --from=builder /build/HABEF/habef /usr/local/bin/

WORKDIR /work

# Default entrypoint forwards to run_phabsim.sh inside /work. The
# orchestration script (mounted from the host benchmarks dir) decides
# which module to invoke.
ENTRYPOINT ["/work/run_phabsim.sh"]
