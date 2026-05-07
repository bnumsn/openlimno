#!/usr/bin/env bash
# Build + smoke-test the SCHISM v5.11.0 OCI container locally.
#
# Usage:
#   bash containers/schism/build.sh            # local single-arch build
#   bash containers/schism/build.sh --multi    # multi-arch (needs buildx)
#   bash containers/schism/build.sh --push     # push to ghcr.io (needs login)
#
# Prerequisites:
#   docker buildx ls    # confirm buildx is enabled
#   echo $GHCR_TOKEN | docker login ghcr.io -u <user> --password-stdin
set -euo pipefail

REPO="ghcr.io/openlimno/schism"
TAG="5.11.0"
HERE="$(cd "$(dirname "$0")" && pwd)"

PLATFORMS="linux/amd64"
PUSH=""
LOAD="--load"
case "${1:-}" in
  --multi) PLATFORMS="linux/amd64,linux/arm64"; LOAD="" ;;
  --push)  PLATFORMS="linux/amd64,linux/arm64"; LOAD=""; PUSH="--push" ;;
esac

echo "Building $REPO:$TAG for $PLATFORMS ..."
docker buildx build \
    --platform "$PLATFORMS" \
    -t "$REPO:$TAG" \
    -t "$REPO:latest" \
    $LOAD $PUSH \
    "$HERE"

if [[ -z "$PUSH" && "$LOAD" == "--load" ]]; then
    echo
    echo "Smoke test: container starts (entrypoint will print SCHISM usage and exit non-zero)..."
    docker run --rm "$REPO:$TAG" || true
    echo
    echo "Image $REPO:$TAG built locally. To push:"
    echo "    bash containers/schism/build.sh --push"
fi
