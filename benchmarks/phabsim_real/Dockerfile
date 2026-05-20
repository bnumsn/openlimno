# PHABSIM Fortran-77 container -- R-PHABSIM-REAL track
#
# This is a substantive WIP, not a working image yet. The USFWS source
# archive URL and SHA-256 must be license-verified before the guarded
# ADD/RUN block is enabled. Target image: ghcr.io/openlimno/phabsim:1986.

FROM debian:12-slim AS builder

ARG PHABSIM_SRC_URL=""
ARG PHABSIM_SRC_SHA256=""

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        file \
        gfortran \
        make \
        patch \
        unzip \
        wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN test -n "$PHABSIM_SRC_URL" -a -n "$PHABSIM_SRC_SHA256" || ( \
        echo "ERROR: set PHABSIM_SRC_URL and PHABSIM_SRC_SHA256 after source/license verification." >&2; \
        echo "Example: docker build --build-arg PHABSIM_SRC_URL=... --build-arg PHABSIM_SRC_SHA256=... ." >&2; \
        exit 1 )

RUN wget -O phabsim.src "$PHABSIM_SRC_URL" \
    && echo "$PHABSIM_SRC_SHA256  phabsim.src" | sha256sum -c - \
    && mkdir src \
    && case "$(file -b phabsim.src)" in \
         *Zip*) unzip -q phabsim.src -d src ;; \
         *gzip*) tar -xzf phabsim.src -C src --strip-components=1 ;; \
         *) echo "unsupported PHABSIM archive type" >&2; exit 2 ;; \
       esac

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN set -eux; \
    cd /build/src; \
    export FC="${FC:-gfortran}"; \
    export FFLAGS="${FFLAGS:--O2 -std=legacy -fallow-argument-mismatch -fno-range-check}"; \
    for module in IFG4 HABTAE HABEF; do \
      dir="$(find . -type d -iname "$module" | head -n 1)"; \
      test -n "$dir"; \
      pushd "$dir"; \
      if [[ -f Makefile || -f makefile ]]; then \
        make FC="$FC" FFLAGS="$FFLAGS"; \
      else \
        "$FC" $FFLAGS -o "${module,,}" ./*.f ./*.for ./*.F 2>&1 | tee build.log; \
      fi; \
      install -m 0755 "$(find . -maxdepth 1 -type f -perm -111 | head -n 1)" "/usr/local/bin/${module,,}"; \
      popd; \
    done

FROM debian:12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgfortran5 \
        python3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/bin/ifg4 /usr/local/bin/ifg4
COPY --from=builder /usr/local/bin/habtae /usr/local/bin/habtae
COPY --from=builder /usr/local/bin/habef /usr/local/bin/habef

WORKDIR /work
ENTRYPOINT ["/work/run_phabsim.sh"]
