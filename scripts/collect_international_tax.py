"""Collect a bounded US/JP/CN official-source pilot outside production databases."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.international_sources import SOURCES, audit, collect


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory under evaluation/sources/")
    parser.add_argument("--resume", action="store_true", help="Retry incomplete sources and verify saved hashes")
    parser.add_argument("--audit", action="store_true", help="Read-only integrity audit of an existing collection")
    args = parser.parse_args()
    try:
        root = args.output.resolve()
        allowed = (Path(__file__).resolve().parent.parent / "evaluation" / "sources").resolve()
        if not root.is_relative_to(allowed) or root == allowed:
            parser.error("output must be a child of evaluation/sources/")
        if args.audit:
            print(json.dumps(audit(root), ensure_ascii=False))
            return 0
        result = collect(root, resume=args.resume)
        counts = {"collected": sum(item["status"] == "collected" for item in result["records"].values()), "failed": sum(item["status"] == "failed" for item in result["records"].values()), "expected": len(SOURCES)}
        print(json.dumps(counts, ensure_ascii=False))
        return 0 if counts["collected"] == len(SOURCES) else 2
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
