#!/bin/bash

mkdir -p msnoise_italy/src
mkdir -p msnoise_italy/data

cd msnoise_italy/src || exit 1

curl -fL -o 00_download_mseed_italy.py "https://raw.githubusercontent.com/frostforestcdjl/download_data_italy/main/00_download_mseed_italy.py"
curl -fL -o 01_plot_ccfs_mseed.py "https://raw.githubusercontent.com/frostforestcdjl/download_data_italy/main/01_plot_ccfs_mseed.py"
curl -fL -o 01a_scan_available_ccf.py "https://raw.githubusercontent.com/frostforestcdjl/download_data_italy/main/01a_scan_available_ccf.py"
curl -fL -o 02_plot_mwcs_txt.py "https://raw.githubusercontent.com/frostforestcdjl/download_data_italy/main/02_plot_mwcs_txt.py"
curl -fL -o 03_load_dtt_plot_dvv.ipynb "https://raw.githubusercontent.com/frostforestcdjl/download_data_italy/main/03_load_dtt_plot_dvv.ipynb"
curl -fL -o 04_plot_dvv.py "https://raw.githubusercontent.com/frostforestcdjl/download_data_italy/main/04_plot_dvv.py"

curl -fL -o 03a_convert_dtt_to_dvv.py "https://raw.githubusercontent.com/frostforestcdjl/download_data_italy/main/03a_convert_dtt_to_dvv.py"

# --- downlaod examples folder ---
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/frostforestcdjl/download_data_italy.git /tmp/download_data_italy
  
git -C /tmp/download_data_italy sparse-checkout set examples
cp -r /tmp/download_data_italy/examples .
rm -rf /tmp/download_data_italy

# --- download data ---
python 00_download_mseed_italy.py
