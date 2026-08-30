#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VENV_ACTIVATE="${PROJECT_DIR}/venv-wsl/bin/activate"

if [[ ! -f "${VENV_ACTIVATE}" ]]; then
  echo "[ERROR] WSL virtual environment not found: ${VENV_ACTIVATE}" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${VENV_ACTIVATE}"
cd "${PROJECT_DIR}"

export OLLAMA_WINDOWS_IP="$(ip -4 route show default | awk 'NR == 1 { print $3 }')"
if [[ -z "${OLLAMA_WINDOWS_IP}" ]]; then
  echo "[ERROR] Could not detect the Windows host IP." >&2
  exit 1
fi

if ! docker run --rm --gpus all --entrypoint nvidia-smi \
  ghcr.io/ggml-org/llama.cpp:server-cuda >/dev/null; then
  echo "[ERROR] Docker cannot access the NVIDIA GPU." >&2
  exit 1
fi

docker compose -f docker-compose.yml -f docker-compose.llamacpp.yml up -d --build "$@"

echo
echo "[OK] llama.cpp Docker Compose stack started"
docker compose -f docker-compose.yml -f docker-compose.llamacpp.yml ps
