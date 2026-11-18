#!/usr/bin/env bash
# Build and (re)start the container on the NAS over SSH. No registry needed:
# the Docker CLI streams this folder to the NAS's Docker daemon, which builds
# the image natively (so ARM vs x86 NAS doesn't matter).
#
# Config: copy .deploy.env.example to .deploy.env and set NAS_SSH.
set -euo pipefail
cd "$(dirname "$0")/.."

[[ -f .deploy.env ]] && source .deploy.env
: "${NAS_SSH:?Set NAS_SSH (e.g. NAS_SSH=brik@nas.local) in .deploy.env}"

export DOCKER_HOST="ssh://${NAS_SSH}"

echo "==> Building and starting on ${NAS_SSH}"
docker compose -p flipping up -d --build --remove-orphans

echo "==> Cleaning up dangling images"
docker image prune -f >/dev/null

echo "==> Status"
docker compose -p flipping ps
echo
echo "Logs: DOCKER_HOST=ssh://${NAS_SSH} docker compose -p flipping logs -f"
