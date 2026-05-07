# SCHISM v5.11.0 LTS — OCI container for OpenLimno
#
# Per ADR-0002: SCHISM is the sole 2D backend for OpenLimno 1.0 and is
# distributed as an OCI image (conda-forge does not package SCHISM as of
# 2026-Q2). The image is multi-arch (linux/amd64 + linux/arm64).
#
# Build:
#   docker buildx build \
#       --platform linux/amd64,linux/arm64 \
#       -t ghcr.io/openlimno/schism:5.11.0 \
#       -t ghcr.io/openlimno/schism:latest \
#       containers/schism/
#
# Run (typical OpenLimno invocation):
#   docker run --rm -v $PWD/work:/work -w /work \
#       ghcr.io/openlimno/schism:5.11.0
#
# Verify (after build):
#   docker run --rm ghcr.io/openlimno/schism:5.11.0 --version || true
#   # SCHISM has no --version flag; the entrypoint exits non-zero with usage,
#   # but the image is healthy if it gets that far.

# ---------------------------------------------------------------------------
# Stage 1: build SCHISM from a pinned tag
# ---------------------------------------------------------------------------
FROM ubuntu:24.04 AS builder

ARG SCHISM_VERSION=v5.11.0
ARG MAKEFLAGS=-j4

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        gfortran \
        git \
        ca-certificates \
        libopenmpi-dev \
        openmpi-bin \
        libhdf5-dev \
        libhdf5-openmpi-dev \
        libnetcdf-dev \
        libnetcdff-dev \
        zlib1g-dev \
        wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth 1 --branch ${SCHISM_VERSION} https://github.com/schism-dev/schism.git

# SCHISM CMake build. Flags chosen to match the upstream "default OpenMPI"
# recipe; they are documented at
# https://schism-dev.github.io/schism/master/getting-started/installation.html
WORKDIR /src/schism/build
RUN cmake .. \
        -DCMAKE_Fortran_COMPILER=mpif90 \
        -DCMAKE_C_COMPILER=mpicc \
        -DCMAKE_CXX_COMPILER=mpicxx \
        -DCMAKE_BUILD_TYPE=Release \
        -DUSE_NETCDF=ON \
        -DNetCDF_C_DIR=/usr \
        -DNetCDF_FORTRAN_DIR=/usr \
    && make ${MAKEFLAGS}

# ---------------------------------------------------------------------------
# Stage 2: runtime image (only shared libraries, no compiler)
# ---------------------------------------------------------------------------
FROM ubuntu:24.04

ARG SCHISM_VERSION=v5.11.0
LABEL org.opencontainers.image.title="SCHISM ${SCHISM_VERSION} (OpenLimno LTS pin)" \
      org.opencontainers.image.source="https://github.com/openlimno/openlimno" \
      org.opencontainers.image.licenses="Apache-2.0 (wrapper) / SCHISM-license (binary)" \
      org.opencontainers.image.description="SCHISM hydrodynamic solver, ADR-0002 LTS pin" \
      org.opencontainers.image.version="${SCHISM_VERSION}"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        openmpi-bin \
        libopenmpi3 \
        libhdf5-103-1 \
        libhdf5-openmpi-103 \
        libnetcdf19 \
        libnetcdff7 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy the SCHISM binary; the upstream build produces several variants
# (pschism_TVD-VL is the most-used semi-implicit baroclinic build).
COPY --from=builder /src/schism/build/bin/pschism_* /usr/local/bin/

# Friendly default name for the OpenLimno adapter
RUN ln -sf /usr/local/bin/pschism_TVD-VL /usr/local/bin/schism

# Run SCHISM under an unprivileged user (security hardening).
RUN useradd --create-home --shell /bin/bash schism
USER schism
WORKDIR /work

ENTRYPOINT ["/usr/local/bin/schism"]
