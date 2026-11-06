#!/usr/bin/env python3
"""Scan MWCS Zarr files and plot daily measurement availability."""

import argparse
import csv
import math
import re
import sys

from datetime import date, datetime, timedelta
from pathlib import Path


PAIR_NAME = re.compile(
    r"^([^. _]+)\.([^_]+)_([^. _]+)\.([^_]+)$"
)


# ============================================================
# Arguments and utilities
# ============================================================

def parse_date(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise argparse.ArgumentTypeError("Use YYYY-MM-DD.")

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def positive_int(value):
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Must be a positive integer."
        ) from exc

    if number < 1:
        raise argparse.ArgumentTypeError(
            "Must be a positive integer."
        )

    return number


def warn(message):
    print(f"Warning: {message}", file=sys.stderr)


def yyyyddd_to_date(value):
    """
    Convert YYYYJJJ integer to Python date.

    Example:
        2015001 -> 2015-01-01
        2015365 -> 2015-12-31
        2016366 -> 2016-12-31
    """

    value = int(value)

    year = value // 1000
    jday = value % 1000

    if not 1 <= year <= 9999:
        raise ValueError(f"Invalid year: {value}")

    days_in_year = (
        date(year + 1, 1, 1) - date(year, 1, 1)
    ).days if year < 9999 else (
        366 if (
            year % 4 == 0
            and (year % 100 != 0 or year % 400 == 0)
        ) else 365
    )

    if jday < 1 or jday > days_in_year:
        raise ValueError(f"Invalid Julian day: {value}")

    return date(year, 1, 1) + timedelta(days=jday - 1)


# ============================================================
# Read Zarr dates
# ============================================================

def read_zarr_dates(zarr_path, start=None, end=None):
    """
    Read available dates from an MWCS Zarr store.

    Expected structure:

        /
        ├── data (n_dates, n_lags, 4)
        └── date (n_dates,)

    Only the date array is loaded.
    """

    import numpy as np
    import zarr

    root = zarr.open_group(
        str(zarr_path),
        mode="r"
    )

    if "date" not in root:
        raise ValueError(
            f"Missing 'date' array in {zarr_path}"
        )

    if "data" not in root:
        raise ValueError(
            f"Missing 'data' array in {zarr_path}"
        )

    dates_raw = np.asarray(root["date"][:])
    data_shape = root["data"].shape

    if dates_raw.ndim != 1:
        raise ValueError(
            f"Unexpected date shape in {zarr_path}: "
            f"{dates_raw.shape}"
        )

    if len(data_shape) != 3:
        raise ValueError(
            f"Unexpected data shape in {zarr_path}: "
            f"{data_shape}"
        )

    if data_shape[0] != len(dates_raw):
        raise ValueError(
            f"Date/data length mismatch in {zarr_path}: "
            f"{len(dates_raw)} vs {data_shape[0]}"
        )

    days = set()

    for value in dates_raw:

        try:
            day = yyyyddd_to_date(value)
        except (ValueError, TypeError, OverflowError) as exc:
            warn(
                f"Skipping invalid date {value} "
                f"in {zarr_path}: {exc}"
            )
            continue

        if start is not None and day < start:
            continue

        if end is not None and day > end:
            continue

        days.add(day)

    return sorted(days)


# ============================================================
# Scan all components / station pairs
# ============================================================

def scan(root, components=None, start=None, end=None):
    """
    Return rows:

        (component, pair, label, sorted_dates)

    Includes empty rows when a Zarr has no matching dates.
    """

    rows = []
    selected = set(components) if components else None

    component_dirs = sorted(
        path for path in root.iterdir()
        if path.is_dir()
    )

    for component_dir in component_dirs:

        component = component_dir.name

        if selected and component not in selected:
            continue

        print(f"Scanning component: {component}")

        zarr_paths = sorted(
            path for path in component_dir.iterdir()
            if path.is_dir()
            and path.name.lower().endswith(".zarr")
        )

        print(f"  Found {len(zarr_paths)} Zarr stores")

        for index, zarr_path in enumerate(zarr_paths, start=1):

            pair = zarr_path.name[:-5]

            match = PAIR_NAME.fullmatch(pair)

            if not match:
                warn(
                    f"Skipping malformed station-pair "
                    f"Zarr name: {zarr_path}"
                )
                continue

            network1, station1, network2, station2 = (
                match.groups()
            )

            label = (
                f"{network1}.{station1}–"
                f"{network2}.{station2}.{component}"
            )

            try:
                days = read_zarr_dates(
                    zarr_path,
                    start=start,
                    end=end
                )
            except Exception as exc:
                warn(
                    f"Failed to read {zarr_path}: {exc}"
                )
                # Keep the station pair visible as an empty row.
                days = []

            rows.append(
                (component, pair, label, days)
            )

            if index % 20 == 0 or index == len(zarr_paths):
                print(
                    f"  Processed {index}/{len(zarr_paths)}"
                )

    return rows


# ============================================================
# Convert dates to continuous intervals
# ============================================================

def intervals(days, mdates):
    """
    Merge consecutive available dates into intervals.

    Returns:
        [(start_matplotlib_date, duration_days), ...]
    """

    if not days:
        return []

    result = []

    first = previous = days[0]

    for current in days[1:]:

        if current.toordinal() == previous.toordinal() + 1:
            previous = current
            continue

        result.append(
            (
                mdates.date2num(first),
                previous.toordinal()
                - first.toordinal() + 1
            )
        )

        first = previous = current

    result.append(
        (
            mdates.date2num(first),
            previous.toordinal()
            - first.toordinal() + 1
        )
    )

    return result


# ============================================================
# Export availability CSV
# ============================================================

def export_csv(rows, destination):

    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with destination.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as stream:

        writer = csv.writer(stream)

        writer.writerow(
            [
                "component",
                "station_pair",
                "label",
                "date",
                "available"
            ]
        )

        for component, pair, label, days in rows:

            for day in days:

                writer.writerow(
                    [
                        component,
                        pair,
                        label,
                        day.isoformat(),
                        1
                    ]
                )


# ============================================================
# Plot availability
# ============================================================

def plot(
    rows,
    output,
    start,
    end,
    rows_per_page,
    dpi,
    title
):

    import matplotlib
    matplotlib.use("Agg")

    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    earliest = min(
        (
            days[0]
            for _, _, _, days in rows
            if days
        ),
        default=None
    )

    latest = max(
        (
            days[-1]
            for _, _, _, days in rows
            if days
        ),
        default=None
    )

    left = start or earliest
    right = end or latest

    if left is None or right is None:
        raise ValueError(
            "No valid dates found. Supply both "
            "--start and --end to plot empty rows."
        )

    if left > right:
        raise ValueError(
            "Plot start date is after end date."
        )

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    page_count = math.ceil(
        len(rows) / rows_per_page
    )

    for page_number in range(page_count):

        page_rows = rows[
            page_number * rows_per_page:
            (page_number + 1) * rows_per_page
        ]

        height = max(
            4.0,
            1.8 + 0.24 * len(page_rows)
        )

        fig, ax = plt.subplots(
            figsize=(16, height),
            dpi=dpi,
            layout="constrained"
        )

        # ---------------------------------------------
        # Plot daily intervals
        # ---------------------------------------------

        for row_index, (_, _, _, days) in enumerate(page_rows):

            spans = intervals(days, mdates)

            if spans:
                ax.broken_barh(
                    spans,
                    (
                        row_index - 0.38,
                        0.76
                    ),
                    facecolors="#1676B8",
                    edgecolors="none"
                )

        # ---------------------------------------------
        # Y axis
        # ---------------------------------------------

        ax.set_yticks(
            range(len(page_rows))
        )

        ax.set_yticklabels(
            [row[2] for row in page_rows],
            fontsize=8
        )

        ax.set_ylim(
            len(page_rows) - 0.5,
            -0.5
        )

        ax.set_ylabel(
            "Network.station pair.component"
        )

        # ---------------------------------------------
        # X axis
        # ---------------------------------------------

        ax.set_xlim(
            mdates.date2num(left),
            mdates.date2num(right) + 1
        )

        ax.xaxis_date()

        locator = mdates.AutoDateLocator(
            minticks=4,
            maxticks=12
        )

        ax.xaxis.set_major_locator(
            locator
        )

        ax.xaxis.set_major_formatter(
            mdates.ConciseDateFormatter(locator)
        )

        ax.grid(
            axis="x",
            alpha=0.25
        )

        ax.set_axisbelow(True)

        ax.set_xlabel(
            "Date (blue intervals indicate MWCS availability)"
        )

        # ---------------------------------------------
        # Title
        # ---------------------------------------------

        suffix = (
            f" — page {page_number + 1}/{page_count}"
            if page_count > 1
            else ""
        )

        if earliest is not None and latest is not None:
            date_range = (
                f" ({earliest.isoformat()} "
                f"to {latest.isoformat()})"
            )
        else:
            date_range = " (no available days)"

        ax.set_title(
            title + date_range + suffix
        )

        # ---------------------------------------------
        # Save figure
        # ---------------------------------------------

        destination = (
            output
            if page_count == 1
            else output.with_name(
                f"{output.stem}_{page_number + 1:03d}.png"
            )
        )

        try:
            fig.savefig(
                destination,
                format="png"
            )
        finally:
            plt.close(fig)

        print(f"PNG: {destination}")


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=Path(
            "MWCS_unfold/01/pm014_DAYS"
        ),
        help=(
            "Directory containing component folders "
            "with station-pair .zarr stores."
        )
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(
            "mwcs_availability.png"
        ),
        help=(
            "Output PNG; multiple pages receive "
            "_001, _002, etc."
        )
    )

    parser.add_argument(
        "--components",
        nargs="+",
        help="Optional components, e.g. ZZ EE NN."
    )

    parser.add_argument(
        "--start",
        type=parse_date,
        help="Inclusive YYYY-MM-DD."
    )

    parser.add_argument(
        "--end",
        type=parse_date,
        help="Inclusive YYYY-MM-DD."
    )

    parser.add_argument(
        "--csv",
        type=Path,
        help="Optional availability CSV."
    )

    parser.add_argument(
        "--rows-per-page",
        type=positive_int,
        default=80
    )

    parser.add_argument(
        "--dpi",
        type=positive_int,
        default=150
    )

    parser.add_argument(
        "--title",
        default="Daily MWCS availability"
    )

    args = parser.parse_args()

    if not args.input.is_dir():
        parser.error(
            f"Input directory does not exist: {args.input}"
        )

    if args.output.suffix.lower() != ".png":
        parser.error(
            "--output must have a .png extension."
        )

    if (
        args.start
        and args.end
        and args.start > args.end
    ):
        parser.error(
            "--start must be on or before --end."
        )

    if (
        args.csv
        and args.csv.resolve() == args.output.resolve()
    ):
        parser.error(
            "--csv and --output must be different paths."
        )

    try:

        rows = scan(
            args.input,
            args.components,
            args.start,
            args.end
        )

        if not rows:
            parser.error(
                "No matching MWCS Zarr stores found."
            )

        plot(
            rows,
            args.output,
            args.start,
            args.end,
            args.rows_per_page,
            args.dpi,
            args.title
        )

        if args.csv:
            export_csv(
                rows,
                args.csv
            )
            print(f"CSV: {args.csv}")

        total = sum(
            len(days)
            for _, _, _, days in rows
        )

        active_pairs = sum(
            bool(days)
            for _, _, _, days in rows
        )

        print()
        print("=== MWCS availability summary ===")
        print(f"Station-pair/component rows: {len(rows):,}")
        print(f"Rows with available dates: {active_pairs:,}")
        print(f"Available row-days: {total:,}")

    except (
        OSError,
        ValueError,
        RuntimeError
    ) as exc:

        parser.exit(
            1,
            f"Error: {exc}\n"
        )


if __name__ == "__main__":
    main()
