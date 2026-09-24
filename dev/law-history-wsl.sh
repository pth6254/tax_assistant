#!/usr/bin/env bash
# Operate the opt-in archive worker without restarting the chat API.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source venv-wsl/bin/activate
export OLLAMA_WINDOWS_IP="$(ip -4 route show default | awk 'NR == 1 {print $3}')"
case "${1:-status}" in
  start) docker compose --profile history up -d --build --no-deps law-history-worker ;;
  status) docker compose --profile history ps -a law-history-worker
          docker compose --profile history run --rm --no-deps law-history-worker python scripts/collect_law_history.py status ;;
  logs) docker compose --profile history logs --tail 30 law-history-worker ;;
  stop) docker compose --profile history stop law-history-worker ;;
  *) echo 'Usage: bash dev/law-history-wsl.sh start|status|logs|stop' >&2; exit 2 ;;
esac
