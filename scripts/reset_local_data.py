#!/usr/bin/env python3
"""Reset local data for the Opportunity Analysis Tool.

This script NEVER deletes source code, templates, fixed test fixtures,
configuration, or .env. It only targets machine-local runtime data:
SQLite database, user uploads, generated reports, logs, and temp files.

Default mode is DRY-RUN: it shows what would be deleted without removing
anything. Pass --confirm to actually delete.

Usage:
    # Dry-run (default) — shows what would be deleted
    python scripts/reset_local_data.py

    # Actually delete
    python scripts/reset_local_data.py --confirm

    # Show this help
    python scripts/reset_local_data.py --help
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)

# Machine-local data targets. NEVER include source/templates here.
TARGET_PATHS = [
    "data/web.db",
    "data/web.db-journal",
    "data/web.db-wal",
    "data/web.db-shm",
    "data/web_storage",
    "data/output",
    "data/amazon/output",
    "logs",
    "temp",
]

# Protected paths that must never be deleted — sanity-check list.
PROTECTED_PATHS = [
    "src",
    "backend",
    "frontend",
    "tests",
    "config",
    "scripts",
    "docs",
    "handoff",
    "deploy",
    "examples",
    "data/raw",
    "data/amazon/demo_product_input.json",
    "data/amazon/demo_competitors.csv",
    "data/amazon/demo_reviews.csv",
    "data/amazon/input",
    "data/amazon/templates",
    "requirements.txt",
    ".env",
    ".env.example",
    ".gitignore",
    "README.md",
    "CONTRIBUTING.md",
]


def _dry_run() -> int:
    print("=" * 72)
    print("DRY-RUN: showing what would be deleted. No files removed.")
    print("=" * 72)
    total_files = 0
    total_bytes = 0
    for rel in TARGET_PATHS:
        path = PROJECT_ROOT / rel
        if not path.exists():
            print(f"  [SKIP] {rel} (does not exist)")
            continue
        if path.is_file():
            size = path.stat().st_size
            total_files += 1
            total_bytes += size
            print(f"  [FILE] {rel} ({size} bytes)")
        elif path.is_dir():
            count = 0
            size = 0
            for fpath in path.rglob("*"):
                if fpath.is_file():
                    try:
                        size += fpath.stat().st_size
                        count += 1
                    except OSError:
                        pass
            total_files += count
            total_bytes += size
            print(f"  [DIR ] {rel}/ ({count} files, {size} bytes)")
    print("-" * 72)
    print(f"Total: {total_files} files, {total_bytes} bytes would be deleted.")
    print("\nProtected (NOT deleted): source, templates, tests, config, .env, docs.")
    print("To actually delete, run: python scripts/reset_local_data.py --confirm")
    return 0


def _confirm_delete() -> int:
    print("=" * 72)
    print("CONFIRMED DELETE: removing machine-local runtime data.")
    print("=" * 72)
    # Safety: ensure none of the TARGET_PATHS is inside a protected path.
    for rel in TARGET_PATHS:
        path = (PROJECT_ROOT / rel).resolve()
        for prot in PROTECTED_PATHS:
            prot_abs = (PROJECT_ROOT / prot).resolve()
            try:
                path.relative_to(prot_abs)
                print(f"  [ABORT] target {rel} is inside protected {prot}")
                return 2
            except ValueError:
                pass
    deleted = 0
    for rel in TARGET_PATHS:
        path = PROJECT_ROOT / rel
        if not path.exists():
            print(f"  [SKIP] {rel} (does not exist)")
            continue
        try:
            if path.is_file():
                path.unlink()
                print(f"  [DEL ] {rel}")
                deleted += 1
            elif path.is_dir():
                shutil.rmtree(path)
                print(f"  [RMDIR] {rel}/")
                deleted += 1
        except OSError as exc:
            print(f"  [ERR ] {rel}: {exc!r}")
    # Recreate empty required dirs so the app can start again.
    for empty in ["data/web_storage", "data/output", "logs", "temp"]:
        try:
            (PROJECT_ROOT / empty).mkdir(parents=True, exist_ok=True)
            print(f"  [MKDIR] {empty}/")
        except OSError as exc:
            print(f"  [ERR ] cannot recreate {empty}: {exc!r}")
    print("-" * 72)
    print(f"Deleted {deleted} target(s). Required empty dirs recreated.")
    print("Next: run scripts/check_environment.py, then start backend.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset local runtime data (SQLite, uploads, reports, logs)."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete. Without this flag, only show what would be deleted.",
    )
    args = parser.parse_args()
    if args.confirm:
        return _confirm_delete()
    return _dry_run()


if __name__ == "__main__":
    sys.exit(main())
