"""CLI tool for importing workout schedules from PDF files."""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import pdfplumber

from wodplanner.models.schedule import Schedule
from wodplanner.services.schedule import ScheduleService, normalize_class_name


# Dutch month names to month numbers
DUTCH_MONTHS = {
    "januari": 1,
    "februari": 2,
    "maart": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "augustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}


def parse_dutch_date(date_str: str, year: int) -> date | None:
    """Parse a Dutch date string like 'Maandag 13 April' to a date object."""
    # Pattern: Day name + day number + month name
    pattern = r"(?:Maandag|Dinsdag|Woensdag|Donderdag|Vrijdag|Zaterdag|Zondag)\s+(\d+)\s+(\w+)"
    match = re.match(pattern, date_str, re.IGNORECASE)
    if not match:
        return None

    day = int(match.group(1))
    month_name = match.group(2).lower()

    month = DUTCH_MONTHS.get(month_name)
    if not month:
        return None

    try:
        return date(year, month, day)
    except ValueError:
        return None


def is_date_row(text: str) -> bool:
    """Check if the text looks like a date row (e.g., 'Maandag 13 April')."""
    if not text:
        return False
    pattern = r"^(Maandag|Dinsdag|Woensdag|Donderdag|Vrijdag|Zaterdag|Zondag)\s+\d+\s+\w+"
    return bool(re.match(pattern, text.strip(), re.IGNORECASE))


def is_class_name(text: str) -> bool:
    """Check if the text looks like a class name."""
    if not text:
        return False

    # Known class patterns
    class_patterns = [
        r"^CrossFit",
        r"^CF101",
        r"^Boxing",
        r"^HyCross",
        r"^Gymnastics",
        r"^Olympic",
        r"^Oly",
        r"^Strength",
        r"^Teen Athlete",
        r"^Strongman",
    ]

    text = text.strip()
    for pattern in class_patterns:
        if re.match(pattern, text, re.IGNORECASE):
            return True
    return False


def clean_text(text: str | None) -> str | None:
    """Clean up extracted text."""
    if not text:
        return None
    # Collapse horizontal whitespace per line, preserve newlines
    lines = text.strip().split("\n")
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in lines]
    lines = [line for line in lines if line]
    # Join lines that continue an unclosed parenthetical (PDF line-wrap artifact)
    merged: list[str] = []
    for line in lines:
        if merged and merged[-1].count("(") > merged[-1].count(")"):
            merged[-1] += " " + line
        else:
            merged.append(line)
    text = "\n".join(merged)
    return text if text else None


def append_content(existing: str | None, new: str | None) -> str | None:
    """Append new content to existing, handling None values."""
    if not new:
        return existing
    if not existing:
        return new
    return f"{existing}\n{new}"


def is_continuation_row(row: list[str | None]) -> bool:
    """Check if this row is a continuation of the previous class (empty first cell, content in others)."""
    if not row:
        return False
    # First cell is empty or None
    first_cell = row[0]
    if first_cell and first_cell.strip():
        return False
    # But has content in other cells
    return any(cell and cell.strip() for cell in row[1:])


def extract_schedules_from_pdf(pdf_path: Path, year: int) -> list[Schedule]:
    """Extract schedule entries from a PDF file."""
    schedules: list[Schedule] = []
    source_file = pdf_path.name

    with pdfplumber.open(pdf_path) as pdf:
        current_date: date | None = None
        last_schedule: Schedule | None = None

        for page in pdf.pages:
            # Extract tables from the page
            tables = page.extract_tables()

            for table in tables:
                if not table:
                    continue

                for row in table:
                    if not row or not any(row):
                        continue

                    # Clean the row
                    row = [clean_text(cell) if cell else None for cell in row]

                    # Check if this is a continuation row (empty first cell, content in others)
                    # This happens when a table row spans across pages
                    if is_continuation_row(row) and last_schedule:
                        # Append content to the last schedule
                        if len(row) > 1 and row[1]:
                            last_schedule.warmup_mobility = append_content(
                                last_schedule.warmup_mobility, row[1]
                            )
                        if len(row) > 2 and row[2]:
                            last_schedule.strength_specialty = append_content(
                                last_schedule.strength_specialty, row[2]
                            )
                        if len(row) > 3 and row[3]:
                            last_schedule.metcon = append_content(
                                last_schedule.metcon, row[3]
                            )
                        # Update raw content
                        raw_parts = [p for p in row if p]
                        if raw_parts:
                            last_schedule.raw_content = append_content(
                                last_schedule.raw_content, " | ".join(raw_parts)
                            )
                        continue

                    # Get first cell to check for date or class
                    first_cell = row[0] if row else None

                    if not first_cell:
                        continue

                    # Check if this is a date row
                    if is_date_row(first_cell):
                        parsed_date = parse_dutch_date(first_cell, year)
                        if parsed_date:
                            current_date = parsed_date
                        continue

                    # Skip header rows
                    if first_cell.lower() in ("datum", "warming-up & mobility"):
                        continue

                    # Check if this is a class entry
                    if is_class_name(first_cell) and current_date:
                        class_type = normalize_class_name(first_cell)

                        # Extract workout details from remaining columns
                        warmup_mobility = row[1] if len(row) > 1 else None
                        strength_specialty = row[2] if len(row) > 2 else None
                        metcon = row[3] if len(row) > 3 else None

                        # Create raw content for reference
                        raw_parts = [p for p in row if p]
                        raw_content = " | ".join(raw_parts)

                        schedule = Schedule(
                            date=current_date,
                            class_type=class_type,
                            warmup_mobility=warmup_mobility,
                            strength_specialty=strength_specialty,
                            metcon=metcon,
                            raw_content=raw_content,
                            source_file=source_file,
                        )
                        schedules.append(schedule)
                        last_schedule = schedule

    return schedules


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Import workout schedules from CrossFit Purmerend PDF files"
    )
    parser.add_argument(
        "pdf_file",
        type=Path,
        help="Path to the PDF file to import",
    )
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Year for the schedule dates (e.g., 2026)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and display schedules without saving to database",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("wodplanner.db"),
        help="Path to the database file (default: wodplanner.db)",
    )

    args = parser.parse_args()

    # Validate PDF file exists
    if not args.pdf_file.exists():
        print(f"Error: PDF file not found: {args.pdf_file}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing PDF: {args.pdf_file}")
    print(f"Year: {args.year}")

    # Extract schedules from PDF
    schedules = extract_schedules_from_pdf(args.pdf_file, args.year)

    if not schedules:
        print("No schedules found in PDF")
        sys.exit(0)

    print(f"\nFound {len(schedules)} schedule entries:")
    print("-" * 60)

    # Group by date for display
    by_date: dict[date, list[Schedule]] = {}
    for schedule in schedules:
        if schedule.date not in by_date:
            by_date[schedule.date] = []
        by_date[schedule.date].append(schedule)

    for schedule_date in sorted(by_date.keys()):
        print(f"\n{schedule_date.strftime('%A %d %B %Y')}:")
        for schedule in by_date[schedule_date]:
            metcon_preview = ""
            if schedule.metcon:
                metcon_preview = schedule.metcon[:50] + "..." if len(schedule.metcon) > 50 else schedule.metcon
            print(f"  - {schedule.class_type}: {metcon_preview}")

    if args.dry_run:
        print("\n[Dry run - not saving to database]")
        sys.exit(0)

    # Save to database
    print(f"\nSaving to database: {args.db}")
    service = ScheduleService(args.db)
    count = service.bulk_add(schedules)
    print(f"Successfully saved {count} schedule entries")


if __name__ == "__main__":
    main()
