#!/usr/bin/env python3
"""Plot daily CCF availability from component/station-pair folders."""

import argparse
import csv
import math
import re
import sys
from datetime import date
from pathlib import Path

FILENAME = re.compile(r"(\d{4}-\d{2}-\d{2})\.mseed", re.IGNORECASE)


def parse_date(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise argparse.ArgumentTypeError("Use YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Must be a positive integer.")
    return number


def warn(message):
    print(f"Warning: {message}", file=sys.stderr)


def scan(root, components=None, start=None, end=None):
    """Return (component, pair, label, sorted dates) rows, including empty rows."""
    rows = []
    selected = set(components) if components else None

    for component_dir in sorted(root.iterdir()):
        if not component_dir.is_dir():
            continue
        if selected and component_dir.name not in selected:
            continue

        for pair_dir in sorted(component_dir.iterdir()):
            if not pair_dir.is_dir():
                continue

            parts = pair_dir.name.split("_")
            if len(parts) != 4 or not all(parts):
                warn(f"Skipping malformed station-pair folder: {pair_dir}")
                continue

            network1, station1, network2, station2 = parts
            label = (
                f"{network1}.{station1}–{network2}.{station2}"
                f".{component_dir.name}"
            )
            days = set()

            for entry in pair_dir.iterdir():
                if not entry.is_file() or entry.suffix.lower() != ".mseed":
                    continue

                match = FILENAME.fullmatch(entry.name)
                if not match:
                    warn(f"Skipping malformed MiniSEED filename: {entry}")
                    continue

                try:
                    day = date.fromisoformat(match.group(1))
                except ValueError:
                    warn(f"Skipping invalid calendar date: {entry}")
                    continue

                if start and day < start:
                    continue
                if end and day > end:
                    continue
                days.add(day)

            rows.append(
                (component_dir.name, pair_dir.name, label, sorted(days))
            )

    return rows


def intervals(days, mdates):
    """Merge consecutive days into sparse (start, duration) intervals."""
    if not days:
        return []

    result = []
    first = previous = days[0]
    for current in days[1:]:
        if current.toordinal() == previous.toordinal() + 1:
            previous = current
            continue
        result.append(
            (mdates.date2num(first), previous.toordinal() - first.toordinal() + 1)
        )
        first = previous = current

    result.append(
        (mdates.date2num(first), previous.toordinal() - first.toordinal() + 1)
    )
    return result


def export_csv(rows, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["component", "station_pair", "label", "date", "available"]
        )
        for component, pair, label, days in rows:
            for day in days:
                writer.writerow([component, pair, label, day.isoformat(), 1])


def plot(rows, output, start, end, rows_per_page, dpi, title):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "Matplotlib is required: python -m pip install matplotlib"
        ) from exc

    earliest = min((days[0] for _, _, _, days in rows if days), default=None)
    latest = max((days[-1] for _, _, _, days in rows if days), default=None)

    left = start or earliest
    right = end or latest
    if left is None or right is None:
        raise ValueError(
            "No valid dates found. Supply both --start and --end "
            "to plot empty station-pair rows."
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    page_count = math.ceil(len(rows) / rows_per_page)

    for page_number in range(page_count):
        page_rows = rows[
            page_number * rows_per_page:(page_number + 1) * rows_per_page
        ]
        height = max(4.0, 1.8 + 0.24 * len(page_rows))
        figure, axis = plt.subplots(
            figsize=(16, height), dpi=dpi, layout="constrained"
        )

        for row_index, (_, _, _, days) in enumerate(page_rows):
            spans = intervals(days, mdates)
            if spans:
                axis.broken_barh(
                    spans, (row_index - 0.38, 0.76),
                    facecolors="#1676B8", edgecolors="none"
                )

        axis.set_yticks(range(len(page_rows)))
        axis.set_yticklabels([row[2] for row in page_rows], fontsize=8)
        axis.set_ylim(len(page_rows) - 0.5, -0.5)
        axis.set_xlim(mdates.date2num(left), mdates.date2num(right) + 1)
        axis.xaxis_date()

        locator = mdates.AutoDateLocator(minticks=4, maxticks=12)
        axis.xaxis.set_major_locator(locator)
        axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        axis.grid(axis="x", alpha=0.25)
        axis.set_axisbelow(True)
        axis.set_xlabel("Date (each blue interval marks available days)")
        axis.set_ylabel("Network.station pair.component")

        suffix = (
            f" — page {page_number + 1}/{page_count}" if page_count > 1 else ""
        )
        if earliest is not None and latest is not None:
            date_range = f" ({earliest.isoformat()} to {latest.isoformat()})"
        else:
            date_range = " (no available days)"
        
        axis.set_title(title + date_range + suffix)
        
        destination = (
            output if page_count == 1 else output.with_name(
                f"{output.stem}_{page_number + 1:03d}.png"
            )
        )
        try:
            figure.savefig(destination, format="png")
        finally:
            plt.close(figure)
        print(f"PNG: {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-i", "--input", type=Path, default=Path("STACKS/01/001_DAYS"),
        help="Directory containing component folders."
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("availability.png"),
        help="PNG destination; multiple pages receive _001, _002, etc."
    )
    parser.add_argument(
        "--components", nargs="+", help="Optional component names, e.g. EE ZZ."
    )
    parser.add_argument("--start", type=parse_date, help="Inclusive YYYY-MM-DD.")
    parser.add_argument("--end", type=parse_date, help="Inclusive YYYY-MM-DD.")
    parser.add_argument("--csv", type=Path, help="Optional available-day CSV.")
    parser.add_argument("--rows-per-page", type=positive_int, default=80)
    parser.add_argument("--dpi", type=positive_int, default=150)
    parser.add_argument("--title", default="Daily CCF availability")
    args = parser.parse_args()

    if not args.input.is_dir():
        parser.error(f"Input directory does not exist: {args.input}")
    if args.output.suffix.lower() != ".png":
        parser.error("--output must have a .png extension.")
    if args.start and args.end and args.start > args.end:
        parser.error("--start must be on or before --end.")
    if args.csv and args.csv.resolve() == args.output.resolve():
        parser.error("--csv and --output must be different paths.")

    try:
        rows = scan(args.input, args.components, args.start, args.end)
        if not rows:
            parser.error("No matching station-pair folders found.")

        plot(
            rows, args.output, args.start, args.end,
            args.rows_per_page, args.dpi, args.title
        )
        if args.csv:
            export_csv(rows, args.csv)
            print(f"CSV: {args.csv}")

        total = sum(len(days) for _, _, _, days in rows)
        print(f"Found {total:,} available row-days across {len(rows):,} rows.")
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
