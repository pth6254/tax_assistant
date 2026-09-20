"""Run the evaluation CLI from the repository root."""
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from evaluation.cli import entrypoint

    raise SystemExit(entrypoint())
