# CCTorch DVV Station Metadata and Geometry Scanner

A Python utility for automatically extracting seismic station information from CCTorch dv/v outputs, retrieving station metadata through FDSN web services, and generating station geometry and lag-time windows for subsequent spatial inversion.

## 1. Features

- **Automatic station discovery:** Recursively scan all DVV output folders and identify unique seismic stations and station pairs.
- **Multi-data-center support:** Retrieve station coordinates from SCEDC, NCEDC, and EarthScope using ObsPy FDSN clients.
- **Network-aware FDSN queries:** Automatically select preferred data centers based on seismic network codes, with fallback providers.
- **Station geometry:** Convert geographic coordinates (latitude/longitude) into local Cartesian coordinates (km) using a WGS84 Azimuthal Equidistant projection.
- **Station-pair distances:** Calculate geodesic distances and projected distances for all available station pairs.
- **Distance-dependent lag-time windows:** Generate MWCS lag-time windows based on the minimum filter frequency and station-pair distance.
- **Station usage tracking:** Record which filters, stacking periods, and components contain each station and station pair.
- **Visualization:** Generate a station distribution map and station-pair distance histogram.
- **Inversion-ready outputs:** Export CSV, TXT, NPY, and NPZ files for subsequent 2D dv/v sensitivity and resolution analysis.

## 2. Directory Structure

Place `scan_dvv_station_metadata.py` in the same directory as `DVV/`.

The script automatically determines its location and scans the entire `DVV/` directory.

```text
PROJECT/
├── scan_dvv_station_metadata.py
├── DVV/
│   ├── 01/
│   │   ├── pm014_DAYS/
│   │   │   ├── EE/
│   │   │   │   ├── CI.CCC_CI.CGO.txt
│   │   │   │   └── ...
│   │   │   ├── NN/
│   │   │   └── ZZ/
│   │   └── pm030_DAYS/
│   ├── 02/
│   └── ...
└── station_metadata/             # Automatically generated
```

Expected DVV directory structure:

```text
DVV/<filter_id>/<stacking_day>/<component>/<station_pair>.txt
```

Expected station-pair filename:

```text
NETWORK1.STATION1_NETWORK2.STATION2.txt
```

For example:

```text
CI.CCC_CI.CGO.txt
CI.CCC_CI.CLC.txt
BK.BIGM_BK.DMOR.txt
```

The script extracts station information from filenames. The contents of the TXT files are not required for station discovery.

## 3. Requirements

Python 3.10 or newer is recommended.

Required Python packages:

- NumPy
- pandas
- Matplotlib
- ObsPy
- pyproj

Install using micromamba:

```bash
micromamba install -c conda-forge \
    numpy pandas matplotlib obspy pyproj
```

The script requires an internet connection to retrieve station coordinates from FDSN services.

The local file-scanning functionality can be used without an internet connection.

## 4. Configuration

The main configuration parameters are defined at the beginning of `scan_dvv_station_metadata.py`.

### 4.1 Input and output directories

```python
SCRIPT_DIR = Path(__file__).resolve().parent

DVV_DIR = SCRIPT_DIR / "DVV"
OUTPUT_DIR = SCRIPT_DIR / "station_metadata"
```

The paths are determined automatically based on the location of the Python script.

No absolute path configuration is required.

### 4.2 FDSN data centers

Supported providers:

```python
FDSN_DATA_CENTERS = {
    "SCEDC": "https://service.scedc.caltech.edu",
    "NCEDC": "https://service.ncedc.org",
    "EARTHSCOPE": "EARTHSCOPE",
}
```

Preferred providers are selected by network:

```python
NETWORK_DATA_CENTERS = {
    "CI": ["SCEDC", "EARTHSCOPE", "NCEDC"],
    "BK": ["NCEDC", "EARTHSCOPE", "SCEDC"],
    "NC": ["NCEDC", "EARTHSCOPE", "SCEDC"],
    "BP": ["NCEDC", "EARTHSCOPE", "SCEDC"],
}
```

For networks not explicitly configured, the script uses:

```python
DEFAULT_DATA_CENTERS = [
    "EARTHSCOPE",
    "SCEDC",
    "NCEDC",
]
```

Additional FDSN data centers and network mappings can be added to these dictionaries.

### 4.3 Filter frequency configuration

The minimum frequency of each filter is used to determine the lag-time window.

```python
FILTER_FMIN = {
    "01": 0.1,
}
```

For multiple filters, extend the dictionary with the actual minimum frequencies:

```python
FILTER_FMIN = {
    "01": 0.1,
    "02": 0.2,
    "03": 0.4,
}
```

The frequencies above are examples; each value must match the filter configuration used during the corresponding dv/v processing.

The filter configuration can also be overridden through command-line arguments.

If a filter ID has no configured minimum frequency, the associated lag-time window values are saved as `NaN` rather than assigning an arbitrary default.

### 4.4 MWCS lag-time window parameters

```python
N_PERIODS = 3.0

WINDOW_VELOCITY = 1.0    # km/s
WINDOW_WIDTH = 40.0      # seconds

KERNEL_VELOCITY = 2.0    # km/s
```

`WINDOW_VELOCITY` is used to determine the measurement window based on station separation.

`KERNEL_VELOCITY` is used only to calculate the modeled direct arrival time in the generated metadata. It does not modify the MWCS window definition.

## 5. Usage

### 5.1 Basic execution

From the project directory:

```bash
python scan_dvv_station_metadata.py
```

The script automatically:

1. Scans all nested DVV directories.
2. Extracts unique stations and station pairs.
3. Queries available FDSN data centers.
4. Retrieves station coordinates.
5. Generates local Cartesian station geometry.
6. Computes station-pair distances.
7. Generates MWCS lag-time windows.
8. Saves metadata and geometry files.

### 5.2 Specify a station metadata date

To retrieve station metadata for a particular observation period:

```bash
python scan_dvv_station_metadata.py \
    --date 2024-09-01
```

The specified date is used to select station metadata epochs.

This is recommended for historical datasets, particularly when station coordinates or metadata have changed over time.

Without `--date`, the script selects the latest returned metadata epoch for each station.

### 5.3 Specify filter frequencies

```bash
python scan_dvv_station_metadata.py \
    --filter-fmin 01=0.1 02=0.2 03=0.4
```

These values override or extend `FILTER_FMIN` without modifying the Python script.

### 5.4 Scan without FDSN queries

```bash
python scan_dvv_station_metadata.py --skip-fdsn
```

This mode performs local station discovery without accessing remote metadata services.

It generates station and pair usage information but does not retrieve coordinates or generate new geometry.

Previously generated geometry files, if present, are not automatically removed.

### 5.5 Set FDSN batch size

```bash
python scan_dvv_station_metadata.py \
    --batch-size 10
```

The default batch size is 20 stations per request.

Reducing the batch size may help when an FDSN provider rejects large requests.

## 6. Station Coordinate System

Station geographic coordinates are retrieved in latitude and longitude.

The script converts them into local Cartesian coordinates using the WGS84 Azimuthal Equidistant (AEQD) projection.

The projection origin is defined by the median latitude and longitude of the retrieved stations:

\[
\phi_0=\operatorname{median}(\phi_i)
\]

\[
\lambda_0=\operatorname{median}(\lambda_i)
\]

The resulting coordinates are expressed in kilometers:

\[
(x_i,y_i)\quad [\mathrm{km}]
\]

The local coordinates can be used directly in 2D sensitivity-kernel calculations.

Station-pair distances are calculated independently using WGS84 geodesic distances.

The script also reports the maximum relative discrepancy between geodesic and projected pair distances to assess projection distortion.

## 7. Distance-Dependent MWCS Lag-Time Windows

Each station pair uses a lag-time window determined by the minimum filter frequency and station-pair distance.

The window start time is defined as:

\[
t_{\mathrm{start},ij}
=
\frac{N_{\mathrm{periods}}}{f_{\min}}
+
\frac{D_{ij}}{v_{\mathrm{window}}}
\]

The window end time is:

\[
t_{\mathrm{end},ij}
=
t_{\mathrm{start},ij}
+
T_{\mathrm{window}}
\]

where:

| Parameter | Description | Default |
|---|---|---|
| \(N_{\mathrm{periods}}\) | Number of periods of the minimum filter frequency | 3 |
| \(f_{\min}\) | Minimum filter frequency | Filter dependent |
| \(D_{ij}\) | Station-pair distance | km |
| \(v_{\mathrm{window}}\) | Window reference velocity | 1 km/s |
| \(T_{\mathrm{window}}\) | Window duration | 40 s |

For example, with a 0.1–0.9 Hz filter and a station-pair distance of 40 km:

\[
t_{\mathrm{start}}
=
\frac{3}{0.1}
+
\frac{40}{1}
=
70\ \mathrm{s}
\]

\[
t_{\mathrm{end}}=110\ \mathrm{s}
\]

The corresponding lag-time window is:

```text
70–110 s
```

The window parameters are stored separately for each available filter, stacking period, component, and station pair.

## 8. Output Files

All outputs are stored under `station_metadata/`.

```text
station_metadata/
├── station_list.txt
├── station_coordinates.csv
├── station_xy_km.csv
├── station_pairs.csv
├── station_pairs_for_inversion.csv
├── station_pairs_geometry.csv
├── station_pair_lag_windows.csv
├── station_usage.csv
├── station_pair_usage.csv
├── station_geometry.npz
├── station_geometry.png
├── missing_stations.txt
├── invalid_filenames.txt
└── pair_subsets/
    └── 01/
        └── pm014_DAYS/
            ├── EE_pair_indices.npy
            ├── NN_pair_indices.npy
            └── ZZ_pair_indices.npy
```

### 8.1 Station metadata

| File | Description |
|---|---|
| `station_list.txt` | Unique stations discovered across all DVV files |
| `station_coordinates.csv` | Geographic coordinates, elevation, metadata epochs, and FDSN providers |
| `station_xy_km.csv` | Station metadata with projected Cartesian coordinates |
| `missing_stations.txt` | Stations for which coordinates could not be retrieved |

### 8.2 Station-pair information

| File | Description |
|---|---|
| `station_pairs.csv` | All unique station pairs, including autocorrelations |
| `station_pairs_for_inversion.csv` | Cross-correlation pairs with valid coordinates for both stations |
| `station_pairs_geometry.csv` | Station indices, geodesic distances, projected distances, and modeled direct arrival times |
| `station_pair_lag_windows.csv` | Distance-dependent MWCS windows for each filter, stacking period, component, and pair |

### 8.3 Usage tracking

| File | Description |
|---|---|
| `station_usage.csv` | Filters, stacking periods, components, and file counts associated with each station |
| `station_pair_usage.csv` | Filters, stacking periods, components, and file counts associated with each pair |
| `invalid_filenames.txt` | TXT files that do not match the expected directory structure or naming convention |

### 8.4 Geometry and inversion files

| File | Description |
|---|---|
| `station_geometry.npz` | NumPy arrays containing station coordinates, names, pairs, distances, and projection origin |
| `station_geometry.png` | Station map and station-pair distance histogram |
| `pair_subsets/` | Pair-index arrays organized by filter, stacking period, and component |

Autocorrelation pairs are excluded from inversion geometry but remain recorded in the general station-pair inventory.

## 9. Using the Results for 2D dv/v Inversion

### 9.1 Load station geometry

```python
import numpy as np
from pathlib import Path

metadata_dir = Path("station_metadata")

with np.load(
    metadata_dir / "station_geometry.npz",
    allow_pickle=False
) as geo:

    stations = geo["stations"].copy()
    station_names = geo["station_names"].copy()
    station_pairs = geo["station_pairs"].copy()
    distances = geo["pair_distance_km"].copy()

print("Stations:", stations.shape)
print("Station names:", station_names.shape)
print("Station pairs:", station_pairs.shape)
print("Pair distances:", distances.shape)
```

The arrays have the following structure:

| Variable | Shape | Description |
|---|---|---|
| `stations` | `(N, 2)` | Cartesian station coordinates in km |
| `station_names` | `(N,)` | Network.station identifiers |
| `station_pairs` | `(M, 2)` | Integer station-pair indices |
| `distances` | `(M,)` | Geodesic pair distances in km |

All station-pair indices refer to the ordering in `station_names` and `stations`.

### 9.2 Select a particular filter and component

For example, to select filter `01`, stacking period `pm014_DAYS`, and component `ZZ`:

```python
station_pairs = np.load(
    metadata_dir
    / "pair_subsets"
    / "01"
    / "pm014_DAYS"
    / "ZZ_pair_indices.npy"
)

print("Selected pairs:", station_pairs.shape)
```

Only pairs that actually exist in the selected DVV output and have available station coordinates are included.

### 9.3 Load the corresponding MWCS windows

```python
import pandas as pd

df = pd.read_csv(
    metadata_dir / "station_pair_lag_windows.csv",
    dtype={"filter_id": str}
)

selected = df[
    (df["filter_id"].str.zfill(2) == "01")
    & (df["stacking_day"] == "pm014_DAYS")
    & (df["component"] == "ZZ")
].copy()

window_lookup = {
    tuple(sorted((row.station1, row.station2))):
        (row.t_start_s, row.t_end_s)
    for row in selected.itertuples()
}

windows = np.array([
    window_lookup[
        tuple(sorted((
            str(station_names[i]),
            str(station_names[j])
        )))
    ]
    for i, j in station_pairs
], dtype=float)

if not np.all(np.isfinite(windows)):
    raise ValueError("Missing or invalid lag-time windows.")

t_start = windows[:, 0]
t_end = windows[:, 1]

print("Window start range:", t_start.min(), t_start.max())
print("Window end range:", t_end.min(), t_end.max())
```

These arrays can be passed to a pair-dependent finite-window sensitivity-kernel calculation.

## 10. Notes and Limitations

**Station metadata epochs**

A single metadata epoch is selected for each station. For datasets spanning station relocations, coordinates should be resolved separately for the relevant observation periods.

**Station-pair availability**

The script uses only station pairs actually discovered in the DVV files. It does not assume that every possible station pair exists in every filter, stacking period, or component.

**Unknown filter frequencies**

Lag-time windows for filters without configured minimum frequencies are stored as `NaN`. Define all relevant filter frequencies before using the windows in an inversion.

**FDSN availability**

Metadata retrieval depends on remote FDSN services. Missing stations are recorded rather than silently discarded from the discovered station inventory.

**Local projection**

The AEQD projection is suitable for regional analyses, but projection distortion should be checked when station networks span large geographic regions.

**Geometry versus inversion domain**

Station geometry does not define the spatial inversion grid. Model boundaries, grid spacing, regularization, and sensitivity kernels must be configured separately.

**Observation uncertainty**

The generated lag-time windows describe measurement geometry and timing. They do not provide MWCS measurement uncertainties, correlations, or observational covariance matrices.

**Existing outputs**

The script writes results to a fixed output directory. Re-running it updates generated files, but modes such as `--skip-fdsn` do not automatically remove older geometry files. Similarly, obsolete pair-subset files from previous runs may remain unless the output directory is cleaned.

## 11. Recommended Workflow

```text
CCTorch DVV Processing
          |
          v
DVV/filter_id/stacking_day/component/*.txt
          |
          v
scan_dvv_station_metadata.py
          |
          +-- Unique station discovery
          |
          +-- SCEDC / NCEDC / EarthScope
          |
          +-- Station geographic coordinates
          |
          +-- Cartesian geometry
          |
          +-- Actual station-pair distances
          |
          +-- Distance-dependent MWCS windows
          |
          v
station_metadata/
          |
          v
2D Sensitivity Kernel Calculation
          |
          v
BB + BD + DB + DD
          |
          v
SVD / Resolution Matrix / PSF
          |
          v
2D dv/v Inversion
```

This utility is intended to provide reproducible station metadata and geometry preprocessing for CCTorch-based ambient-noise dv/v monitoring and subsequent spatial inversion experiments.
