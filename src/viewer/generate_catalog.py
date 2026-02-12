#!/usr/bin/env python3
"""Generate _catalog.json with pre-computed metadata for all log files.

Scans a local logs directory, extracts model/timestamp from the first
20 lines of each JSONL file, counts total lines, and writes
the result as a flat JSON list to ``<logs_dir>/_catalog.json``.

Stdlib-only — no Flask, boto3, or other third-party dependencies.

Usage:
    python generate_catalog.py logs
    python generate_catalog.py /path/to/logs
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_MAX_PARSE_LINES = 20


def _extract_metadata(filepath: Path) -> dict:
    """Extract model, first_timestamp, entry_count from a JSONL file.

    Reads the first ``_MAX_PARSE_LINES`` lines for model/timestamp,
    then counts remaining lines cheaply.
    """
    model: str | None = None
    first_ts: str | None = None
    count = 0

    with open(filepath, encoding="utf-8") as f:
        for i, raw in enumerate(f):
            line = raw.strip()
            if not line:
                continue
            count += 1

            if i >= _MAX_PARSE_LINES:
                continue

            try:
                entry = json.loads(line)
                if first_ts is None and "ts" in entry:
                    first_ts = entry["ts"]
                msg = entry.get("message", "")
                if model is None:
                    if "Starting controller:" in msg:
                        match = re.search(r"model=(\S+)", msg)
                        if match:
                            model = match.group(1)
                    elif "Starting LLM controller with model:" in msg:
                        match = re.search(r"model:\s*(\S+)", msg)
                        if match:
                            model = match.group(1)
                    elif "LiteLLM completion()" in msg:
                        match = re.search(r"model=\s*([^;\s]+)", msg)
                        if match:
                            model = match.group(1)
            except json.JSONDecodeError:
                pass

    return {
        "entry_count": count,
        "model": model or "unknown",
        "first_timestamp": first_ts,
    }


def generate_catalog(logs_dir: Path) -> list[dict]:
    """Build a catalog list for all JSONL files under *logs_dir*."""
    catalog: list[dict] = []

    for filepath in sorted(logs_dir.rglob("*.jsonl")):
        rel = filepath.relative_to(logs_dir)
        parts = rel.parts
        if len(parts) < 2:
            # File at root level — skip (no group)
            continue

        group = "/".join(parts[:-1])
        meta = _extract_metadata(filepath)
        stat = filepath.stat()

        catalog.append(
            {
                "name": filepath.name,
                "group": group,
                "size": stat.st_size,
                "entry_count": meta["entry_count"],
                "model": meta["model"],
                "first_timestamp": meta["first_timestamp"],
            }
        )

    return catalog


def main() -> None:
    logs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("logs")
    if not logs_dir.is_dir():
        print(f"Error: {logs_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    catalog = generate_catalog(logs_dir)

    out = logs_dir / "_catalog.json"
    out.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(catalog)} entries to {out}")


if __name__ == "__main__":
    main()
