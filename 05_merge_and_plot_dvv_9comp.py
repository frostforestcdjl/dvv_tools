import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from pathlib import Path

# ============================================================
# 1. Configuration
# ============================================================

# Directory containing this script
base_dir = Path(__file__).resolve().parent

# Main DVV directory
dvv_dir = base_dir / "DVV"

# Component combinations
components = [
    "EE", "EN", "EZ",
    "NE", "NN", "NZ",
    "ZE", "ZN", "ZZ"
]

# Plot settings
FIGSIZE = (12, 8)
DPI = 150

# ============================================================
# 2. Find all filter folders
# ============================================================

if not dvv_dir.is_dir():
    raise FileNotFoundError(
        f"DVV directory does not exist: {dvv_dir}"
    )

filter_dirs = sorted(
    [
        folder
        for folder in dvv_dir.iterdir()
        if folder.is_dir() and folder.name.isdigit()
    ],
    key=lambda folder: int(folder.name)
)

print(f"Total filters: {len(filter_dirs)}")

# ============================================================
# 3. Process each filter
# ============================================================

for filter_dir in filter_dirs:

    filter_id = filter_dir.name

    print("\n" + "=" * 60)
    print(f"Processing filter: {filter_id}")
    print("=" * 60)

    # ========================================================
    # 4. Find all valid input folders
    # ========================================================

    input_dirs = sorted(
        [
            folder
            for folder in filter_dir.iterdir()
            if (
                folder.is_dir()

                # Exclude previously generated output folders
                and not folder.name.endswith("_9comp")

                # Require at least one component directory
                # containing TXT files
                and any(
                    (folder / component).is_dir()
                    and any(
                        (folder / component).glob("*.txt")
                    )
                    for component in components
                )
            )
        ]
    )

    print(
        f"Filter {filter_id}: "
        f"{len(input_dirs)} input folders found"
    )

    if not input_dirs:
        print(
            f"No valid input folders found in {filter_dir}"
        )
        continue

    # ========================================================
    # 5. Process each input folder
    # ========================================================

    for input_dir in input_dirs:

        input_name = input_dir.name

        print("\n" + "-" * 60)
        print(f"Processing: {filter_id}/{input_name}")
        print("-" * 60)

        # ----------------------------------------------------
        # Input and output directories
        # ----------------------------------------------------

        output_dir = filter_dir / f"{input_name}_9comp"

        img_dir = output_dir / "img"

        output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        img_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        # ====================================================
        # 6. Find all station pairs
        # ====================================================

        station_pairs = set()

        for component in components:

            component_dir = input_dir / component

            if not component_dir.is_dir():
                print(
                    f"Missing component folder: "
                    f"{component_dir}"
                )
                continue

            for file in component_dir.glob("*.txt"):
                station_pairs.add(file.name)

        station_pairs = sorted(station_pairs)

        print(
            f"Filter {filter_id} | {input_name}: "
            f"{len(station_pairs)} station pairs"
        )

        if not station_pairs:
            print(
                f"No station pairs found in {input_dir}"
            )
            continue

        # ====================================================
        # 7. Process each station pair
        # ====================================================

        for i, pair in enumerate(station_pairs, start=1):

            dfs = []

            # ------------------------------------------------
            # Read dv/v from all available components
            # ------------------------------------------------

            for component in components:

                file_path = input_dir / component / pair

                if not file_path.is_file():
                    continue

                try:
                    df = pd.read_csv(
                        file_path,
                        dtype={"Date": str}
                    )

                except (OSError, pd.errors.EmptyDataError) as e:
                    print(
                        f"Warning: Cannot read {file_path}: {e}"
                    )
                    continue

                required_columns = [
                    "Date",
                    "dvv_M",
                    "dvv_M0"
                ]

                missing_columns = [
                    column
                    for column in required_columns
                    if column not in df.columns
                ]

                if missing_columns:
                    print(
                        f"Warning: Missing columns "
                        f"{missing_columns} in {file_path}"
                    )
                    continue

                df = df[
                    required_columns
                ].copy()

                # Convert dv/v values to numeric
                df["dvv_M"] = pd.to_numeric(
                    df["dvv_M"],
                    errors="coerce"
                )

                df["dvv_M0"] = pd.to_numeric(
                    df["dvv_M0"],
                    errors="coerce"
                )

                # Replace infinite values with NaN
                df[["dvv_M", "dvv_M0"]] = (
                    df[["dvv_M", "dvv_M0"]]
                    .replace([np.inf, -np.inf], np.nan)
                )

                df["Component"] = component

                dfs.append(df)

            if not dfs:
                print(
                    f"Warning: No valid data for {pair}"
                )
                continue

            # ------------------------------------------------
            # Combine all components
            # ------------------------------------------------

            df_all = pd.concat(
                dfs,
                ignore_index=True
            )

            # ------------------------------------------------
            # Calculate average dv/v
            # ------------------------------------------------

            df_avg = (
                df_all
                .groupby("Date", as_index=False)
                .agg(
                    dvv_M=("dvv_M", "mean"),
                    dvv_M0=("dvv_M0", "mean"),
                    n_M=("dvv_M", "count"),
                    n_M0=("dvv_M0", "count")
                )
            )

            df_avg = df_avg.sort_values(
                "Date"
            )

            # ------------------------------------------------
            # Save averaged dv/v
            # ------------------------------------------------

            output_file = output_dir / pair

            df_avg.to_csv(
                output_file,
                index=False
            )

            # =================================================
            # 8. Plot dvv_M and dvv_M0
            # =================================================

            fig, axes = plt.subplots(
                2, 1,
                figsize=FIGSIZE,
                dpi=DPI,
                sharex=True
            )

            dates_avg = pd.to_datetime(
                df_avg["Date"],
                format="%Y%j",
                errors="coerce"
            )

            for ax, column in zip(
                axes,
                ["dvv_M", "dvv_M0"]
            ):

                # --------------------------------------------
                # Individual components
                # --------------------------------------------

                for component in components:

                    df_comp = df_all[
                        df_all["Component"] == component
                    ]

                    if df_comp.empty:
                        continue

                    dates = pd.to_datetime(
                        df_comp["Date"],
                        format="%Y%j",
                        errors="coerce"
                    )

                    ax.scatter(
                        dates,
                        df_comp[column] * 100,
                        s=3,
                        alpha=0.5,
                        label=component
                    )

                # --------------------------------------------
                # Averaged dv/v
                # --------------------------------------------

                ax.scatter(
                    dates_avg,
                    df_avg[column] * 100,
                    s=8,
                    color="black",
                    alpha=1.0,
                    label="Average",
                    zorder=10
                )

                ax.set_ylabel(
                    f"{column} (%)"
                )

                ax.legend(
                    ncol=5,
                    fontsize=9
                )

                ax.grid(
                    alpha=0.3
                )

            axes[-1].set_xlabel(
                "Date"
            )

            fig.suptitle(
                f"Filter {filter_id} | "
                f"{input_name} | "
                f"{Path(pair).stem}"
            )

            fig.tight_layout()

            # ------------------------------------------------
            # Save PNG
            # ------------------------------------------------

            img_file = img_dir / (
                f"{Path(pair).stem}.png"
            )

            fig.savefig(
                img_file,
                dpi=DPI,
                bbox_inches="tight"
            )

            plt.close(fig)

            # ------------------------------------------------
            # Progress
            # ------------------------------------------------

            print(
                f"[Filter {filter_id}] "
                f"[{input_name}] "
                f"[{i}/{len(station_pairs)}] "
                f"Saved: {pair}"
            )

        print(
            f"\nFilter {filter_id} | "
            f"{input_name} completed!"
        )

        print(
            f"Averaged dv/v: {output_dir}"
        )

        print(
            f"Figures: {img_dir}"
        )

    print(
        f"\nAll input folders completed "
        f"for filter {filter_id}!"
    )

# ============================================================
# 9. Finished
# ============================================================

print("\n" + "=" * 60)
print("All filters and input folders processed successfully!")
print("=" * 60)
