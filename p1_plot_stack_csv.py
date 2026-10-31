#!/usr/bin/env python3
"""Plot CCF availability from multiple CSV files, colored by source file."""

import argparse
import csv
import math
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path


def parse_date(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"Expected YYYY-MM-DD, got {value!r}")
    return date.fromisoformat(value)


def cli_date(value):
    try:
        return parse_date(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def positive_int(value):
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Must be a positive integer.") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("Must be a positive integer.")
    return number


def load_csvs(folder, components=None, start=None, end=None):
    """Group dates by source file, component, and station pair."""
    files = sorted(
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() == ".csv"
    )
    if not files:
        raise ValueError(f"No CSV files found in {folder}")

    selected = set(components) if components else None
    groups = defaultdict(set)

    for path in files:
        skipped = 0

        with path.open("r", newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            required = {"component", "station_pair", "date"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    f"{path.name}: missing columns: {', '.join(sorted(missing))}"
                )

            for record in reader:
                component = (record.get("component") or "").strip()
                pair = (record.get("station_pair") or "").strip()

                if selected and component not in selected:
                    continue

                available = record.get("available")
                if available is not None:
                    available = available.strip().lower()
                    if available in {"0", "false", "no"}:
                        continue
                    if available not in {"1", "true", "yes"}:
                        skipped += 1
                        continue

                if not component or not pair:
                    skipped += 1
                    continue

                try:
                    day = parse_date((record.get("date") or "").strip())
                except ValueError:
                    skipped += 1
                    continue

                if start and day < start:
                    continue
                if end and day > end:
                    continue

                groups[(path.name, component, pair)].add(day)

        if skipped:
            print(
                f"Warning: {path.name}: skipped {skipped} invalid records.",
                file=sys.stderr,
            )

    rows = []
    for (source, component, pair), days in sorted(groups.items()):
        parts = pair.split("_")
        if len(parts) == 4 and all(parts):
            network1, station1, network2, station2 = parts
            label = (
                f"{network1}.{station1}–{network2}.{station2}.{component}"
            )
        else:
            label = f"{pair}.{component}"

        rows.append((source, label, sorted(days)))

    return rows


def day_intervals(days, mdates):
    """Merge consecutive available days without allocating a daily matrix."""
    spans = []
    first = previous = days[0]

    for current in days[1:]:
        if current.toordinal() == previous.toordinal() + 1:
            previous = current
            continue

        spans.append((
            mdates.date2num(first),
            previous.toordinal() - first.toordinal() + 1,
        ))
        first = previous = current

    spans.append((
        mdates.date2num(first),
        previous.toordinal() - first.toordinal() + 1,
    ))
    return spans


def plot(rows, args):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
    except ImportError as exc:
        raise RuntimeError(
            "Install Matplotlib: python -m pip install matplotlib"
        ) from exc

    sources = sorted({source for source, _, _ in rows})

    # High-contrast palette for any study area.
    palette = [
        "#0072B2",  # Blue
        "#D55E00",  # Vermilion
        "#009E73",  # Green
        "#CC79A7",  # Purple
        "#E69F00",  # Orange
        "#000000",  # Black
        "#56B4E9",  # Sky blue
        "#8B4513",  # Brown
    ]

    if len(sources) > len(palette):
        raise ValueError(
            f"Found {len(sources)} CSV files, but the palette contains "
            f"{len(palette)} distinct colors. Extend the palette."
        )

    colors = {
        source: palette[index]
        for index, source in enumerate(sources)
    }

    earliest = min(days[0] for _, _, days in rows)
    latest = max(days[-1] for _, _, days in rows)
    left = args.start or earliest
    right = args.end or latest
    page_count = math.ceil(len(rows) / args.rows_per_page)

    args.output.parent.mkdir(parents=True, exist_ok=True)

    for page_index in range(page_count):
        page_rows = rows[
            page_index * args.rows_per_page:
            (page_index + 1) * args.rows_per_page
        ]

        height = max(4.5, 2.4 + 0.24 * len(page_rows))
        figure, axis = plt.subplots(
            figsize=(16, height),
            dpi=args.dpi,
            layout="constrained",
        )

        for row_index, (source, label, days) in enumerate(page_rows):
            axis.broken_barh(
                day_intervals(days, mdates),
                (row_index - 0.38, 0.76),
                facecolors=colors[source],
                edgecolors="none",
            )

        axis.set_yticks(range(len(page_rows)))
        axis.set_yticklabels(
            [
                f"{label} [{Path(source).stem}]"
                for source, label, _ in page_rows
            ],
            fontsize=8,
        )

        for tick, (source, _, _) in zip(
            axis.get_yticklabels(), page_rows
        ):
            tick.set_color(colors[source])

        axis.set_ylim(len(page_rows) - 0.5, -0.5)
        axis.set_xlim(
            mdates.date2num(left),
            mdates.date2num(right) + 1,
        )
        axis.xaxis_date()

        locator = mdates.AutoDateLocator(minticks=4, maxticks=12)
        axis.xaxis.set_major_locator(locator)
        axis.xaxis.set_major_formatter(
            mdates.ConciseDateFormatter(locator)
        )

        axis.grid(axis="x", alpha=0.25)
        axis.set_axisbelow(True)
        axis.set_xlabel("Date")
        axis.set_ylabel("Network.station pair.component [CSV source]")

        page_suffix = (
            f" — page {page_index + 1}/{page_count}"
            if page_count > 1 else ""
        )
        axis.set_title(
            f"{args.title} ({earliest.isoformat()} to "
            f"{latest.isoformat()}){page_suffix}"
        )

        handles = [
            Patch(facecolor=colors[source], label=Path(source).stem)
            for source in sources
        ]
        axis.legend(
            handles=handles,
            loc="lower left",
            bbox_to_anchor=(0, 1.06),
            ncol=min(4, len(handles)),
            fontsize=8,
            frameon=False,
        )

        destination = (
            args.output if page_count == 1
            else args.output.with_name(
                f"{args.output.stem}_{page_index + 1:03d}.png"
            )
        )

        try:
            figure.savefig(destination, format="png")
        finally:
            plt.close(figure)

        print(f"PNG: {destination}")

    print(
        f"Plotted {len(rows):,} rows from {len(sources)} CSV files."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-i", "--input",
        type=Path,
        default=Path("stack_csv"),
        help="Folder containing CSV files (default: stack_csv).",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("combined_availability.png"),
    )
    parser.add_argument(
        "--components", nargs="+",
        help="Optional component filter, e.g. EE ZZ.",
    )
    parser.add_argument("--start", type=cli_date)
    parser.add_argument("--end", type=cli_date)
    parser.add_argument(
        "--rows-per-page", type=positive_int, default=80,
    )
    parser.add_argument("--dpi", type=positive_int, default=150)
    parser.add_argument(
        "--title", default="Daily CCF availability",
    )
    args = parser.parse_args()

    if not args.input.is_dir():
        parser.error(f"Input folder does not exist: {args.input}")
    if args.output.suffix.lower() != ".png":
        parser.error("--output must end with .png")
    if args.start and args.end and args.start > args.end:
        parser.error("--start must be on or before --end")

    try:
        rows = load_csvs(
            args.input, args.components, args.start, args.end
        )
        if not rows:
            raise ValueError("No available days match the selected filters.")
        plot(rows, args)
    except (OSError, ValueError, RuntimeError, csv.Error) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
