#!/usr/bin/env python3
"""
Web-based log viewer for JSONL log files.

Displays structured log entries with filtering, search, and formatted output.
Allows selecting from available log files via web UI.

Usage:
    python log_viewer.py                    # Start viewer (scans /var/log/pal9000)
    python log_viewer.py --log-dir /path    # Specify log directory
    python log_viewer.py --port 9000        # Custom port
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, redirect, request, send_from_directory

app = Flask(__name__)

# Default logs directory
DEFAULT_LOGS_DIR = Path("/var/log/pal9000")

# Global configuration
LOG_DIR: Path = DEFAULT_LOGS_DIR
TAGS_PATH: Path = DEFAULT_LOGS_DIR / "tags.json"
TAGS_DATA: dict[str, list[str]] = {}
# Per-group tags cache: group_name -> {filename: [tags]}
GROUP_TAGS_DATA: dict[str, dict[str, list[str]]] = {}

# S3 storage backend (None when using filesystem)
S3: Any | None = None


def parse_log_metadata(
    lines: Iterable[str],
    max_parse_lines: int = 20,
) -> dict[str, Any]:
    """Parse metadata (model, timestamp) from the first lines of a JSONL log.

    Args:
        lines: Iterable of raw text lines.
        max_parse_lines: Number of leading lines to parse for metadata.

    Returns:
        Dict with model, first_timestamp, entry_count.
    """
    model = None
    first_timestamp = None
    entry_count = 0

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        entry_count += 1

        if i < max_parse_lines:
            try:
                entry = json.loads(line)
                if first_timestamp is None and "ts" in entry:
                    first_timestamp = entry["ts"]

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
        "model": model or "unknown",
        "first_timestamp": first_timestamp,
        "entry_count": entry_count,
    }


def extract_log_metadata(filepath: Path) -> dict[str, Any]:
    """Extract metadata from a log file by scanning all lines."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return parse_log_metadata(f)
    except Exception as exc:
        print(f"Warning: failed to extract metadata from {filepath}: {exc}")
        return {"model": "unknown", "first_timestamp": None, "entry_count": 0}


def _is_debug_log(filepath: Path) -> bool:
    """Check if file is a debug log."""
    return filepath.name.endswith("_debug.jsonl")


def scan_log_files(
    directory: Path, include_debug: bool = False
) -> list[dict[str, Any]]:
    """
    Scan directory for JSONL log files and return metadata.

    Args:
        directory: Directory to scan
        include_debug: If True, include *_debug.jsonl files

    Returns:
        List of file metadata dicts with name, size, mtime, entry_count, model
    """
    if not directory.exists():
        return []

    files = []
    for filepath in sorted(directory.glob("*.jsonl"), reverse=True):
        if not include_debug and _is_debug_log(filepath):
            continue
        try:
            stat = filepath.stat()
            metadata = extract_log_metadata(filepath)

            files.append(
                {
                    "name": filepath.name,
                    "path": str(filepath),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "entry_count": metadata["entry_count"],
                    "model": metadata["model"],
                    "first_timestamp": metadata["first_timestamp"],
                }
            )
        except Exception as exc:
            print(f"Warning: failed to scan {filepath}: {exc}")
            continue

    return files


def scan_groups(directory: Path, include_debug: bool = False) -> list[dict[str, Any]]:
    """
    Recursively scan directory for group subdirectories containing .jsonl files.

    Group names use the relative path from *directory*, e.g. "default/default1"
    or "live/different_behaviour/distract_person".

    Args:
        directory: Base log directory to scan
        include_debug: If True, include *_debug.jsonl files in count

    Returns:
        List of group metadata dicts with name and file_count
    """
    if not directory.exists():
        return []

    groups = []
    for subdir in sorted(directory.rglob("*")):
        if not subdir.is_dir() or subdir.name.endswith("_images"):
            continue
        jsonl_files = [
            f for f in subdir.glob("*.jsonl") if include_debug or not _is_debug_log(f)
        ]
        if jsonl_files:
            groups.append(
                {
                    "name": str(subdir.relative_to(directory)),
                    "file_count": len(jsonl_files),
                }
            )

    return groups


def get_tags_path_for_group(group: str | None) -> Path:
    """Get the tags.json path for a specific group or root."""
    if group:
        return LOG_DIR / group / "tags.json"
    return LOG_DIR / "tags.json"


def load_tags_for_group(group: str | None = None) -> dict[str, list[str]]:
    """Load tag mapping from disk for a specific group (or root)."""
    tags_path = get_tags_path_for_group(group)
    if not tags_path.exists():
        return {}

    try:
        with open(tags_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {
                    name: [str(tag) for tag in tags if str(tag).strip()]
                    for name, tags in data.items()
                    if isinstance(tags, list)
                }
    except Exception as exc:
        print(f"Warning: failed to load tags from {tags_path}: {exc}")

    return {}


def save_tags_for_group(tags: dict[str, list[str]], group: str | None = None) -> None:
    """Persist tag mapping to disk for a specific group (or root)."""
    tags_path = get_tags_path_for_group(group)
    try:
        tags_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tags_path, "w", encoding="utf-8") as f:
            json.dump(tags, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"Warning: failed to save tags to {tags_path}: {exc}")


def parse_jsonl_lines(
    lines: Iterable[str],
    since_line: int | None = None,
) -> list[dict[str, Any]]:
    """Parse JSONL lines into log entry dicts.

    Args:
        lines: Iterable of raw text lines (enumerated from 1 internally).
        since_line: If provided, only return entries after this line number.

    Returns:
        List of parsed log entry dicts.
    """
    entries: list[dict[str, Any]] = []
    for line_num, raw_line in enumerate(lines, 1):
        if since_line is not None and line_num <= since_line:
            continue
        line = raw_line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            entry["_line_number"] = line_num
            entries.append(entry)
        except json.JSONDecodeError:
            entries.append(
                {
                    "_line_number": line_num,
                    "_parse_error": True,
                    "raw_line": line[:200],
                }
            )
    return entries


def parse_jsonl_file(
    filepath: Path, since_line: int | None = None
) -> list[dict[str, Any]]:
    """Parse JSONL file and return list of log entries."""
    if not filepath.exists():
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return parse_jsonl_lines(f, since_line=since_line)
    except Exception as exc:
        print(f"Warning: failed to parse {filepath}: {exc}")
        return []


def search_logs(
    query: str, level: str | None = None, event: str | None = None
) -> list[dict[str, Any]]:
    """
    Search across all JSONL logs in LOG_DIR.

    # TODO: search does not cover grouped files — only root-level .jsonl.

    Args:
        query: Full-text query (case-insensitive)
        level: Optional level filter
        event: Optional event filter

    Returns:
        List of matching entries with file metadata.
    """
    if not query:
        return []

    results: list[dict[str, Any]] = []
    search_text = query.lower()

    for filepath in sorted(LOG_DIR.glob("*.jsonl"), reverse=True):
        if _is_debug_log(filepath):
            continue
        entries = parse_jsonl_file(filepath)
        for entry in entries:
            if entry.get("_parse_error"):
                raw_line = entry.get("raw_line", "")
                if search_text in raw_line.lower():
                    entry_copy = dict(entry)
                    entry_copy["_file"] = filepath.name
                    results.append(entry_copy)
                continue

            if level and entry.get("level") != level:
                continue

            if event and entry.get("event") != event:
                continue

            searchable_parts = [
                entry.get("message", ""),
                entry.get("tool", ""),
                entry.get("event", ""),
                json.dumps(entry.get("args", {}), ensure_ascii=False),
                str(entry.get("result", "")),
            ]
            searchable = " ".join(searchable_parts).lower()
            if search_text in searchable:
                entry_copy = dict(entry)
                entry_copy["_file"] = filepath.name
                results.append(entry_copy)

    return results


_INDEX_HTML = Path(__file__).with_name("index.html")


@app.route("/")
def index() -> str:
    """Main page — served from index.html next to this module."""
    return _INDEX_HTML.read_text(encoding="utf-8")


@app.route("/api/groups")
def api_groups() -> Any:
    """Return list of available log groups (subdirectories)."""
    include_debug = request.args.get("include_debug", "").lower() == "true"
    if S3:
        groups = S3.list_groups(include_debug=include_debug)
    else:
        groups = scan_groups(LOG_DIR, include_debug=include_debug)
    return jsonify({"groups": groups})


@app.route("/api/files")
def api_files() -> Any:
    """Return list of available JSONL log files."""
    group = request.args.get("group")
    include_debug = request.args.get("include_debug", "").lower() == "true"
    if S3:
        files = S3.list_files(group=group, include_debug=include_debug)
        return jsonify(files)
    if group:
        target_dir = LOG_DIR / group
        if not target_dir.exists():
            return jsonify({"error": "group not found"}), 404
        files = scan_log_files(target_dir, include_debug=include_debug)
        for f in files:
            f["group"] = group
    else:
        # Aggregate files from all groups
        files = []
        for g in scan_groups(LOG_DIR, include_debug=include_debug):
            group_dir = LOG_DIR / g["name"]
            for f in scan_log_files(group_dir, include_debug=include_debug):
                f["group"] = g["name"]
                files.append(f)
        files.sort(key=lambda f: f["name"], reverse=True)
    return jsonify(files)


@app.route("/api/logs")
def api_logs() -> Any:
    """Return log entries from specified file."""
    filename = request.args.get("file")
    group = request.args.get("group")
    if not filename:
        return jsonify({"error": "file parameter required"}), 400

    since_line = request.args.get("since_line", type=int)

    if S3:
        if not S3.file_exists(filename, group=group):
            return jsonify({"error": "file not found"}), 404
        entries = S3.read_log_entries(filename, group=group, since_line=since_line)
        return jsonify({"entries": entries, "file": filename})

    if group:
        filepath = LOG_DIR / group / filename
    else:
        filepath = LOG_DIR / filename
    if not filepath.exists():
        return jsonify({"error": "file not found"}), 404

    if since_line is not None:
        entries = parse_jsonl_file(filepath, since_line=since_line)
    else:
        entries = parse_jsonl_file(filepath)

    return jsonify({"entries": entries, "file": filename})


@app.route("/api/search")
def api_search() -> Any:
    """Search across all log files."""
    query = request.args.get("q", "")
    if not query:
        return jsonify({"error": "q parameter required"}), 400

    level = request.args.get("level")
    event = request.args.get("event")

    if S3:
        results = S3.search_logs(query, level=level or None, event=event or None)
    else:
        results = search_logs(query, level=level or None, event=event or None)
    return jsonify({"results": results, "count": len(results)})


@app.route("/api/tags", methods=["GET", "POST"])
def api_tags() -> Any:
    """Retrieve or update tags for log files."""
    global TAGS_DATA, GROUP_TAGS_DATA

    if request.method == "GET":
        group = request.args.get("group")
        if S3:
            if group:
                tags = S3.load_tags(group=group)
            else:
                tags = S3.load_all_tags()
            result: dict[str, Any] = {"tags": tags}
            if group:
                result["group"] = group
            return jsonify(result)
        if group:
            group_tags = load_tags_for_group(group)
            return jsonify({"tags": group_tags, "group": group})
        # Aggregate tags from all groups
        all_tags: dict[str, list[str]] = {}
        all_tags.update(load_tags_for_group())  # root-level tags
        for g in scan_groups(LOG_DIR):
            all_tags.update(load_tags_for_group(g["name"]))
        return jsonify({"tags": all_tags})

    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON body"}), 400

    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid payload"}), 400

    filename = payload.get("file")
    tags = payload.get("tags")
    group = payload.get("group") or request.args.get("group")

    if not filename or not isinstance(filename, str):
        return jsonify({"error": "file must be provided"}), 400

    if not isinstance(tags, list):
        return jsonify({"error": "tags must be a list"}), 400

    cleaned_tags = []
    for tag in tags:
        if isinstance(tag, str):
            tag_clean = tag.strip()
            if tag_clean:
                cleaned_tags.append(tag_clean)

    if S3:
        if not S3.file_exists(filename, group=group):
            return jsonify({"error": "file not found"}), 404
        all_tags = S3.load_tags(group=group)
        all_tags[filename] = cleaned_tags
        S3.save_tags(all_tags, group=group)
        resp: dict[str, Any] = {"file": filename, "tags": cleaned_tags, "success": True}
        if group:
            resp["group"] = group
        return jsonify(resp)

    if group:
        filepath = LOG_DIR / group / filename
    else:
        filepath = LOG_DIR / filename
    if not filepath.exists():
        return jsonify({"error": "file not found"}), 404

    if group:
        if group not in GROUP_TAGS_DATA:
            GROUP_TAGS_DATA[group] = load_tags_for_group(group)
        GROUP_TAGS_DATA[group][filename] = cleaned_tags
        save_tags_for_group(GROUP_TAGS_DATA[group], group)
        return jsonify(
            {"file": filename, "tags": cleaned_tags, "group": group, "success": True}
        )
    else:
        TAGS_DATA[filename] = cleaned_tags
        save_tags_for_group(TAGS_DATA)
        return jsonify({"file": filename, "tags": cleaned_tags, "success": True})


@app.route("/images/<path:image_path>")
def serve_image(image_path: str) -> Any:
    """Serve images referenced in log entries."""
    group = request.args.get("group")

    if S3:
        url = S3.get_image_url(image_path, group=group)
        if url:
            return redirect(url)
        return jsonify({"error": "image not found"}), 404

    resolved_log_dir = LOG_DIR.resolve()

    # Extract the *_images/filename tail — always the last two segments
    parts = image_path.split("/")
    tail = "/".join(parts[-2:]) if len(parts) >= 2 else image_path

    # If group is known, resolve directly inside LOG_DIR/group/
    if group:
        candidate = (LOG_DIR / group / tail).resolve()
        if candidate.is_relative_to(resolved_log_dir) and candidate.is_file():
            return send_from_directory(candidate.parent, candidate.name)

    # Fallback: strip common prefixes and try direct resolution
    log_dir_str = str(LOG_DIR).lstrip("/")
    for prefix in ("log_images/", "logs/", f"{log_dir_str}/"):
        if image_path.startswith(prefix):
            image_path = image_path[len(prefix) :]
            break

    possible_paths = [
        (LOG_DIR / image_path).resolve(),
        Path("/" + image_path).resolve(),
    ]
    for path in possible_paths:
        if path.is_relative_to(resolved_log_dir) and path.is_file():
            return send_from_directory(path.parent, path.name)

    return jsonify({"error": "image not found"}), 404


def _init_s3_storage() -> None:
    """Initialise the global S3 storage backend from environment variables."""
    global S3

    from s3_storage import S3LogStorage

    bucket = os.environ.get("S3_BUCKET")
    if not bucket:
        raise ValueError("S3_BUCKET env var is required when USE_S3=true")

    S3 = S3LogStorage(
        bucket=bucket,
        prefix=os.environ.get("S3_PREFIX", ""),
        endpoint_url=os.environ.get("S3_ENDPOINT_URL"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        region_name=os.environ.get("AWS_REGION", "auto"),
    )
    print(f"Using S3 storage: {bucket}/{S3.prefix}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Web-based log viewer for JSONL files")
    parser.add_argument(
        "--log-dir",
        type=str,
        default=None,
        help=f"Directory to scan for log files (default: {DEFAULT_LOGS_DIR})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "5790")),
        help="HTTP port (default: 5790 or PORT env var)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Bind address (default: 0.0.0.0)",
    )

    args = parser.parse_args()

    # S3 mode: read everything from Tigris / S3-compatible storage
    if os.environ.get("USE_S3", "").lower() == "true":
        _init_s3_storage()
    else:
        global LOG_DIR, TAGS_PATH, TAGS_DATA

        if args.log_dir:
            LOG_DIR = Path(args.log_dir).resolve()
        else:
            LOG_DIR = DEFAULT_LOGS_DIR

        TAGS_PATH = LOG_DIR / "tags.json"

        if not LOG_DIR.exists():
            print(f"Warning: Log directory does not exist: {LOG_DIR}")
            print("Creating directory...")
            LOG_DIR.mkdir(parents=True, exist_ok=True)

        TAGS_DATA = load_tags_for_group()
        print(f"Using filesystem storage: {LOG_DIR}")

    print(f"Server: http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
