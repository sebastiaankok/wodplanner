"""CLI tool for managing the benchmark WOD list."""

import argparse
import sys
from pathlib import Path

from wodplanner.services.benchmark import BenchmarkService
from wodplanner.services.migrations import ensure_migrations


def main():
    parser = argparse.ArgumentParser(description="Add a benchmark WOD to the list")
    parser.add_argument(
        "--name",
        type=str,
        help="Benchmark WOD name to add",
    )
    parser.add_argument(
        "--category",
        type=str,
        default="Benchmark",
        help="Category (e.g. 'The Girls', 'Hero', 'Benchmark')",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("wodplanner.db"),
        help="Path to the database file (default: wodplanner.db)",
    )
    args = parser.parse_args()

    ensure_migrations(args.db)
    service = BenchmarkService(args.db)

    raw_name = args.name.strip() if args.name else None
    if not raw_name:
        names = service.get_benchmark_list()
        print("Existing benchmark WODs:")
        for i, name in enumerate(names, 1):
            print(f"  {i}. {name}")
        raw_name = input("\nEnter new benchmark name: ").strip()
        if not raw_name:
            print("No name provided. Exiting.")
            sys.exit(0)

    category = input(f"Category [{args.category}]: ").strip() or args.category

    if service.add_benchmark_wod(raw_name, category):
        print(f'Added "{raw_name}" (category: {category}) to the benchmark WOD list.')
    else:
        print(f'Benchmark "{raw_name}" already exists in the list.')
        sys.exit(1)
