#!/usr/bin/env python3
"""Convert daily DTT tables into station-pair DVV time series."""

import argparse
import csv
import math
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def parse_date(value):
    value = value.strip()

    if re.fullmatch(r"\d{7}", value):
        parsed = datetime.strptime(value, "%Y%j")
        if parsed.strftime("%Y%j") != value:
            raise ValueError(f"Invalid year/day-of-year date: {value}")
        return parsed.date()

    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    ).date()


def numeric_value(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return number if math.isfinite(number) else None


def convert_component(folder, destination, include_all=False):
    observations = defaultdict(lambda: defaultdict(list))
    invalid_rows = 0
    skipped_all = 0
    duplicate_rows = 0

    files = sorted(
        path for path in folder.iterdir()
        if path.is_file()
        and path.suffix.lower() == ".txt"
        and not path.name.startswith(".")
    )

    for source in files:
        with source.open(
            "r", newline="", encoding="utf-8-sig"
        ) as stream:
            reader = csv.DictReader(stream)
            required = {"Date", "Pairs", "M", "M0", "EM", "EM0"}
            missing = required - set(reader.fieldnames or [])

            if missing:
                raise ValueError(
                    f"{source}: missing columns "
                    f"{', '.join(sorted(missing))}"
                )

            for record in reader:
                pair = (record.get("Pairs") or "").strip()

                if pair == "ALL":
                    if not include_all:
                        skipped_all += 1
                        continue
                elif not re.fullmatch(
                    r"[A-Za-z0-9]+_[A-Za-z0-9]+_"
                    r"[A-Za-z0-9]+_[A-Za-z0-9]+",
                    pair,
                ):
                    invalid_rows += 1
                    continue

                try:
                    day = parse_date(record.get("Date") or "")
                except (ValueError, TypeError, OverflowError):
                    invalid_rows += 1
                    continue

                value_m = numeric_value(record.get("M"))
                value_m0 = numeric_value(record.get("M0"))
                error_m = numeric_value(record.get("EM"))
                error_m0 = numeric_value(record.get("EM0"))

                if value_m is None and value_m0 is None:
                    invalid_rows += 1
                    continue

                # Uncertainties must be nonnegative and accompany a value.
                if value_m is None or (
                    error_m is not None and error_m < 0
                ):
                    error_m = None

                if value_m0 is None or (
                    error_m0 is not None and error_m0 < 0
                ):
                    error_m0 = None

                if day in observations[pair]:
                    duplicate_rows += 1

                observations[pair][day].append((
                    -value_m if value_m is not None else None,
                    -value_m0 if value_m0 is not None else None,
                    error_m,
                    error_m0,
                ))

    if not observations:
        print(f"No valid data: {folder}")
        return 0, 0

    def combine(records, value_index, error_index):
        valid = [
            (record[value_index], record[error_index])
            for record in records
            if record[value_index] is not None
        ]

        if not valid:
            return "", ""

        count = len(valid)
        mean_value = math.fsum(value for value, _ in valid) / count

        if any(error is None for _, error in valid):
            return mean_value, ""

        # Propagate uncertainties for an unweighted mean,
        # assuming independent measurements.
        mean_error = math.hypot(
            *(error for _, error in valid)
        ) / count

        return mean_value, mean_error

    destination.mkdir(parents=True, exist_ok=True)
    output_rows = 0

    for pair, dated_records in sorted(observations.items()):
        output = destination / f"{pair}.txt"

        with output.open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.writer(stream)
            writer.writerow([
                "Date",
                "dvv_M",
                "dvv_M0",
                "dvv_EM",
                "dvv_EM0",
            ])

            for day, records in sorted(dated_records.items()):
                mean_m, error_m = combine(records, 0, 2)
                mean_m0, error_m0 = combine(records, 1, 3)

                writer.writerow([
                    day.strftime("%Y%j"),
                    mean_m,
                    mean_m0,
                    error_m,
                    error_m0,
                ])
                output_rows += 1

    print(
        f"{folder} -> {destination}: "
        f"{len(observations)} pair files, {output_rows} dated rows"
    )

    if invalid_rows:
        print(
            f"  Warning: skipped {invalid_rows} invalid rows.",
            file=sys.stderr,
        )

    if duplicate_rows:
        print(
            f"  Averaged {duplicate_rows} duplicate pair/date rows; "
            "propagated uncertainties assuming independence."
        )

    if skipped_all:
        print(f"  Skipped {skipped_all} aggregate ALL rows.")

    return len(observations), output_rows

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-path",
        type=Path,
        default=Path("."),
        help="Project containing DTT; default: current directory.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Override the input DTT directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Override the output DVV directory.",
    )
    parser.add_argument(
        "--include-all",
        action="store_true",
        help="Also export aggregate ALL rows to ALL.txt.",
    )
    args = parser.parse_args()

    source_root = (
        args.input if args.input is not None
        else args.project_path / "DTT"
    )
    output_root = (
        args.output if args.output is not None
        else args.project_path / "DVV"
    )

    if not source_root.is_dir():
        parser.error(f"DTT directory not found: {source_root}")

    source_resolved = source_root.resolve()
    output_resolved = output_root.resolve()

    if (
        source_resolved == output_resolved
        or source_resolved in output_resolved.parents
        or output_resolved in source_resolved.parents
    ):
        parser.error("Input and output directories must not overlap.")

    # A fresh output directory avoids stale station-pair files.
    if output_root.exists():
        parser.error(
            f"Output already exists: {output_root}. "
            "Choose a new --output directory."
        )

    total_files = 0
    total_rows = 0
    component_count = 0

    try:
        for filter_folder in sorted(source_root.iterdir()):
            if (
                not filter_folder.is_dir()
                or not filter_folder.name.isdigit()
            ):
                continue

            for stack_folder in sorted(filter_folder.iterdir()):
                if (
                    not stack_folder.is_dir()
                    or not re.fullmatch(
                        r"\d+(?:pm)?_DAYS", stack_folder.name
                    )
                ):
                    continue

                for component_folder in sorted(stack_folder.iterdir()):
                    if (
                        not component_folder.is_dir()
                        or component_folder.name.startswith(".")
                    ):
                        continue

                    relative = component_folder.relative_to(source_root)
                    file_count, row_count = convert_component(
                        component_folder,
                        output_root / relative,
                        include_all=args.include_all,
                    )

                    component_count += 1
                    total_files += file_count
                    total_rows += row_count

    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        parser.exit(
            1,
            f"Error: {exc}\n"
            "Conversion stopped; output may be incomplete.\n",
        )

    if not total_files:
        parser.exit(1, "No valid DTT data found.\n")

    print(
        f"\nFinished: {component_count} component folders, "
        f"{total_files} DVV files, {total_rows} dated rows."
    )
    print(f"Output: {output_root}")


if __name__ == "__main__":
    main()
