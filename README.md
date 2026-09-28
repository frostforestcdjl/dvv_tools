# dv/v Tools

A collection of tools for downloading seismic data, plotting cross-correlation functions (CCFs), and visualizing dv/v results.

## 0. Download Seismic Data

1. Place `00_download_data_italy.sh` in an empty folder. Make sure at least **1 TB of free disk space** is available.

2. Run:

   ```bash
   sh 00_download_data_italy.sh
   ```

3. Have a cup of coffee ☕ and wait approximately **20–30 hours** for the download to finish.

After processing the downloaded data with **MSNoise**, you should have `STACKS`, `MWCS`, and `DTT` folder containing the dv/v results.

## 1. Plot CCFs from MiniSEED or Zarr Files

Depending on your data format in `STACKS`, download one of the following scripts:

- `01_plot_ccfs_mseed.py` — for MiniSEED files
- `01_plot_ccfs_zarr.py` — for Zarr files

Place the script in the same folder as `STACKS`, then run it with Python. For example:

```bash
python 01_plot_ccfs_mseed.py
```

or:

```bash
python 01_plot_ccfs_zarr.py
```

## 2. Load DTT Data and Plot dv/v

Download the Jupyter notebook:

`02_load_dt_plot_dvv.ipynb`

Open and run the notebook to load data from the `DTT` folder and plot the dv/v results.
