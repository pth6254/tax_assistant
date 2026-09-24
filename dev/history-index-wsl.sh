#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source venv-wsl/bin/activate
export OLLAMA_WINDOWS_IP="$(ip -4 route show default | awk 'NR == 1 {print $3}')"
case "${1:-status}" in
  build) docker compose --profile history-index build law-history-indexer ;;
  test) docker compose --profile history-index run --rm --no-deps law-history-indexer pytest -q ;;
  graph) docker compose --profile history-index run --rm --no-deps law-history-indexer python scripts/index_law_history.py graph ;;
  audit) docker compose --profile history-index run --rm --no-deps law-history-indexer python -m evaluation.history_index_audit ;;
  smoke) docker compose --profile history-index run --rm --no-deps law-history-indexer python -m evaluation.history_smoke ;;
  embed-version) docker compose --profile history-index run --rm --no-deps law-history-indexer python scripts/index_law_history.py embed --version-id "${2:?version id required}" ;;
  start) docker compose --profile history-index up -d --no-deps law-history-indexer ;;
  migrate) docker compose --profile history-index run --rm --no-deps law-history-indexer alembic upgrade head ;;
  status) docker compose --profile history-index ps -a law-history-indexer
          docker compose --profile history-index run --rm --no-deps law-history-indexer python scripts/index_law_history.py status ;;
  logs) docker compose --profile history-index logs --tail 15 law-history-indexer ;;
  stop) docker compose --profile history-index stop law-history-indexer ;;
  *) echo 'Usage: bash dev/history-index-wsl.sh build|migrate|start|status|logs|stop|test|graph|audit|smoke|embed-version ID' >&2; exit 2 ;;
esac
