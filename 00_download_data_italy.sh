#!/bin/bash

mkdir -p msnoise_italy/src
mkdir -p msnoise_italy/data

cd msnoise_italy/src || exit 1

curl -fL -o 00_download_mseed_italy.py "https://raw.githubusercontent.com/frostforestcdjl/download_data_italy/main/00_download_mseed_italy.py"
curl -fL -o 01_plot_ccfs_mseed.py "https://raw.githubusercontent.com/frostforestcdjl/download_data_italy/main/01_plot_ccfs_mseed.py"
curl -fL -o 02_plot_mwcs_txt.py "https://raw.githubusercontent.com/frostforestcdjl/download_data_italy/main/02_plot_mwcs_txt.py"
curl -fL -o 03_load_dtt_plot_dvv.ipynb "https://raw.githubusercontent.com/frostforestcdjl/download_data_italy/main/03_load_dtt_plot_dvv.ipynb"

python 00_download_mseed_italy.py
