# MWCS Zarr Availability Scanner

A Python utility for scanning daily Moving Window Cross-Spectral (MWCS) measurement availability from station-pair Zarr stores and visualizing the results as timeline plots.

The script is designed for ambient-noise interferometry workflows, where MWCS measurements are stored separately for each station pair and correlation component.

**Script:** `02a_scan_available_mwcs_zarr.py`

## 1. Features

- Automatically scans MWCS Zarr stores organized by component and station pair.
- Reads available dates directly from the Zarr `date` array.
- Supports all nine correlation components: `EE`, `EN`, `EZ`, `NE`, `NN`, `NZ`, `ZE`, `ZN`, and `ZZ`.
- Converts `YYYYJJJ` dates into standard `YYYY-MM-DD` dates.
- Visualizes daily availability using horizontal timeline plots.
- Combines consecutive available dates into continuous intervals for efficient plotting.
- Supports user-defined start and end dates.
- Automatically splits large figures into multiple PNG files.
- Optionally exports available dates to CSV.
- Includes autocorrelation and cross-correlation station pairs.
- Avoids loading the full MWCS measurement array, reducing memory usage.

## 2. Expected Directory Structure

The input directory should contain component subdirectories, each containing station-pair Zarr stores.

Example:

```text
MWCS_unfold/
└── 01/
    └── pm014_DAYS/
        ├── EE/
        │   ├── CI.CCC_CI.LRL.zarr/
        │   └── CI.CCC_CI.WBM.zarr/
        ├── NN/
        │   └── CI.CCC_CI.LRL.zarr/
        └── ZZ/
            ├── CI.CCC_CI.CCC.zarr/
            ├── CI.CCC_CI.LRL.zarr/
            ├── CI.CCC_CI.WBM.zarr/
            ├── CI.WCS2_CI.WRC2.zarr/
            └── CI.WMF_CI.WMF.zarr/
```

Station-pair filenames follow:

```text
NETWORK1.STATION1_NETWORK2.STATION2.zarr
```

For example:

```text
CI.CCC_CI.LRL.zarr
```

represents the station pair `CI.CCC` and `CI.LRL`.

Autocorrelations such as `CI.CCC_CI.CCC.zarr` are also supported.

## 3. Expected Zarr Structure

Each station-pair Zarr store should contain two arrays:

```text
/
├── data (n_dates, n_lags, 4) float64
└── date (n_dates,) int64
```

An example from the Ridgecrest dataset:

```text
data (4188, 591, 4) float64
date (4188,) int64
```

The dimensions of `data` represent:

| Dimension | Description |
|---|---|
| Axis 0 | Measurement dates |
| Axis 1 | MWCS lapse-time samples |
| Axis 2 | MWCS measurement parameters |

The four MWCS parameters are:

| Column | Parameter | Unit |
|---|---|---|
| 0 | Lapse time | seconds |
| 1 | Time shift (`dt`) | seconds |
| 2 | Time-shift uncertainty (`dt_err`) | seconds |
| 3 | Correlation coefficient (`corrcoef`) | dimensionless |

The `date` array contains integer dates in `YYYYJJJ` format, where `JJJ` is the day of the year.

Examples:

```text
2015001 -> 2015-01-01
2015365 -> 2015-12-31
2016366 -> 2016-12-31
```

**Important:** This script only reads the `date` array and checks the dimensions of `data`. It does not load the full MWCS measurements.

## 4. Requirements

Python 3.9 or later is recommended.

Required packages:

- NumPy
- Matplotlib
- Zarr

Install using pip:

```bash
pip install numpy matplotlib zarr
```

Or using micromamba:

```bash
micromamba install -c conda-forge numpy matplotlib zarr
```

## 5. Usage

### 5.1 Basic Usage

From the project directory:

```bash
python 02a_scan_available_mwcs_zarr.py \
    -i MWCS_unfold/01/pm014_DAYS \
    -o mwcs_availability.png
```

This scans all detected component folders and generates availability plots.

### 5.2 Scan ZZ Component Only

```bash
python 02a_scan_available_mwcs_zarr.py \
    -i MWCS_unfold/01/pm014_DAYS \
    -o mwcs_availability_ZZ.png \
    --components ZZ
```

### 5.3 Scan Multiple Components

```bash
python 02a_scan_available_mwcs_zarr.py \
    -i MWCS_unfold/01/pm014_DAYS \
    -o mwcs_availability_multi.png \
    --components ZZ EE NN
```

### 5.4 Scan All Nine Components

```bash
python 02a_scan_available_mwcs_zarr.py \
    -i MWCS_unfold/01/pm014_DAYS \
    -o mwcs_availability_all.png \
    --components EE EN EZ NE NN NZ ZE ZN ZZ
```

### 5.5 Specify a Date Range

To visualize availability between January 1, 2019 and December 31, 2021:

```bash
python 02a_scan_available_mwcs_zarr.py \
    -i MWCS_unfold/01/pm014_DAYS \
    -o mwcs_availability_2019_2021.png \
    --components ZZ \
    --start 2019-01-01 \
    --end 2021-12-31
```

Both start and end dates are inclusive.

### 5.6 Export a CSV File

```bash
python 02a_scan_available_mwcs_zarr.py \
    -i MWCS_unfold/01/pm014_DAYS \
    -o mwcs_availability_ZZ.png \
    --components ZZ \
    --csv mwcs_availability_ZZ.csv
```

### 5.7 Customize Plot Settings

```bash
python 02a_scan_available_mwcs_zarr.py \
    -i MWCS_unfold/01/pm014_DAYS \
    -o mwcs_availability_ZZ.png \
    --components ZZ \
    --rows-per-page 50 \
    --dpi 300 \
    --title "Ridgecrest ZZ MWCS Availability"
```

## 6. Command-Line Arguments

| Argument | Description | Default |
|---|---|---|
| `-i`, `--input` | Root directory containing component folders | `MWCS_unfold/01/pm014_DAYS` |
| `-o`, `--output` | Output PNG filename | `mwcs_availability.png` |
| `--components` | Components to include | All detected components |
| `--start` | Start date, inclusive (`YYYY-MM-DD`) | Earliest available date |
| `--end` | End date, inclusive (`YYYY-MM-DD`) | Latest available date |
| `--csv` | Optional CSV output path | None |
| `--rows-per-page` | Maximum number of station-pair rows per figure | 80 |
| `--dpi` | PNG resolution | 150 |
| `--title` | Figure title | `Daily MWCS availability` |

View the built-in help:

```bash
python 02a_scan_available_mwcs_zarr.py --help
```

## 7. Output

### 7.1 PNG Availability Plot

The generated figure contains:

- **X-axis:** Calendar date.
- **Y-axis:** Station pair and correlation component.
- **Blue horizontal intervals:** Dates with MWCS records.
- **Blank regions:** Dates without MWCS records in the Zarr date index.

Consecutive available dates are merged into continuous horizontal intervals.

For large datasets, the plot is automatically divided into multiple pages.

For example:

```text
mwcs_availability_001.png
mwcs_availability_002.png
mwcs_availability_003.png
```

### 7.2 CSV Availability Table

When `--csv` is specified, the script exports one row for each available station-pair/component/day combination.

Example:

```csv
component,station_pair,label,date,available
ZZ,CI.CCC_CI.LRL,CI.CCC–CI.LRL.ZZ,2015-01-01,1
ZZ,CI.CCC_CI.LRL,CI.CCC–CI.LRL.ZZ,2015-01-02,1
ZZ,CI.CCC_CI.WBM,CI.CCC–CI.WBM.ZZ,2015-01-01,1
```

Only available dates are included. Missing dates are not represented as rows with `available=0`.

### 7.3 Terminal Summary

The script reports the number of scanned station-pair/component rows and available records.

Example output:

```text
Scanning component: ZZ
  Found 120 Zarr stores
  Processed 20/120
  Processed 40/120
  ...
  Processed 120/120

PNG: mwcs_availability_ZZ_001.png
PNG: mwcs_availability_ZZ_002.png

=== MWCS availability summary ===
Station-pair/component rows: 120
Rows with available dates: 115
Available row-days: 450,000
```

These values are illustrative; actual counts depend on the dataset.

## 8. Definition of MWCS Availability

In this script, a date is considered **available** when it is present in the Zarr `date` array.

This does not necessarily mean that the corresponding MWCS measurements are valid or suitable for seismic velocity-change inversion.

For example, an available date may contain:

- Non-finite time shifts (`NaN` or `Inf`).
- Large time-shift uncertainties.
- Low correlation coefficients.
- Unstable or cycle-skipped MWCS estimates.
- Missing or invalid measurements within a particular coda window.

The script does not perform quality control based on these quantities.

For inversion applications, additional filtering using `dt`, `dt_err`, `corrcoef`, and coda lapse-time ranges is recommended.

## 9. Error Handling

The script handles several common problems:

**Malformed station-pair filename**

Files that do not follow:

```text
NETWORK.STATION_NETWORK.STATION.zarr
```

are skipped with a warning.

**Missing Zarr arrays**

A warning is issued if a Zarr store does not contain the expected `date` or `data` array.

**Inconsistent array dimensions**

A warning is issued if the number of dates does not match the first dimension of the MWCS data array.

**Invalid dates**

Malformed or impossible `YYYYJJJ` values are skipped.

**Unreadable Zarr stores**

If a store cannot be opened, the corresponding station-pair row is retained with no available dates.

## 10. Notes for Ridgecrest dv/v Inversion

This utility can be used to identify dates with sufficient MWCS station-pair coverage before performing spatial dv/v inversion.

For the Ridgecrest workflow:

- The MWCS dataset contains multiple correlation components.
- The initial multi-lapse-time inversion benchmark uses the ZZ component.
- The current inversion geometry contains 14 stations and 91 distinct station pairs.
- The inversion model uses a 4 × 4 km spatial grid with 684 model cells.

The availability plot may include autocorrelations and additional station pairs that are not part of the 91-pair inversion geometry.

Therefore, the number of available Zarr files is not necessarily equal to the number of usable inversion station pairs.

A recommended workflow is:

1. Scan ZZ MWCS availability.
2. Identify dates with high station-pair coverage.
3. Match Zarr station pairs to the inversion geometry.
4. Extract MWCS measurements at selected coda lapse times.
5. Apply quality control to time shifts and uncertainties.
6. Assemble the multi-lapse-time sensitivity matrix and observation vector.
7. Perform regularized spatial dv/v inversion.

## 11. Performance Considerations

The script reads only the Zarr `date` array and the metadata required to verify the `data` array shape.

It does not load waveform data or the full MWCS measurement array.

This makes it suitable for scanning many Zarr stores with thousands of dates and hundreds of lapse-time samples.

Plotting time and image size scale primarily with the number of station-pair rows and available-date intervals.

Use `--rows-per-page` to control figure size when processing large datasets.

---

**Purpose:** Visualize MWCS record availability and identify suitable time periods for further ambient-noise interferometry analysis and seismic velocity-change inversion.
