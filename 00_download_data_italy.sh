#!/bin/bash

mkdir -p msnoise_italy/src
mkdir -p msnoise_italy/data

cd msnoise_italy/src || exit 1

curl -fL -o 00_download_mseed_italy.py "https://raw.githubusercontent.com/frostforestcdjl/download_data_italy/main/00_download_mseed_italy.py"

python 00_download_mseed_italy.py
