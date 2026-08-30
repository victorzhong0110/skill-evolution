#!/usr/bin/env python3
"""Walk a directory and print the code-stats report format."""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".skill-evolution"}


def ext_of(path: Path) -> str:
    suffix = path.suffix
    return suffix if suffix else "(no ext)"


def iter_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            out.append(Path(dirpath) / name)
    return out


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    files = [p for p in iter_files(root) if p.is_file()]
    by_ext: dict[str, list[Path]] = defaultdict(list)
    lines_by_file: dict[Path, int] = {}
    total_size = 0
    total_lines = 0

    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n_lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
        lines_by_file[path] = n_lines
        by_ext[ext_of(path)].append(path)
        total_size += path.stat().st_size
        total_lines += n_lines

    ext_rows = sorted(
        (
            (ext, len(paths), sum(lines_by_file[p] for p in paths))
            for ext, paths in by_ext.items()
        ),
        key=lambda row: (-row[2], row[0]),
    )

    print("# Code Statistics")
    print()
    print("## Summary")
    print(f"- Total Files: {len(files)}")
    print(f"- Total Lines: {total_lines}")
    print(f"- Total Size: {total_size} bytes")
    print()
    print("## Files by Extension")
    print("| Extension | Files | Lines |")
    print("|-----------|-------|-------|")
    for ext, n_files, n_lines in ext_rows:
        print(f"| {ext} | {n_files} | {n_lines} |")
    print()
    print("## Top 5 File Extensions by Line Count")
    for i, (ext, _, n_lines) in enumerate(ext_rows[:5], start=1):
        print(f"{i}. {ext} — {n_lines} lines")
    print()
    print("## Largest Files (top 5)")
    largest = sorted(lines_by_file.items(), key=lambda item: (-item[1], str(item[0])))[:5]
    for i, (path, n_lines) in enumerate(largest, start=1):
        print(f"{i}. {path.name} ({n_lines} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
