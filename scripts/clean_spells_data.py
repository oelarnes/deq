"""Prune stale 17Lands JSON files from the spells data cache.

Each nightly deq run fetches data for a slightly different (start_date, end_date)
window; old files accumulate indefinitely. This script keeps only the most
recent N date-range variants per (set_code, format, cohort, color) key and
deletes the rest.

Only ratings/ files are cleaned. deck_color/ files are preserved because the
site does a linear date search across variants to determine sample size.

Usage:
    pdm run python scripts/clean_spells_data.py          # dry-run (default)
    pdm run python scripts/clean_spells_data.py --execute
"""

from __future__ import annotations

import argparse
import os
import re
from collections import defaultdict
from pathlib import Path

SPELLS_DATA_HOME = Path(
    os.environ.get("SPELLS_DATA_HOME", Path.home() / ".local/share/spells")
)

# Filename pattern: {format}_{cohort}_{color}_{start}_{end}.json
# e.g. PremierDraft_all_WU_2024-08-13_2024-09-24.json
FNAME_RE = re.compile(
    r"^(?P<fmt>.+)_(?P<cohort>all|top)_(?P<color>[A-Z+\-]+)_"
    r"(?P<start>\d{4}-\d{2}-\d{2})_(?P<end>\d{4}-\d{2}-\d{2})\.json$"
)

KEEP_RECENT = 1  # keep only the single latest date range per key


def gather_deletions(data_subdir: str, fname_re: re.Pattern) -> list[Path]:
    """Scan a ratings/ or deck_color/ subdirectory; return list of files to delete."""
    base = SPELLS_DATA_HOME / data_subdir
    if not base.exists():
        return []

    to_delete: list[Path] = []

    for set_dir in sorted(base.iterdir()):
        if not set_dir.is_dir():
            continue

        # Group files by key (everything except the date range)
        by_key: dict[str, list[tuple[str, str, Path]]] = defaultdict(list)
        for f in set_dir.iterdir():
            m = fname_re.match(f.name)
            if not m:
                continue
            groups = m.groupdict()
            color = groups.get("color", "")
            key = f"{groups['fmt']}_{groups['cohort']}_{color}"
            by_key[key].append((groups["start"], groups["end"], f))

        for key, variants in by_key.items():
            # Sort by (end_date desc, start_date desc) — newest window first
            variants.sort(key=lambda t: (t[1], t[0]), reverse=True)
            keep = variants[:KEEP_RECENT]
            delete = variants[KEEP_RECENT:]
            for start, end, path in delete:
                to_delete.append(path)

    return to_delete


def main(execute: bool) -> None:
    deletions = gather_deletions("ratings", FNAME_RE)

    if not deletions:
        print("Nothing to clean.")
        return

    total_bytes = sum(f.stat().st_size for f in deletions)
    print(f"{'[DRY RUN] ' if not execute else ''}Found {len(deletions)} files to delete "
          f"({total_bytes / 1_000_000:.1f} MB):\n")

    for path in sorted(deletions):
        rel = path.relative_to(SPELLS_DATA_HOME)
        print(f"  {'DELETE' if execute else 'would delete'}  {rel}")
        if execute:
            path.unlink()

    if execute:
        print(f"\nDeleted {len(deletions)} files ({total_bytes / 1_000_000:.1f} MB freed).")
    else:
        print(f"\nRe-run with --execute to actually delete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true", help="Actually delete files (default: dry-run)"
    )
    args = parser.parse_args()
    main(execute=args.execute)
