import os
import numpy as np
import pandas as pd

from matplotlib import pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable

import argparse
import ast

import matplotlib.dates as mdates

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
parser.add_argument(
    "--climate_file",
    type=str,
    default=None,
    help="Path to the PRISM precipitation and temperature TXT file. "
         "If omitted, rainfall and temperature are not plotted."
)
parser.add_argument(
    "--regression",
    action="store_true",
    help="Add a linear regression line to the dv/v panel"
)
parser.add_argument(
    "--filters",
    nargs="+",
    default=None,
    help="Filter folders in DVV to plot (e.g., --filters 01 03). Default: all."
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


# ========================================================
# Scan DVV folders
# ========================================================

def list_filters(project_path):
    dvv_path = os.path.join(project_path, "DVV")
    return sorted(
        d for d in os.listdir(dvv_path)
        if not d.startswith(".") and os.path.isdir(os.path.join(dvv_path, d))
    )


def scan_files(project_path, filter_id):
    files_set = set()
    pairs_set = set()

    filter_path = os.path.join(project_path, "DVV", filter_id)

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
            files_set.update(os.path.join(component_path, f) for f in files)
            pairs_set.update(os.path.splitext(f)[0] for f in files)

    files_list = sorted(files_set)
    pair_list = sorted(pairs_set)

    print(f"[filter {filter_id}] {len(files_list)} files found.")
    print(f"[filter {filter_id}] {len(pair_list)} unique station pairs found.")

    return files_list, pair_list


# ========================================================
# Shorten the pair label for plot titles
# ========================================================

def _short_number(text):
    """'30.682482182519845' -> '30.68', '30.0' -> '30' (at most 2 decimals)."""
    return f"{float(text):.2f}".rstrip("0").rstrip(".")


def format_pair_label(station_pair):
    """'nw1.st1_nw2.st2_dt1_dt2' -> same name with dt1, dt2 rounded to at most 2 decimals.

    Labels without two numeric lag times at the end (e.g. 'ALL') are returned unchanged.
    """
    parts = station_pair.rsplit("_", 2)
    if len(parts) != 3:
        return station_pair
    name, dt1, dt2 = parts
    try:
        return f"{name}_{_short_number(dt1)}_{_short_number(dt2)}"
    except ValueError:
        return station_pair


# ========================================================
# Load DVV files
# ========================================================

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

    # Moving average
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


# ========================================================
# Load PRISM climate data
# ========================================================

def load_prism_climate(file_path):
    """
    Read PRISM daily time-series TXT data.

    Expected columns:
        Date,ppt (mm),tmean (degrees C)

    Automatically skips PRISM metadata lines.
    """

    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"PRISM file not found: {file_path}"
        )

    # Locate the CSV header following the metadata
    with open(file_path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    header_line = None

    for i, line in enumerate(lines):
        if line.strip().startswith("Date,"):
            header_line = i
            break

    if header_line is None:
        raise ValueError(
            "Cannot find the PRISM CSV header."
        )

    # Read data after metadata
    df = pd.read_csv(
        file_path,
        skiprows=header_line,
        na_values=["NA", "NaN", "-9999", "-9999.0"]
    )

    df.columns = df.columns.str.strip()

    required_columns = [
        "Date",
        "ppt (mm)",
        "tmean (degrees C)"
    ]

    missing = [
        c for c in required_columns
        if c not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing PRISM columns: {missing}"
        )

    df["Date"] = pd.to_datetime(
        df["Date"],
        format="%Y-%m-%d",
        errors="coerce"
    )

    df["ppt (mm)"] = pd.to_numeric(
        df["ppt (mm)"],
        errors="coerce"
    )

    df["tmean (degrees C)"] = pd.to_numeric(
        df["tmean (degrees C)"],
        errors="coerce"
    )

    df = (
        df.dropna(subset=["Date"])
        .sort_values("Date")
        .drop_duplicates(subset=["Date"])
        .set_index("Date")
    )

    print("\nPRISM climate data loaded")
    print(f"First date: {df.index.min()}")
    print(f"Last date:  {df.index.max()}")
    print(f"Total records: {len(df)}")
    print(f"Valid precipitation: {df['ppt (mm)'].count()}")
    print(f"Valid temperature:   {df['tmean (degrees C)'].count()}")

    return df


# ========================================================
# Plot
# ========================================================

def plot_dvv(
    plot_case,
    station_pair,
    date_lst,
    M_lst,
    M0_lst,
    M_lst_smooth,
    M0_lst_smooth,
    moving_average,
    day_adjust,
    event_pack=(),
    reverse_y=False,
    save_path='',
    climate_df=None,
    filter_id='',
    regression=False
):

    # ========================================================
    # Date adjustment
    # ========================================================

    date_lst = pd.to_datetime(
        date_lst + np.timedelta64(day_adjust, "D")
    )

    # ========================================================
    # Figure layout: 3 panels with climate data, 1 panel without
    # ========================================================

    has_climate = climate_df is not None

    if has_climate:
        fig, axes = plt.subplots(
            3,
            1,
            figsize=(12, 8),
            sharex=True,
            gridspec_kw={
                "height_ratios": [3, 1.3, 1.3],
                "hspace": 0.08
            }
        )
        ax, ax_rain, ax_temp = axes
    else:
        fig, ax = plt.subplots(figsize=(12, 4))
        axes = [ax]

    ax_bottom = axes[-1]

    # ========================================================
    # Panel 1: dv/v scatter plot
    # ========================================================

    if plot_case == 'M':

        y_data = np.asarray(M_lst, dtype=float)

        ax.scatter(
            date_lst,
            y_data,
            color='orange',
            s=3,
            label='M'
        )

        if moving_average > 1:

            y_smooth = np.asarray(
                M_lst_smooth,
                dtype=float
            )

            ax.scatter(
                date_lst,
                y_smooth,
                color='r',
                s=3,
                label=(
                    f'M ({moving_average}-day '
                    f'moving average)'
                )
            )

    elif plot_case == 'M0':

        y_data = np.asarray(M0_lst, dtype=float)

        ax.scatter(
            date_lst,
            y_data,
            color='grey',
            s=3,
            label='M0'
        )

        if moving_average > 1:

            y_smooth = np.asarray(
                M0_lst_smooth,
                dtype=float
            )

            ax.scatter(
                date_lst,
                y_smooth,
                color='k',
                s=3,
                label=(
                    f'M0 ({moving_average}-day '
                    f'moving average)'
                )
            )

    else:
        raise ValueError(
            "plot_case must be 'M' or 'M0'"
        )

    # ========================================================
    # Linear regression (only with --regression)
    # ========================================================

    if regression:

        x_data = np.asarray(
            mdates.date2num(date_lst),
            dtype=float
        )

        valid = (
            np.isfinite(x_data)
            & np.isfinite(y_data)
        )

        if np.count_nonzero(valid) >= 2:

            x_valid = x_data[valid]
            y_valid = y_data[valid]

            if np.ptp(x_valid) > 0:

                x_reference = x_valid.min()
                x_relative = x_valid - x_reference

                slope, intercept = np.polyfit(
                    x_relative,
                    y_valid,
                    deg=1
                )

                x_fit = np.linspace(
                    x_valid.min(),
                    x_valid.max(),
                    500
                )

                y_fit = (
                    slope * (x_fit - x_reference)
                    + intercept
                )

                slope_year = slope * 365.25

                ax.plot(
                    mdates.num2date(x_fit),
                    y_fit,
                    color='blue',
                    linewidth=2,
                    linestyle='--',
                    label=(
                        f'Linear regression '
                        f'({slope_year:+.4f} %/year)'
                    ),
                    zorder=5
                )

                print(
                    f"{station_pair} ({plot_case}): "
                    f"Slope = {slope_year:+.6f} %/year"
                )

    # ========================================================
    # Y-axis limits based on original scatter data
    # ========================================================

    y_all = y_data.copy()

    if moving_average > 1:

        y_all = np.concatenate([
            y_all,
            y_smooth
        ])

    y_all = y_all[np.isfinite(y_all)]

    if y_all.size > 0:

        ymin = np.min(y_all)
        ymax = np.max(y_all)

        yrange = ymax - ymin

        margin = (
            0.05 * yrange
            if yrange > 0
            else 0.01
        )

        ax.set_ylim(
            ymin - margin,
            ymax + margin
        )

    # ========================================================
    # Earthquake markers
    # ========================================================

    if event_pack:

        event_time, event_distance, event_place = event_pack

        cmap = plt.get_cmap("gist_rainbow")
        norm = Normalize(vmin=0, vmax=500)

        for time, distance, place in zip(
            event_time,
            event_distance,
            event_place
        ):

            if not np.isfinite(distance):
                continue

            ax.axvline(
                time,
                color=cmap(norm(distance)),
                linestyle="--",
                linewidth=1,
                alpha=0.7,
                zorder=1
            )

        sm = ScalarMappable(
            norm=norm,
            cmap=cmap
        )

        sm.set_array([])

        # Attach colorbar to the full axes group
        # so the panels remain aligned
        cbar = fig.colorbar(
            sm,
            ax=axes,
            pad=0.02,
            fraction=0.025,
            aspect=35
        )

        cbar.set_label(
            "Earthquake distance (km)"
        )

    # ========================================================
    # Panel 2 and 3: PRISM climate data (only with --climate_file)
    # ========================================================

    if has_climate:

        # Restrict climate data to dv/v time range
        start_date = date_lst.min()
        end_date = date_lst.max()

        climate_plot = climate_df.loc[
            (climate_df.index >= start_date)
            & (climate_df.index <= end_date)
        ]

        if climate_plot.empty:
            print(
                f"[WARNING] No PRISM data within "
                f"the dv/v time range for {station_pair}"
            )

        # ----------------------------------------------------
        # Panel 2: Daily precipitation + moving average
        # ----------------------------------------------------

        ax_rain.plot(
            climate_plot.index,
            climate_plot["ppt (mm)"],
            color="royalblue",
            linewidth=0.5,
            alpha=0.5,
            label="Daily precipitation"
        )

        if CLIMATE_SMOOTH_DAYS > 1:
            ax_rain.plot(
                climate_plot.index,
                climate_plot["ppt_smooth"],
                color="blue",
                linewidth=1.5,
                label=f"{CLIMATE_SMOOTH_DAYS}-day moving average"
            )

        ax_rain.set_ylabel("Precipitation\n(mm/day)")
        ax_rain.set_ylim(bottom=0)
        ax_rain.grid(axis="y", alpha=0.25)
        ax_rain.legend(loc="upper right", fontsize=8)

        # ----------------------------------------------------
        # Panel 3: Daily temperature + smoothed temperature
        # ----------------------------------------------------

        ax_temp.plot(
            climate_plot.index,
            climate_plot["tmean (degrees C)"],
            color="lightcoral",
            linewidth=0.5,
            alpha=0.4,
            label="Daily temperature"
        )

        ax_temp.plot(
            climate_plot.index,
            climate_plot["temp_smooth"],
            color="purple",
            linewidth=1.5,
            label=f"{CLIMATE_SMOOTH_DAYS}-day moving average"
        )

        ax_temp.set_ylabel("Temperature\n(°C)")
        ax_temp.grid(axis="y", alpha=0.25)
        ax_temp.legend(loc="upper right", fontsize=8)

    # ========================================================
    # Axis formatting
    # ========================================================

    ax.set_ylabel("dv/v (%)")

    ax.set_title(
        "dv/v from BK network around Berkeley Campus "
        f"(Station Pair: {format_pair_label(station_pair)}, filter {filter_id})"
    )

    # Use identical date limits for all panels
    ax.set_xlim(
        date_lst.min(),
        date_lst.max()
    )

    if reverse_y:
        ax.invert_yaxis()

    ax.legend(
        loc="best",
        fontsize=9
    )

    ax_bottom.set_xlabel("Date")

    ax_bottom.xaxis.set_major_locator(
        mdates.AutoDateLocator()
    )

    ax_bottom.xaxis.set_major_formatter(
        mdates.ConciseDateFormatter(
            ax_bottom.xaxis.get_major_locator()
        )
    )

    for axis in axes:
        axis.tick_params(
            axis="both",
            labelsize=9
        )

    # ========================================================
    # Save figure
    # ========================================================

    if save_path:

        save_path = os.path.join(
            save_path,
            f"{moving_average}D"
        )

        os.makedirs(
            save_path,
            exist_ok=True
        )

        filename = os.path.join(
            save_path,
            (
                f"{station_pair}_{plot_case}_"
                f"{moving_average}d.png"
            )
        )

        fig.savefig(
            filename,
            dpi=150,
            bbox_inches="tight"
        )

        print(f"Saved: {filename}")

    else:
        plt.show()

    plt.close(fig)


# ========================================================
# Load and smooth PRISM precipitation and temperature
# (only when --climate_file is given)
# ========================================================

CLIMATE_SMOOTH_DAYS = 1

if args.climate_file:
    climate_df = load_prism_climate(args.climate_file)

    climate_df["ppt_smooth"] = (
        climate_df["ppt (mm)"]
        .rolling(f"{CLIMATE_SMOOTH_DAYS}D", center=True, min_periods=1)
        .mean()
    )

    climate_df["temp_smooth"] = (
        climate_df["tmean (degrees C)"]
        .rolling(f"{CLIMATE_SMOOTH_DAYS}D", center=True, min_periods=1)
        .mean()
    )

    # Optional: rainfall accumulated over the preceding 30 days
    climate_df["ppt_30d_sum"] = (
        climate_df["ppt (mm)"]
        .rolling("30D", min_periods=1)
        .sum()
    )
else:
    climate_df = None
    print("No climate file given: rainfall and temperature panels are skipped.")


# ========================================================
# Plot one filter (frequency band)
# ========================================================

def run_filter(filter_id):
    files_list, pair_list = scan_files(project_path, filter_id)
    if not files_list:
        return

    save_path = os.path.join(project_path, "img", filter_id)

    # ---------------- individual station pairs ----------------
    for pair in pair_list:
        print(f"\n[filter {filter_id}] Processing station pair: {pair}")

        files_list_target_pair = [
            f for f in files_list
            if os.path.splitext(os.path.basename(f))[0] == pair
        ]
        print(f"Found {len(files_list_target_pair)} files")

        result = load_msnoise_DVV(files_list_target_pair, moving_average=moving_average)
        if result is None:
            continue

        date_lst, M_lst, M0_lst, M_lst_smooth, M0_lst_smooth, day_adjust = result
        for plot_case in plot_case_lst:
            plot_dvv(plot_case, pair, date_lst, M_lst, M0_lst, M_lst_smooth, M0_lst_smooth,
                     moving_average, day_adjust, event_pack,
                     reverse_y=reverse_y, save_path=save_path,
                     climate_df=climate_df, filter_id=filter_id,
                     regression=args.regression)

    # ---------------- average of all pairs in this band ----------------
    if exclude_stations_file:
        with open(exclude_stations_file, "r") as f:
            exclude_stations_list = [line.strip() for line in f if line.strip()]
        print(f"Exclude stations for regional dv/v: {exclude_stations_list}")
        files_list_target_pair = [
            f for f in files_list
            if all(station not in os.path.basename(f) for station in exclude_stations_list)
        ]
    else:
        files_list_target_pair = files_list

    print(f"\n[filter {filter_id}] Processing all {len(files_list_target_pair)} files")

    result = load_msnoise_DVV(files_list_target_pair, moving_average=moving_average)
    if result is not None:
        date_lst, M_lst, M0_lst, M_lst_smooth, M0_lst_smooth, day_adjust = result
        for plot_case in plot_case_lst:
            plot_dvv(plot_case, "ALL", date_lst, M_lst, M0_lst, M_lst_smooth, M0_lst_smooth,
                     moving_average, day_adjust, event_pack,
                     reverse_y=reverse_y, save_path=save_path,
                     climate_df=climate_df, filter_id=filter_id,
                     regression=args.regression)


# ========================================================
# Main
# ========================================================

filters = args.filters if args.filters else list_filters(project_path)
print(f"Filters to plot: {filters}")

for filter_id in filters:
    run_filter(filter_id)
