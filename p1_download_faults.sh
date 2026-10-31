#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Configuration
# ============================================================

# Directory containing this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# USGS Quaternary Fault Database
URL="https://earthquake.usgs.gov/static/lfs/nshm/qfaults/Qfaults_GIS.zip"

# Output directories
OUTPUT_DIR="$SCRIPT_DIR/data_geo/faults"
ZIP_FILE="$OUTPUT_DIR/Qfaults_GIS.zip"

# ============================================================
# 1. Create output directory
# ============================================================

mkdir -p "$OUTPUT_DIR"

# ============================================================
# 2. Download fault database
# ============================================================

echo "Downloading USGS Quaternary Fault Database..."

curl -fL --retry 3 \
    "$URL" \
    -o "$ZIP_FILE"

echo "Download completed: $ZIP_FILE"

# ============================================================
# 3. Unzip fault database
# ============================================================

echo "Extracting fault database..."

unzip -o "$ZIP_FILE" -d "$OUTPUT_DIR"

echo "Extraction completed!"

# ============================================================
# 4. Remove ZIP file
# ============================================================

rm -f "$ZIP_FILE"

echo "ZIP file removed."

# ============================================================
# 5. Download station scanner
# ============================================================
curl -fL -o $OUTPUT_DIR_SCRIPT/p1_scan_available_stations.py "https://raw.githubusercontent.com/frostforestcdjl/download_data_italy/main/p1_scan_available_stations.py"

# ============================================================
# 6. Finished
# ============================================================

echo "============================================================"
echo "USGS fault database downloaded and extracted successfully!"
echo "Output directory: $OUTPUT_DIR"
echo "============================================================"
