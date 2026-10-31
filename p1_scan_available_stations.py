import pandas as pd
import pygmt
import numpy as np
import geopandas as gpd

from pathlib import Path
from shapely.geometry import box
from obspy import UTCDateTime
from obspy.clients.fdsn import Client


# ============================================================
# 1. User input
# ============================================================

print("=" * 60)
print("Seismic Station Search")
print("=" * 60)

print("\nEnter top-left coordinate:")
lat_top = float(input("Latitude: "))
lon_left = float(input("Longitude: "))

print("\nEnter bottom-right coordinate:")
lat_bottom = float(input("Latitude: "))
lon_right = float(input("Longitude: "))

print("\nEnter time span:")
start_date = input("Start date (YYYY-MM-DD): ")
end_date = input("End date (YYYY-MM-DD): ")

starttime = UTCDateTime(start_date)
endtime = UTCDateTime(end_date) + 86400 - 1e-6

if endtime < starttime:
    raise ValueError("End date must not precede start date.")

# ============================================================
# Legend position
# ============================================================

print("\nSelect legend position:")
print("1. Top-left")
print("2. Top-right")
print("3. Bottom-left")
print("4. Bottom-right")

legend_positions = {
    "1": "TL",
    "2": "TR",
    "3": "BL",
    "4": "BR",
}

while True:
    legend_choice = input(
        "Legend position (1-4, default=4): "
    ).strip()

    if legend_choice == "":
        legend_choice = "4"

    if legend_choice in legend_positions:
        legend_position = legend_positions[legend_choice]
        break

    print("Invalid selection. Please enter 1, 2, 3, or 4.")

print(f"Selected legend position: {legend_position}")

# ============================================================
# 2. Configuration
# ============================================================

base_dir = Path(__file__).resolve().parent

output_dir = base_dir / "station_search"
output_dir.mkdir(parents=True, exist_ok=True)

fault_file = (
    base_dir
    / "faults"
    / "Qfaults_GIS"
    / "SHP"
    / "Qfaults_US_Database.shp"
)

client = Client("EARTHSCOPE")

minlatitude = min(lat_top, lat_bottom)
maxlatitude = max(lat_top, lat_bottom)

minlongitude = min(lon_left, lon_right)
maxlongitude = max(lon_left, lon_right)

region = [
    minlongitude,
    maxlongitude,
    minlatitude,
    maxlatitude,
]

# Plotting parameters
STATION_FONT_SIZE = 10
STATION_SYMBOL_SIZE = "0.4c"  # Increased from 0.25c

# Station appearance
STATION_COLOR = "yellow"
STATION_EDGE_COLOR = "black"
STATION_EDGE_WIDTH = 1.5  # Points

# Fault appearance
FAULT_COLOR = "red"
FAULT_WIDTH = 1.2  # Points

MAP_WIDTH = "15c"
MAP_DPI = 300


# ============================================================
# 3. Retrieve seismic stations
# ============================================================

print("\nSearching seismic stations...")

inventory = client.get_stations(
    starttime=starttime,
    endtime=endtime,
    minlatitude=minlatitude,
    maxlatitude=maxlatitude,
    minlongitude=minlongitude,
    maxlongitude=maxlongitude,
    level="station",
)

station_data = []

for network in inventory:

    for station in network:

        station_data.append({
            "network": network.code,
            "station": station.code,
            "latitude": station.latitude,
            "longitude": station.longitude,
            "elevation_m": station.elevation,
            "start_date": (
                str(station.start_date)
                if station.start_date else ""
            ),
            "end_date": (
                str(station.end_date)
                if station.end_date else ""
            ),
        })

df = pd.DataFrame(station_data)

if df.empty:
    print("No stations found.")
    raise SystemExit

df = df.drop_duplicates(
    subset=[
        "network",
        "station",
        "latitude",
        "longitude",
    ]
)

df = df.sort_values(
    ["network", "station"]
).reset_index(drop=True)

print(f"Total stations: {len(df)}")


# ============================================================
# 4. Save station list
# ============================================================

csv_file = output_dir / "stations.csv"

df.to_csv(
    csv_file,
    index=False,
)

print(f"Station list saved: {csv_file}")


# ============================================================
# 5. Automatically select topography resolution
# ============================================================

def select_topography_resolution(region):
    """
    Automatically select GMT Earth relief resolution
    based on geographic extent.

    Parameters
    ----------
    region : list
        [minlongitude, maxlongitude, minlatitude, maxlatitude]

    Returns
    -------
    resolution : str
        GMT Earth relief resolution.
    """

    lon_min, lon_max, lat_min, lat_max = region

    lat_center = (lat_min + lat_max) / 2

    # Approximate dimensions in kilometers
    width_km = (
        (lon_max - lon_min)
        * 111.32
        * np.cos(np.radians(lat_center))
    )

    height_km = (
        (lat_max - lat_min)
        * 111.32
    )

    area_km2 = width_km * height_km

    print("\nGeographic extent:")
    print(f"Width:  {width_km:.1f} km")
    print(f"Height: {height_km:.1f} km")
    print(f"Area:   {area_km2:.1f} km²")

    if area_km2 < 5_000:
        resolution = "01s"

    elif area_km2 < 20_000:
        resolution = "03s"

    elif area_km2 < 100_000:
        resolution = "15s"

    elif area_km2 < 500_000:
        resolution = "30s"

    elif area_km2 < 2_000_000:
        resolution = "01m"

    else:
        resolution = "05m"

    print(f"Selected topography resolution: {resolution}")

    return resolution


resolution = select_topography_resolution(region)

print(f"\nDownloading topography ({resolution})...")

grid = pygmt.datasets.load_earth_relief(
    resolution=resolution,
    region=region,
)


# ============================================================
# 6. Load USGS Quaternary fault database
# ============================================================

print("\nLoading USGS Quaternary fault database...")

if not fault_file.exists():
    raise FileNotFoundError(
        f"Fault shapefile not found:\n{fault_file}"
    )

# Geographic bounding box in WGS84
bbox = box(
    minlongitude,
    minlatitude,
    maxlongitude,
    maxlatitude,
)

# Read only the shapefile CRS metadata and one record
fault_metadata = gpd.read_file(
    fault_file,
    rows=1,
)

if fault_metadata.crs is None:
    raise ValueError(
        "Fault shapefile has no coordinate reference system."
    )

# Transform bounding box into shapefile CRS
bbox_native = (
    gpd.GeoSeries(
        [bbox],
        crs="EPSG:4326",
    )
    .to_crs(fault_metadata.crs)
    .total_bounds
)

# Spatially filter features while reading
faults = gpd.read_file(
    fault_file,
    bbox=tuple(bbox_native),
)

print(f"Fault features loaded: {len(faults)}")

# Convert fault coordinates to WGS84
faults = faults.to_crs(epsg=4326)

# Keep line geometries only
faults = faults[
    faults.geom_type.isin(
        ["LineString", "MultiLineString"]
    )
].copy()

# Clip fault traces to selected geographic region
faults_region = gpd.clip(
    faults,
    bbox,
)

faults_region = faults_region[
    ~faults_region.geometry.is_empty
].copy()

print(
    f"Fault features within selected region: "
    f"{len(faults_region)}"
)


# ============================================================
# 7. Save clipped fault data
# ============================================================

fault_output = output_dir / "faults_region.geojson"

if not faults_region.empty:

    faults_region.to_file(
        fault_output,
        driver="GeoJSON",
    )

    print(f"Clipped faults saved: {fault_output}")

else:
    print("No mapped faults found within selected region.")

    # Avoid leaving an outdated file from a previous run
    if fault_output.exists():
        fault_output.unlink()


# ============================================================
# 8. Generate map
# ============================================================

print("\nGenerating map...")

pygmt.config(
    FONT_TITLE="12p,Helvetica-Bold,black",
    FONT_LABEL="10p,Helvetica,black",
    FONT_ANNOT_PRIMARY="9p,Helvetica,black",
)

fig = pygmt.Figure()


# ------------------------------------------------------------
# 8.1 Topography color palette
# ------------------------------------------------------------

pygmt.makecpt(
    cmap="geo",
    series=[-3000, 4000, 100],
    continuous=True,
)


# ------------------------------------------------------------
# 8.2 Plot topography
# ------------------------------------------------------------

fig.grdimage(
    grid=grid,
    region=region,
    projection=f"M{MAP_WIDTH}",
    cmap=True,
    shading=True,
    frame=[
        "xaf",
        "yaf",
        f"+tSeismic Stations ({start_date} to {end_date})",
    ],
)


# ------------------------------------------------------------
# 8.3 Plot USGS Quaternary fault traces
# ------------------------------------------------------------

print("Plotting fault traces...")

n_fault_segments = 0

for geom in faults_region.geometry:

    if geom is None or geom.is_empty:
        continue

    if geom.geom_type == "LineString":
        lines = [geom]

    elif geom.geom_type == "MultiLineString":
        lines = list(geom.geoms)

    else:
        continue

    for line in lines:

        if line.is_empty:
            continue

        x, y = line.xy

        fig.plot(
            x=np.asarray(x),
            y=np.asarray(y),
            pen=f"{FAULT_WIDTH}p,{FAULT_COLOR}",
        )

        n_fault_segments += 1

print(f"Plotted fault segments: {n_fault_segments}")


# ------------------------------------------------------------
# 8.4 Coastline and state boundaries
# ------------------------------------------------------------

fig.coast(
    shorelines="0.8p,black",
    borders=[
        "1/0.5p,black",
        "2/0.5p,gray",
    ],
)


# ------------------------------------------------------------
# 8.5 Plot seismic stations
# ------------------------------------------------------------

fig.plot(
    x=df["longitude"],
    y=df["latitude"],
    style=f"t{STATION_SYMBOL_SIZE}",
    fill=STATION_COLOR,
    pen=f"{STATION_EDGE_WIDTH}p,{STATION_EDGE_COLOR}",
)


# ------------------------------------------------------------
# 8.6 Station labels
# ------------------------------------------------------------

for _, row in df.iterrows():

    fig.text(
        x=row["longitude"],
        y=row["latitude"],
        text=f"{row['network']}.{row['station']}",
        font=(
            f"{STATION_FONT_SIZE}p,"
            "Helvetica-Bold,black"
        ),
        justify="BL",
        offset="0.12c/0.12c",
    )


from io import StringIO

# ------------------------------------------------------------
# Legend
# ------------------------------------------------------------

legend_spec = f"""
S 0.10c - 0.4c - {FAULT_WIDTH}p,{FAULT_COLOR} 0.5c Fault
G 0.02c
S 0.10c t {STATION_SYMBOL_SIZE} {STATION_COLOR} {STATION_EDGE_WIDTH}p,{STATION_EDGE_COLOR} 0.5c Seismic station
"""

legend_file = output_dir / "legend.txt"
legend_file.write_text(legend_spec.strip() + "\n")

with pygmt.config(FONT_ANNOT_PRIMARY="9p,Helvetica,black"):
    fig.legend(
        spec=str(legend_file),
        position=f"j{legend_position}+j{legend_position}+o0.2c+w2.9c",
        box="+gwhite+p0.8p,black+c0.05c",
    )

# ------------------------------------------------------------
# 8.7 Elevation colorbar
# ------------------------------------------------------------

fig.colorbar(
    frame=[
        "xaf",
        "y+lElevation (m)",
    ],
)


# ============================================================
# 9. Save PNG
# ============================================================

fig_file = output_dir / "station_map.png"

fig.savefig(
    str(fig_file),
    dpi=MAP_DPI,
)

print("\n" + "=" * 60)
print("Completed")
print("=" * 60)

print(f"Stations:       {len(df)}")
print(f"Fault features: {len(faults_region)}")
print(f"Fault segments: {n_fault_segments}")
print(f"Resolution:     {resolution}")

print("\nOutput files:")
print(f"Station CSV:    {csv_file}")
print(f"Fault GeoJSON:  {fault_output if not faults_region.empty else 'None'}")
print(f"Map PNG:        {fig_file}")
