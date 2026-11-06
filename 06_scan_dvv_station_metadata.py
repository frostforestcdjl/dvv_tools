#!/usr/bin/env python3
"""
scan_dvv_station_metadata.py

Scan CCTorch DVV station-pair files and generate
station metadata, geometry and MWCS lag-time windows.

Expected structure:

    PROJECT/
        scan_dvv_station_metadata.py
        DVV/
            filter_id/
                stacking_day/
                    component/
                        NET1.STA1_NET2.STA2.txt
        station_metadata/  (automatically created)

Dependencies:
    numpy, pandas, matplotlib, pyproj, obspy

Examples:
    python scan_dvv_station_metadata.py

    python scan_dvv_station_metadata.py --date 2024-09-01

    python scan_dvv_station_metadata.py \
        --filter-fmin 01=0.1 02=0.2 03=0.5

    python scan_dvv_station_metadata.py --skip-fdsn
"""

from pathlib import Path
from collections import defaultdict
from itertools import combinations

import argparse
import csv
import re
import sys

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pyproj import CRS, Transformer, Geod
from obspy import UTCDateTime
from obspy.clients.fdsn import Client


# ============================================================
# 1. Configuration
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent

DVV_DIR = SCRIPT_DIR / "DVV"
OUTPUT_DIR = SCRIPT_DIR / "station_metadata"

# Station-pair filename:
# NET1.STA1_NET2.STA2.txt
PAIR_PATTERN = re.compile(
    r"^([A-Za-z0-9]+)\.([A-Za-z0-9-]+)_"
    r"([A-Za-z0-9]+)\.([A-Za-z0-9-]+)\.txt$",
    re.IGNORECASE
)

# ------------------------------------------------------------
# FDSN configuration
# ------------------------------------------------------------

FDSN_DATA_CENTERS = {
    "SCEDC": "https://service.scedc.caltech.edu",
    "NCEDC": "https://service.ncedc.org",
    "EARTHSCOPE": "EARTHSCOPE",
}

NETWORK_DATA_CENTERS = {
    "CI": ["SCEDC", "EARTHSCOPE", "NCEDC"],
    "BK": ["NCEDC", "EARTHSCOPE", "SCEDC"],
    "NC": ["NCEDC", "EARTHSCOPE", "SCEDC"],
    "BP": ["NCEDC", "EARTHSCOPE", "SCEDC"],
}

DEFAULT_DATA_CENTERS = [
    "EARTHSCOPE",
    "SCEDC",
    "NCEDC",
]

FDSN_TIMEOUT = 30
BATCH_SIZE = 20

# ------------------------------------------------------------
# MWCS window configuration
# ------------------------------------------------------------

# Add other filter IDs and their actual minimum frequencies.
FILTER_FMIN = {
    "01": 0.1,
}

N_PERIODS = 3.0
WINDOW_VELOCITY = 1.0    # km/s
WINDOW_WIDTH = 40.0      # seconds

# Only for reporting model direct arrival times.
# Does not affect the MWCS window definition.
KERNEL_VELOCITY = 2.0    # km/s

# ------------------------------------------------------------
# Geometry visualization
# ------------------------------------------------------------

FIG_DPI = 200
LABEL_STATIONS = True


# ============================================================
# 2. General utilities
# ============================================================

def make_batches(items, batch_size):
    for start in range(0, len(items), batch_size):
        yield items[start:start + batch_size]


def normalize_station_id(network, station):
    return (
        f"{str(network).strip().upper()}."
        f"{str(station).strip().upper()}"
    )


def canonical_pair(a, b):
    return tuple(sorted((a, b)))


def join_sorted(items):
    return ",".join(sorted(items))


def save_csv(path, rows, columns):

    with path.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=columns
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(row)


def save_lines(path, lines):

    with path.open("w", encoding="utf-8") as f:

        for line in lines:
            f.write(f"{line}\n")


# ============================================================
# 3. Scan all DVV station-pair files
# ============================================================

def scan_dvv_directory(dvv_dir):

    if not dvv_dir.is_dir():
        raise FileNotFoundError(
            f"DVV directory not found: {dvv_dir}"
        )

    station_usage = defaultdict(lambda: {
        "file_count": 0,
        "filters": set(),
        "stacking_days": set(),
        "components": set(),
    })

    pair_usage = defaultdict(lambda: {
        "file_count": 0,
        "filters": set(),
        "stacking_days": set(),
        "components": set(),
    })

    # One record for every actual DVV TXT file.
    file_records = []

    invalid_files = []

    txt_files = sorted(dvv_dir.rglob("*.txt"))

    print("\nScanning DVV directory")
    print("=" * 70)
    print("Directory:", dvv_dir)

    for path in txt_files:

        if not path.is_file():
            continue

        # Ignore macOS resource-fork files.
        if path.name.startswith("._"):
            continue

        relative = path.relative_to(dvv_dir)
        parts = relative.parts

        # Expected depth:
        # filter_id / stacking_day / component / filename
        if len(parts) != 4:

            invalid_files.append(
                f"{relative} | unexpected directory depth"
            )
            continue

        filter_id, stacking_day, component, filename = parts

        match = PAIR_PATTERN.fullmatch(filename)

        if match is None:

            invalid_files.append(
                f"{relative} | invalid filename"
            )
            continue

        net1, sta1, net2, sta2 = match.groups()

        station1 = normalize_station_id(net1, sta1)
        station2 = normalize_station_id(net2, sta2)

        pair = canonical_pair(station1, station2)

        record = {
            "filter_id": filter_id,
            "stacking_day": stacking_day,
            "component": component,
            "station1": pair[0],
            "station2": pair[1],
            "is_autocorrelation": pair[0] == pair[1],
            "relative_path": str(relative),
        }

        file_records.append(record)

        # Track each station once per file.
        for station_id in {station1, station2}:

            usage = station_usage[station_id]

            usage["file_count"] += 1
            usage["filters"].add(filter_id)
            usage["stacking_days"].add(stacking_day)
            usage["components"].add(component)

        usage = pair_usage[pair]

        usage["file_count"] += 1
        usage["filters"].add(filter_id)
        usage["stacking_days"].add(stacking_day)
        usage["components"].add(component)

    stations = sorted(station_usage)
    pairs = sorted(pair_usage)

    filters = sorted({
        r["filter_id"] for r in file_records
    })

    stacking_days = sorted({
        r["stacking_day"] for r in file_records
    })

    components = sorted({
        r["component"] for r in file_records
    })

    print("Valid TXT files:", len(file_records))
    print("Invalid TXT files:", len(invalid_files))
    print("Unique stations:", len(stations))
    print("Unique station pairs:", len(pairs))
    print("Filters:", filters)
    print("Stacking days:", stacking_days)
    print("Components:", components)

    return {
        "stations": stations,
        "pairs": pairs,
        "file_records": file_records,
        "station_usage": station_usage,
        "pair_usage": pair_usage,
        "invalid_files": invalid_files,
        "filters": filters,
        "stacking_days": stacking_days,
        "components": components,
    }


# ============================================================
# 4. FDSN station metadata
# ============================================================

def epoch_timestamp(station):

    if station.start_date is None:
        return float("-inf")

    return float(station.start_date.timestamp)


def epoch_is_valid(station, query_time):

    if query_time is None:
        return True

    if (
        station.start_date is not None
        and station.start_date > query_time
    ):
        return False

    if (
        station.end_date is not None
        and station.end_date <= query_time
    ):
        return False

    return True


def station_to_record(network, station, provider):

    network = network.upper()
    code = station.code.upper()

    return {
        "network": network,
        "station": code,
        "station_id": f"{network}.{code}",
        "latitude": float(station.latitude),
        "longitude": float(station.longitude),
        "elevation_m": float(station.elevation),
        "start_date": (
            str(station.start_date)
            if station.start_date is not None
            else ""
        ),
        "end_date": (
            str(station.end_date)
            if station.end_date is not None
            else ""
        ),
        "provider": provider,
    }


def collect_inventory(
    inventory,
    requested,
    records,
    provider,
    query_time
):

    for network in inventory:

        for station in network:

            station_id = normalize_station_id(
                network.code,
                station.code
            )

            if station_id not in requested:
                continue

            if not epoch_is_valid(station, query_time):
                continue

            epoch = epoch_timestamp(station)

            if station_id in records:
                if epoch <= records[station_id]["epoch"]:
                    continue

            records[station_id] = {
                "epoch": epoch,
                "data": station_to_record(
                    network.code,
                    station,
                    provider
                )
            }


def retrieve_station_coordinates(
    station_ids,
    metadata_date=None,
    batch_size=BATCH_SIZE
):

    requested = set(station_ids)
    records = {}

    query_time = (
        UTCDateTime(metadata_date)
        if metadata_date is not None
        else None
    )

    query_kwargs = {
        "level": "station",
    }

    if query_time is not None:
        query_kwargs["starttime"] = query_time
        query_kwargs["endtime"] = query_time + 1

    groups = defaultdict(set)

    for station_id in requested:

        network, station = station_id.split(".", 1)
        groups[network].add(station)

    clients = {}
    unavailable = set()

    def get_client(provider):

        if provider in unavailable:
            return None

        if provider in clients:
            return clients[provider]

        try:

            client = Client(
                FDSN_DATA_CENTERS[provider],
                timeout=FDSN_TIMEOUT
            )

            clients[provider] = client
            return client

        except Exception as exc:

            print(
                f"Cannot initialize {provider}: {exc}"
            )

            unavailable.add(provider)
            return None

    for network, codes in sorted(groups.items()):

        providers = NETWORK_DATA_CENTERS.get(
            network,
            DEFAULT_DATA_CENTERS
        )

        print("\n" + "=" * 70)
        print(f"Network {network}")
        print("Providers:", providers)
        print("=" * 70)

        for provider in providers:

            missing_codes = sorted(
                code for code in codes
                if f"{network}.{code}" not in records
            )

            if not missing_codes:
                break

            client = get_client(provider)

            if client is None:
                continue

            print(
                f"\nQuerying {provider}: "
                f"{len(missing_codes)} stations"
            )

            for batch in make_batches(
                missing_codes,
                batch_size
            ):

                try:

                    inventory = client.get_stations(
                        network=network,
                        station=",".join(batch),
                        **query_kwargs
                    )

                    collect_inventory(
                        inventory,
                        requested,
                        records,
                        provider,
                        query_time
                    )

                except Exception as exc:

                    print(
                        f"Batch query failed: {exc}"
                    )

                    for code in batch:

                        station_id = f"{network}.{code}"

                        if station_id in records:
                            continue

                        try:

                            inventory = client.get_stations(
                                network=network,
                                station=code,
                                **query_kwargs
                            )

                            collect_inventory(
                                inventory,
                                requested,
                                records,
                                provider,
                                query_time
                            )

                        except Exception as sub_exc:

                            print(
                                f"Failed {station_id}: "
                                f"{sub_exc}"
                            )

            remaining = sum(
                f"{network}.{code}" not in records
                for code in codes
            )

            print(
                f"{provider}: "
                f"{remaining} stations remaining"
            )

    coordinates = [
        records[key]["data"]
        for key in sorted(records)
    ]

    missing = sorted(
        requested - set(records)
    )

    return coordinates, missing


# ============================================================
# 5. Geographic projection and station geometry
# ============================================================

def build_station_geometry(
    coordinates,
    pairs,
):

    if not coordinates:
        return None

    df = pd.DataFrame(coordinates)

    df = (
        df.drop_duplicates("station_id")
        .sort_values("station_id")
        .reset_index(drop=True)
    )

    # Projection origin: median station location.
    lat0 = float(df["latitude"].median())
    lon0 = float(df["longitude"].median())

    local_crs = CRS.from_proj4(
        f"+proj=aeqd "
        f"+lat_0={lat0} "
        f"+lon_0={lon0} "
        f"+datum=WGS84 "
        f"+units=m "
        f"+no_defs"
    )

    transformer = Transformer.from_crs(
        "EPSG:4326",
        local_crs,
        always_xy=True
    )

    xx, yy = transformer.transform(
        df["longitude"].to_numpy(),
        df["latitude"].to_numpy()
    )

    df["x_km"] = xx / 1000.0
    df["y_km"] = yy / 1000.0

    station_names = df["station_id"].to_numpy(dtype=str)

    stations = df[
        ["x_km", "y_km"]
    ].to_numpy(dtype=float)

    station_index = {
        name: i
        for i, name in enumerate(station_names)
    }

    geod = Geod(ellps="WGS84")

    available = set(station_names)

    pair_records = []
    pair_indices = []
    distances = []
    projected_distances = []

    for sta1, sta2 in pairs:

        # No autocorrelation in inversion geometry.
        if sta1 == sta2:
            continue

        if sta1 not in available or sta2 not in available:
            continue

        i = station_index[sta1]
        j = station_index[sta2]

        _, _, distance_m = geod.inv(
            df.loc[i, "longitude"],
            df.loc[i, "latitude"],
            df.loc[j, "longitude"],
            df.loc[j, "latitude"]
        )

        distance_km = distance_m / 1000.0

        distance_xy = np.linalg.norm(
            stations[i] - stations[j]
        )

        pair_indices.append((i, j))
        distances.append(distance_km)
        projected_distances.append(distance_xy)

        pair_records.append({
            "station1": sta1,
            "station2": sta2,
            "index1": i,
            "index2": j,
            "distance_km": distance_km,
            "distance_projected_km": distance_xy,
            "direct_arrival_s": (
                distance_km / KERNEL_VELOCITY
            ),
        })

    # Force proper shapes even when no pairs exist.
    pair_indices = np.asarray(
        pair_indices,
        dtype=np.int64
    ).reshape(-1, 2)

    distances = np.asarray(
        distances,
        dtype=np.float64
    )

    projected_distances = np.asarray(
        projected_distances,
        dtype=np.float64
    )

    if len(distances) > 0:

        distortion = (
            np.abs(projected_distances - distances)
            / np.maximum(distances, 1e-12)
        )

        max_distortion = float(np.max(distortion))

    else:
        max_distortion = np.nan

    return {
        "df_stations": df,
        "station_names": station_names,
        "stations": stations,
        "station_pairs": pair_indices,
        "pair_distance_km": distances,
        "pair_records": pair_records,
        "origin_lat": lat0,
        "origin_lon": lon0,
        "max_distance_distortion": max_distortion,
    }


# ============================================================
# 6. Calculate actual MWCS lag-time windows
# ============================================================

def build_lag_windows(
    file_records,
    geometry,
    filter_fmin
):
    """
    One row per unique:
        filter / stacking_day / component / station pair

    t_start = n_periods/fmin + distance/window_velocity
    t_end   = t_start + window_width

    Unknown filter fmin is retained as NaN;
    it is never silently replaced with 0.1 Hz.
    """

    if geometry is None:
        return []

    distance_lookup = {
        canonical_pair(
            row["station1"],
            row["station2"]
        ): row["distance_km"]
        for row in geometry["pair_records"]
    }

    unique_records = {}

    for record in file_records:

        sta1 = record["station1"]
        sta2 = record["station2"]

        if sta1 == sta2:
            continue

        pair = canonical_pair(sta1, sta2)

        if pair not in distance_lookup:
            continue

        key = (
            record["filter_id"],
            record["stacking_day"],
            record["component"],
            pair[0],
            pair[1],
        )

        unique_records[key] = record

    rows = []

    for key in sorted(unique_records):

        filter_id, stacking_day, component, sta1, sta2 = key

        distance = distance_lookup[(sta1, sta2)]

        fmin = filter_fmin.get(filter_id)

        if fmin is None:

            t_start = np.nan
            t_end = np.nan

        else:

            t_start = (
                N_PERIODS / fmin
                + distance / WINDOW_VELOCITY
            )

            t_end = t_start + WINDOW_WIDTH

        rows.append({
            "filter_id": filter_id,
            "stacking_day": stacking_day,
            "component": component,
            "station1": sta1,
            "station2": sta2,
            "distance_km": distance,
            "fmin_hz": (
                fmin if fmin is not None else np.nan
            ),
            "t_start_s": t_start,
            "t_end_s": t_end,
            "window_width_s": WINDOW_WIDTH,
            "direct_arrival_s": (
                distance / KERNEL_VELOCITY
            ),
        })

    return rows


# ============================================================
# 7. Plot station geometry
# ============================================================

def plot_station_geometry(geometry, output_path):

    stations = geometry["stations"]
    names = geometry["station_names"]
    pairs = geometry["station_pairs"]
    distances = geometry["pair_distance_km"]

    fig, axes = plt.subplots(
        1, 2,
        figsize=(15, 6),
        dpi=FIG_DPI,
        constrained_layout=True
    )

    # --------------------------------------------------------
    # Station map
    # --------------------------------------------------------

    ax = axes[0]

    for i, j in pairs:

        ax.plot(
            stations[[i, j], 0],
            stations[[i, j], 1],
            color="gray",
            linewidth=0.6,
            alpha=0.12,
            zorder=1
        )

    ax.scatter(
        stations[:, 0],
        stations[:, 1],
        c="tab:red",
        marker="^",
        s=45,
        edgecolors="black",
        linewidths=0.5,
        zorder=3
    )

    if LABEL_STATIONS:

        for name, (sx, sy) in zip(
            names, stations
        ):

            ax.annotate(
                str(name),
                (sx, sy),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=7
            )

    ax.set_xlabel("X (km)")
    ax.set_ylabel("Y (km)")
    ax.set_title("Station geometry")
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.2)

    # --------------------------------------------------------
    # Pair distance histogram
    # --------------------------------------------------------

    ax = axes[1]

    if len(distances) > 0:

        ax.hist(
            distances,
            bins=min(30, max(5, len(distances) // 3)),
            edgecolor="black",
            alpha=0.75
        )

        for seconds, color in [
            (20, "tab:green"),
            (40, "tab:orange"),
            (60, "tab:red"),
        ]:

            distance = seconds * KERNEL_VELOCITY

            ax.axvline(
                distance,
                color=color,
                linestyle="--",
                linewidth=1.5,
                label=f"D/c={seconds} s"
            )

        ax.legend()

    ax.set_xlabel("Station-pair distance (km)")
    ax.set_ylabel("Number of pairs")
    ax.set_title("Station-pair distance distribution")
    ax.grid(True, alpha=0.2)

    fig.savefig(
        output_path,
        dpi=FIG_DPI,
        bbox_inches="tight"
    )

    plt.close(fig)


# ============================================================
# 8. Save station usage and pair usage
# ============================================================

def save_usage_files(scan):

    station_rows = []

    for station_id, usage in sorted(
        scan["station_usage"].items()
    ):

        station_rows.append({
            "station_id": station_id,
            "file_count": usage["file_count"],
            "filters": join_sorted(usage["filters"]),
            "stacking_days": join_sorted(
                usage["stacking_days"]
            ),
            "components": join_sorted(
                usage["components"]
            ),
        })

    save_csv(
        OUTPUT_DIR / "station_usage.csv",
        station_rows,
        [
            "station_id",
            "file_count",
            "filters",
            "stacking_days",
            "components",
        ]
    )

    pair_rows = []

    for (sta1, sta2), usage in sorted(
        scan["pair_usage"].items()
    ):

        pair_rows.append({
            "station1": sta1,
            "station2": sta2,
            "file_count": usage["file_count"],
            "filters": join_sorted(usage["filters"]),
            "stacking_days": join_sorted(
                usage["stacking_days"]
            ),
            "components": join_sorted(
                usage["components"]
            ),
        })

    save_csv(
        OUTPUT_DIR / "station_pair_usage.csv",
        pair_rows,
        [
            "station1",
            "station2",
            "file_count",
            "filters",
            "stacking_days",
            "components",
        ]
    )


# ============================================================
# 9. Save station geometry
# ============================================================

def save_geometry_files(geometry):

    if geometry is None:
        return

    df = geometry["df_stations"]

    df.to_csv(
        OUTPUT_DIR / "station_xy_km.csv",
        index=False
    )

    pair_records = geometry["pair_records"]

    save_csv(
        OUTPUT_DIR / "station_pairs_geometry.csv",
        pair_records,
        [
            "station1",
            "station2",
            "index1",
            "index2",
            "distance_km",
            "distance_projected_km",
            "direct_arrival_s",
        ]
    )

    # Store numeric arrays and Unicode station names.
    # No object arrays / pickle required.

    np.savez_compressed(
        OUTPUT_DIR / "station_geometry.npz",

        stations=np.asarray(
            geometry["stations"],
            dtype=np.float64
        ),

        station_names=np.asarray(
            geometry["station_names"],
            dtype=str
        ),

        station_pairs=np.asarray(
            geometry["station_pairs"],
            dtype=np.int64
        ),

        pair_distance_km=np.asarray(
            geometry["pair_distance_km"],
            dtype=np.float64
        ),

        origin_lat=np.float64(
            geometry["origin_lat"]
        ),

        origin_lon=np.float64(
            geometry["origin_lon"]
        ),

        latitude=df[
            "latitude"
        ].to_numpy(dtype=np.float64),

        longitude=df[
            "longitude"
        ].to_numpy(dtype=np.float64),
    )

    plot_station_geometry(
        geometry,
        OUTPUT_DIR / "station_geometry.png"
    )


# ============================================================
# 10. Save filtered station-pair subsets
# ============================================================

def save_filter_pair_files(
    file_records,
    geometry,
    windows
):

    if geometry is None:
        return

    names = geometry["station_names"]

    index_lookup = {
        name: i
        for i, name in enumerate(names)
    }

    valid_pairs = {
        canonical_pair(
            row["station1"],
            row["station2"]
        )
        for row in geometry["pair_records"]
    }

    # Preserve exact filter / stacking-day / component
    # membership rather than assuming all pairs exist
    # in every subset.

    groups = defaultdict(set)

    for record in file_records:

        pair = canonical_pair(
            record["station1"],
            record["station2"]
        )

        if pair not in valid_pairs:
            continue

        key = (
            record["filter_id"],
            record["stacking_day"],
            record["component"]
        )

        groups[key].add(pair)

    subset_dir = OUTPUT_DIR / "pair_subsets"

    subset_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    for key, pairs in sorted(groups.items()):

        filter_id, stacking_day, component = key

        indices = np.array([
            (
                index_lookup[a],
                index_lookup[b]
            )
            for a, b in sorted(pairs)
        ], dtype=np.int64).reshape(-1, 2)

        folder = (
            subset_dir
            / filter_id
            / stacking_day
        )

        folder.mkdir(
            parents=True,
            exist_ok=True
        )

        # The indices refer to station_geometry.npz
        # station_names / stations arrays.

        np.save(
            folder / f"{component}_pair_indices.npy",
            indices
        )

    # Save all available window records in one CSV.
    save_csv(
        OUTPUT_DIR / "station_pair_lag_windows.csv",
        windows,
        [
            "filter_id",
            "stacking_day",
            "component",
            "station1",
            "station2",
            "distance_km",
            "fmin_hz",
            "t_start_s",
            "t_end_s",
            "window_width_s",
            "direct_arrival_s",
        ]
    )


# ============================================================
# 11. Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Scan CCTorch DVV files and generate "
            "station metadata and geometry."
        )
    )

    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Reference station metadata date, YYYY-MM-DD."
    )

    parser.add_argument(
        "--skip-fdsn",
        action="store_true",
        help="Scan filenames without querying FDSN."
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
    )

    parser.add_argument(
        "--filter-fmin",
        nargs="*",
        default=[],
        metavar="ID=HZ",
        help="Override minimum frequencies, e.g. 01=0.1 02=0.2"
    )

    args = parser.parse_args()

    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")

    filter_fmin = FILTER_FMIN.copy()

    for item in args.filter_fmin:

        if "=" not in item:
            parser.error(
                f"Invalid --filter-fmin: {item}"
            )

        filter_id, value = item.split("=", 1)

        try:
            frequency = float(value)
        except ValueError:
            parser.error(
                f"Invalid frequency: {item}"
            )

        if frequency <= 0:
            parser.error(
                f"Minimum frequency must be positive: {item}"
            )

        filter_fmin[filter_id] = frequency

    print("\n" + "=" * 70)
    print("CCTorch DVV Station Metadata and Geometry")
    print("=" * 70)

    print("Script directory:", SCRIPT_DIR)
    print("DVV directory:", DVV_DIR)
    print("Output directory:", OUTPUT_DIR)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Step 1. Scan DVV
    # --------------------------------------------------------

    scan = scan_dvv_directory(DVV_DIR)

    stations = scan["stations"]
    pairs = scan["pairs"]

    if not stations:
        raise RuntimeError(
            "No valid station-pair TXT files found."
        )

    save_lines(
        OUTPUT_DIR / "station_list.txt",
        stations
    )

    save_lines(
        OUTPUT_DIR / "invalid_filenames.txt",
        scan["invalid_files"]
    )

    save_csv(
        OUTPUT_DIR / "station_pairs.csv",
        [
            {
                "station1": a,
                "station2": b,
                "is_autocorrelation": a == b,
            }
            for a, b in pairs
        ],
        [
            "station1",
            "station2",
            "is_autocorrelation",
        ]
    )

    save_usage_files(scan)

    # --------------------------------------------------------
    # Step 2. Retrieve FDSN metadata
    # --------------------------------------------------------

    if args.skip_fdsn:

        print("\nSkipping FDSN queries.")

        coordinates = []
        missing = stations.copy()

    else:

        coordinates, missing = (
            retrieve_station_coordinates(
                stations,
                metadata_date=args.date,
                batch_size=args.batch_size
            )
        )

    save_csv(
        OUTPUT_DIR / "station_coordinates.csv",
        coordinates,
        [
            "network",
            "station",
            "station_id",
            "latitude",
            "longitude",
            "elevation_m",
            "start_date",
            "end_date",
            "provider",
        ]
    )

    save_lines(
        OUTPUT_DIR / "missing_stations.txt",
        missing
    )

    # --------------------------------------------------------
    # Step 3. Build station geometry
    # --------------------------------------------------------

    geometry = build_station_geometry(
        coordinates,
        pairs
    )

    save_geometry_files(geometry)

    # --------------------------------------------------------
    # Step 4. Generate inversion pairs
    # --------------------------------------------------------

    if geometry is None:
        inversion_pairs = []
    else:
        inversion_pairs = [
            {
                "station1": row["station1"],
                "station2": row["station2"],
            }
            for row in geometry["pair_records"]
        ]

    save_csv(
        OUTPUT_DIR / "station_pairs_for_inversion.csv",
        inversion_pairs,
        ["station1", "station2"]
    )

    # --------------------------------------------------------
    # Step 5. MWCS lag-time windows
    # --------------------------------------------------------

    windows = build_lag_windows(
        scan["file_records"],
        geometry,
        filter_fmin
    )

    save_filter_pair_files(
        scan["file_records"],
        geometry,
        windows
    )

    unknown_filters = sorted(
        set(scan["filters"]) - set(filter_fmin)
    )

    # --------------------------------------------------------
    # Step 6. Summary
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("Final summary")
    print("=" * 70)

    print("Valid TXT files:", len(scan["file_records"]))
    print("Unique stations:", len(stations))
    print("Unique station pairs:", len(pairs))
    print("Coordinates found:", len(coordinates))
    print("Missing coordinates:", len(missing))
    print("Inversion pairs:", len(inversion_pairs))
    print("Lag-window rows:", len(windows))

    if geometry is not None:

        print(
            "X range (km):",
            geometry["stations"][:, 0].min(),
            geometry["stations"][:, 0].max()
        )

        print(
            "Y range (km):",
            geometry["stations"][:, 1].min(),
            geometry["stations"][:, 1].max()
        )

        print(
            "Maximum projection distance distortion:",
            f"{100 * geometry['max_distance_distortion']:.6f}%"
        )

        distances = geometry["pair_distance_km"]

        if len(distances) > 0:

            print(
                "Pair distance range (km):",
                distances.min(),
                distances.max()
            )

    if unknown_filters:

        print("\nWARNING: Missing fmin for filters:")
        print(unknown_filters)

        print(
            "Their lag-time windows were saved as NaN. "
            "Specify --filter-fmin or edit FILTER_FMIN."
        )

    if missing:

        print("\nStations without coordinates:")

        for station_id in missing:
            print(" ", station_id)

    print("\nOutput:")
    print(OUTPUT_DIR)

    print("\nCompleted.")


if __name__ == "__main__":
    main()
