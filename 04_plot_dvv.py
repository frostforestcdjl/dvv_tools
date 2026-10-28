import os
import numpy as np
import pandas as pd

from matplotlib import pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable

import argparse
import ast

plot_case_lst = ['M', 'M0']

# --- Command-line arguments ---
parser = argparse.ArgumentParser(description="Plot dv/v time series")

parser.add_argument(
    "--project_path",
    required=True,
    default=".",
    help="The path of the project containing DVV folder"
)
parser.add_argument(
    "--moving_average",
    type=int,
    required=True,
    help="Moving average window in days"
)
parser.add_argument(
    "--event_list",
    default="event_list.txt",
    help="Path to event_list.txt (default: event_list.txt)"
)
parser.add_argument(
    "--reverse_y",
    default=False,
    help="Reverse y-axis or not"
)
parser.add_argument(
    "--event_groups",
    type=int,
    nargs="+",
    default=None,
    help="Event groups to plot (e.g., --event_groups 17 20 26). "
         "Default: all groups."
)
parser.add_argument(
    "--exclude_stations",
    default=None,
    help="The station list excluded in the summation plot."
)


args = parser.parse_args()

# --- Parameters ---
project_path = args.project_path
moving_average = args.moving_average
reverse_y = args.reverse_y
exclude_stations_file = args.exclude_stations

# ========================================================
# Read earthquake configuration
# ========================================================

def read_event_list(config_path):
    config_path = os.path.abspath(config_path)
    with open(config_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=config_path)

    values = {}

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(node, ast.Assign) and isinstance(target, ast.Name):
                    if target.id in ["event_file", "center_lat", "center_long"]:
                        values[target.id] = ast.literal_eval(node.value)

    required = {"event_file", "center_lat", "center_long"}

    missing = required - values.keys()

    if missing:
        raise ValueError(f"Missing parameters in {config_path}: {sorted(missing)}")

    event_file = os.path.expanduser(str(values["event_file"]))

    if not os.path.isabs(event_file):
        event_file = os.path.join(os.path.dirname(config_path), event_file)

    center_lat = float(values["center_lat"])
    center_long = float(values["center_long"])

    return event_file, center_lat, center_long


# ========================================================
# Load earthquake catalog and calculate distances
# ========================================================

def load_event_catalog(event_file, center_lat, center_long, groups=None):

    # Read earthquake catalog
    events = pd.read_csv(event_file)

    # Earthquake coordinates
    lat = np.deg2rad(pd.to_numeric(events["latitude"], errors="coerce"))
    lon = np.deg2rad(pd.to_numeric(events["longitude"], errors="coerce"))

    # Reference coordinates
    lat0 = np.deg2rad(center_lat)
    lon0 = np.deg2rad(center_long)

    # Haversine formula
    dlat = lat - lat0
    dlon = lon - lon0

    a = (
        np.sin(dlat / 2)**2
        + np.cos(lat0) * np.cos(lat) * np.sin(dlon / 2)**2
    )

    R = 6371.0  # Earth radius in km

    distance = 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))

    # Add distance to catalog
    events["distance_km"] = distance

    # Filter events by group
    if groups is not None:
        events = events[events["group"].isin(groups)]

    # Extract information
    event_time = pd.to_datetime(events["time"]).to_numpy()
    event_distance = events["distance_km"].to_numpy()
    event_place = events["place"].to_numpy()

    return event_time, event_distance, event_place


# ========================================================
# Initialize earthquake catalog
# ========================================================

event_file, center_lat, center_long = read_event_list(args.event_list)
event_pack = load_event_catalog(event_file, center_lat, center_long, groups=args.event_groups)

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
        file_seg_list = file.split('/')
        for file_seg in file_seg_list:
            if 'DAYS' in file_seg:
                file_seg_tmp = file_seg
                if 'pm' in file_seg_tmp:
                    file_seg_tmp = file_seg_tmp.replace('pm', '').replace('_DAYS', '')
                    day_adjust = int(file_seg_tmp)
                else:
                    file_seg_tmp = file_seg_tmp.replace('_DAYS', '')
                    day_adjust = int(file_seg_tmp)//2
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

    return date_lst, M_lst, M0_lst, M_lst_smooth, M0_lst_smooth, day_adjust

def plot_dvv(plot_case, station_pair, date_lst,
             M_lst, M0_lst, M_lst_smooth, M0_lst_smooth,
             moving_average, day_adjust, event_pack=(), reverse_y=False, save_path=''):

    date_lst = date_lst + np.timedelta64(day_adjust, "D")
    # fig, ax = plt.subplots(figsize=(6, 4))
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

    if event_pack:
        event_time, event_distance, event_place = event_pack

        # Distance color mapping
        cmap = plt.get_cmap("gist_rainbow")
        norm = Normalize(vmin=0, vmax=500)

        for time, distance, place in zip(event_time, event_distance, event_place):

            if not np.isfinite(distance):
                continue

            ax.axvline(time, color=cmap(norm(distance)), linestyle="--", linewidth=1, alpha=0.7, zorder=1)

        # Distance colorbar
        sm = ScalarMappable(
            norm=norm,
            cmap=cmap
        )
        sm.set_array([])

        fig.colorbar(sm, ax=ax, label="Earthquake distance (km)", pad=0.02)

    ax.set_xlabel('Date')
    ax.set_ylabel('dv/v (%)')
    ax.set_title(f'dv/v at {place} (Station Pair: {station_pair})')

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

save_path = os.path.join(project_path, "img")

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

    date_lst, M_lst, M0_lst, M_lst_smooth, M0_lst_smooth, day_adjust = result

    for plot_case in plot_case_lst:

        plot_dvv(
            plot_case,
            pair,
            date_lst,
            M_lst,
            M0_lst,
            M_lst_smooth,
            M0_lst_smooth,
            moving_average,
            day_adjust,
            event_pack,
            reverse_y=reverse_y,
            save_path=save_path
        )


# ========================================================
# Plot average dv/v across all station pairs
# ========================================================
if exclude_stations_file:
    with open(exclude_stations_file, "r") as f:
        exclude_stations_list = [line.strip() for line in f if line.strip()]
    print(f"Exclude stations for regional dv/v: {exclude_stations_list}")
    files_list_target_pair = [
        f for f in files_list
        if all(station not in f for station in exclude_stations_list)
    ]
else:
    files_list_target_pair = files_list

print(f"\nProcessing all station pairs within {files_list_target_pair}")

result = load_msnoise_DVV(
    files_list_target_pair,
    moving_average=moving_average
)


if result is not None:

    date_lst, M_lst, M0_lst, M_lst_smooth, M0_lst_smooth, day_adjust = result

    for plot_case in plot_case_lst:

        plot_dvv(
            plot_case,
            "ALL",
            date_lst,
            M_lst,
            M0_lst,
            M_lst_smooth,
            M0_lst_smooth,
            moving_average,
            day_adjust,
            event_pack,
            reverse_y=reverse_y,
            save_path=save_path
        )
