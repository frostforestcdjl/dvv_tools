import os
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
import argparse

plot_case_lst = ['M', 'M0']

# --- Command-line arguments ---
parser = argparse.ArgumentParser(description="Plot dv/v time series")

parser.add_argument(
    "--moving_average",
    type=int,
    required=True,
    help="Moving average window in days"
)

args = parser.parse_args()

# --- Parameters ---
project_path = '.'
study_area = 'Parkfield_b2008'
moving_average = args.moving_average


def scan_files(project_path):
    files_set = set()
    pairs_set = set()

    dvv_path = os.path.join(project_path, "DVV")

    for filter_id in os.listdir(dvv_path):
        filter_path = os.path.join(dvv_path, filter_id)

        if filter_id.startswith(".") or not os.path.isdir(filter_path):
            continue

        for stack_days in os.listdir(filter_path):
            stack_path = os.path.join(filter_path, stack_days)

            if stack_days.startswith(".") or not os.path.isdir(stack_path):
                continue

            for component in os.listdir(stack_path):
                component_path = os.path.join(stack_path, component)

                if component.startswith(".") or not os.path.isdir(component_path):
                    continue

                files = [
                    f for f in os.listdir(component_path)
                    if f.endswith(".txt") and not f.startswith(".")
                ]

                # Collect full file paths
                files_set.update(
                    os.path.join(component_path, f) for f in files
                )

                # Collect unique station pairs
                pairs_set.update(
                    os.path.splitext(f)[0] for f in files
                )

    files_list = sorted(files_set)
    pair_list = sorted(pairs_set)

    print(f"{len(files_list)} files found.")
    print(f"{len(pair_list)} unique station pairs found.")

    return files_list, pair_list

def load_msnoise_DVV(files_list, moving_average=30):

    required_cols = ["Date", "dvv_M", "dvv_M0"]

    df_list = []

    for file in files_list:

        try:
            df = pd.read_csv(file)

        except (UnicodeDecodeError, pd.errors.ParserError) as e:
            print(f"Error reading {file}: {e}")
            continue

        if not all(col in df.columns for col in required_cols):
            print(f"Missing columns in {file}: {df.columns.tolist()}")
            continue

        if df.empty:
            print(f"No data in {file}")
            continue

        # Select required columns
        df = df[required_cols].copy()
        df["Pair"] = os.path.splitext(os.path.basename(file))[0]

        # Convert YYYYJJJ to datetime
        df["Date"] = pd.to_datetime(
            df["Date"].astype(str),
            format="%Y%j",
            errors="coerce"
        )

        # Convert dv/v to percentage
        df["dvv_M"] = pd.to_numeric(
            df["dvv_M"], errors="coerce"
        ) * 100

        df["dvv_M0"] = pd.to_numeric(
            df["dvv_M0"], errors="coerce"
        ) * 100

        df = df.dropna(subset=["Date"])

        df_list.append(df)

    if not df_list:
        print("No valid DVV data found.")
        return None

    # Combine all files
    df_all = pd.concat(df_list, ignore_index=True)

    # Step 1: Average components/files within each station pair
    df_pair_avg = (
        df_all.groupby(["Date", "Pair"])[["dvv_M", "dvv_M0"]]
        .mean()
    )

    # Step 2: Average station pairs equally
    df_avg = (
        df_pair_avg.groupby("Date")
        .mean()
        .sort_index()
    )

    # 30-day moving average
    df_avg["M_smooth"] = (
        df_avg["dvv_M"]
        .rolling(f"{moving_average}D", center=True, min_periods=1)
        .mean()
    )

    df_avg["M0_smooth"] = (
        df_avg["dvv_M0"]
        .rolling(f"{moving_average}D", center=True, min_periods=1)
        .mean()
    )

    date_lst = df_avg.index.to_numpy()

    M_lst = df_avg["dvv_M"].to_numpy()
    M0_lst = df_avg["dvv_M0"].to_numpy()

    M_lst_smooth = df_avg["M_smooth"].to_numpy()
    M0_lst_smooth = df_avg["M0_smooth"].to_numpy()

    return date_lst, M_lst, M0_lst, M_lst_smooth, M0_lst_smooth

def plot_dvv(study_area, plot_case, station_pair, date_lst,
             M_lst, M0_lst, M_lst_smooth, M0_lst_smooth,
             moving_average, reverse_y=False, save_path=''):

    fig, ax = plt.subplots(figsize=(12, 4))

    if plot_case == 'M':
        ax.scatter(
            date_lst, M_lst,
            color='orange', s=3, label='M'
        )

        if moving_average > 1:
            ax.scatter(
                date_lst, M_lst_smooth,
                color='r', s=3,
                label=f'M ({moving_average}-day moving average)'
            )
    elif plot_case == 'M0':
        ax.scatter(
            date_lst, M0_lst,
            color='grey', s=3, label='M0'
        )

        if moving_average > 1:
            ax.scatter(
                date_lst, M0_lst_smooth,
                color='k', s=3,
                label=f'M0 ({moving_average}-day moving average)'
            )
    else:
        raise ValueError("plot_case must be 'M' or 'M0'")

    ax.set_xlabel('Date')
    ax.set_ylabel('dv/v (%)')
    ax.set_title(f'dv/v at {study_area} (Station Pair: {station_pair})')

    ax.set_xlim(date_lst[0], date_lst[-1])

    if reverse_y:
        ax.invert_yaxis()

    ax.legend()

    plt.tight_layout()

    if save_path:
        save_path = f"{save_path}/{moving_average}D"
        os.makedirs(save_path, exist_ok=True)

        filename = os.path.join(
            save_path,
            f'{station_pair}_{plot_case}_{moving_average}d.png'
        )

        fig.savefig(filename, dpi=150, bbox_inches='tight')

    else:
        plt.show()

    plt.close(fig)

files_list, pair_list = scan_files(project_path)

save_path = "img"

# ========================================================
# Plot individual station pairs
# ========================================================

for pair in pair_list:

    print(f"\nProcessing station pair: {pair}")

    files_list_target_pair = [
        f for f in files_list
        if os.path.splitext(os.path.basename(f))[0] == pair
    ]

    print(f"Found {len(files_list_target_pair)} files")

    result = load_msnoise_DVV(
        files_list_target_pair,
        moving_average=moving_average
    )

    if result is None:
        continue

    date_lst, M_lst, M0_lst, M_lst_smooth, M0_lst_smooth = result

    for plot_case in plot_case_lst:

        plot_dvv(
            study_area,
            plot_case,
            pair,
            date_lst,
            M_lst,
            M0_lst,
            M_lst_smooth,
            M0_lst_smooth,
            moving_average,
            reverse_y=True,
            save_path=save_path
        )


# ========================================================
# Plot average dv/v across all station pairs
# ========================================================

print("\nProcessing all station pairs")

result = load_msnoise_DVV(
    files_list,
    moving_average=moving_average
)

if result is not None:

    date_lst, M_lst, M0_lst, M_lst_smooth, M0_lst_smooth = result

    for plot_case in plot_case_lst:

        plot_dvv(
            study_area,
            plot_case,
            "ALL",
            date_lst,
            M_lst,
            M0_lst,
            M_lst_smooth,
            M0_lst_smooth,
            moving_average,
            reverse_y=True,
            save_path=save_path
        )
