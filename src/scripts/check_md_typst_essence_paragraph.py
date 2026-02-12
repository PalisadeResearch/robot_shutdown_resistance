#!/usr/bin/env python3
"""
Fail if the marked README and Typst lines diverge.

Spec:
- If a line containing MARKER exists in *both* files, require the matching lines
  (potentially multiple) to be identical (ignoring leading/trailing whitespace).
- Otherwise, succeed (no-op).
"""

from __future__ import annotations

from pathlib import Path

MARKER = "<match_md_typst-essence-paragraph>"


def _normalize_matching_line(line: str) -> str:
    if MARKER not in line:
        return line.strip()

    without_comment = line
    for comment_variant in (
        f"<!-- {MARKER} -->",
        f"<!--{MARKER}-->",
        f"<!-- {MARKER}-->",
        f"<!--{MARKER} -->",
    ):
        if comment_variant in without_comment:
            without_comment = without_comment.replace(comment_variant, "")
            break

    without_marker = without_comment.replace(MARKER, "")
    return without_marker.strip()


def _matching_lines(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [_normalize_matching_line(line) for line in lines if MARKER in line]


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    typst_path = repo_root / "paper-typst" / "main.typ"
    md_path = repo_root / "README.md"

    typst_lines = _matching_lines(typst_path)
    md_lines = _matching_lines(md_path)

    if not typst_lines or not md_lines:
        return 0

    if typst_lines == md_lines:
        return 0

    print(f"ERROR: Lines containing {MARKER} differ between files.")
    print(f"- {typst_path}:")
    for line in typst_lines:
        print(f"  {line}")
    print(f"- {md_path}:")
    for line in md_lines:
        print(f"  {line}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
