"""CLI tool for managing the 1RM exercise list."""

import argparse
import sys
from pathlib import Path

from wodplanner.services.one_rep_max import OneRepMaxService, resolve_exercise_interactive


def main():
    parser = argparse.ArgumentParser(description="Add an exercise to the 1RM exercise list")
    parser.add_argument(
        "--exercise",
        type=str,
        help="Exercise name to add (will fuzzy-match against existing list)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("wodplanner.db"),
        help="Path to the database file (default: wodplanner.db)",
    )
    args = parser.parse_args()

    service = OneRepMaxService(args.db)
    exercises = service.get_exercise_list()

    raw_name = args.exercise.strip() if args.exercise else None
    if not raw_name:
        print("Existing exercises:")
        for i, ex in enumerate(exercises, 1):
            print(f"  {i}. {ex}")
        raw_name = input("\nEnter new exercise name: ").strip()
        if not raw_name:
            print("No name provided. Exiting.")
            sys.exit(0)

    resolved = resolve_exercise_interactive(raw_name, exercises)

    if resolved is None:
        print("Skipped.")
        sys.exit(0)

    if resolved in exercises:
        print(f'Exercise "{resolved}" already exists in the list.')
        sys.exit(0)

    service.add_exercise(resolved)
    print(f'Added "{resolved}" to the 1RM exercise list.')
