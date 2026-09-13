#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: bash dev/docker-down-wsl.sh [--dry-run]"
  echo "Stop/remove this project's Compose containers and networks."
  echo "Preserve volumes, images and Windows Ollama. No venv or Ollama connection required."
}

DRY_RUN=false
for arg in "$@"; do
  case "${arg}" in
    --dry-run) DRY_RUN=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[ERROR] Unsupported option: ${arg}" >&2; usage >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

# Only satisfy Compose interpolation. 'down' does not create containers or
# update extra_hosts, so shutdown must not depend on Windows/Ollama availability.
export OLLAMA_WINDOWS_IP="${OLLAMA_WINDOWS_IP:-127.0.0.1}"

# Include both supported configurations to also stop optional llama.cpp services.
# Keep the same project directory/name resolution as the up scripts.
# Do not remove orphans, volumes or images, or forward arbitrary down options.
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.llamacpp.yml)
# The password is only an interpolation placeholder during down/config, never
# persisted or used to start Neo4j. Preserve the graph volume like the DB volume.
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-shutdown-placeholder-only}"
if [[ "${DRY_RUN}" == true ]]; then
  "${COMPOSE[@]}" config --quiet
  echo "[DRY RUN] Working directory: ${PROJECT_DIR}"
  printf '[DRY RUN] '
  printf '%q ' "${COMPOSE[@]}" down --timeout 30
  printf '\n'
  exit 0
fi

"${COMPOSE[@]}" down --timeout 30
echo "[OK] Project containers/networks stopped and removed."
echo "[INFO] Volumes, images and Windows Ollama were preserved."
