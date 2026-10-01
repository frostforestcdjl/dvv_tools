import os
import zarr
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import numpy as np

mwcs_low_dic = {1:0.1}
mwcs_high_dic = {1:0.9}
v_max_rescale_list = [0.01, 0.1, 0.5, 1, 10]

def get_dirs(folder):
    return [
        name for name in os.listdir(folder)
        if os.path.isdir(os.path.join(folder, name))
        and not name.startswith(".")
    ]

def load_ccf_zfile(pair_list):
    z_file = zarr.open(pair_list, mode='r')

    try:
        date = z_file['date'][:]
        data = z_file['data'][:]
        reference = z_file['reference'][:]
    
        try:
            date_dt_cctorch = [datetime.strptime(str(d), '%Y%m%d') for d in date]
        except:
            date_dt_cctorch = [datetime.strptime(str(d), '%Y%j') for d in date]
    
        CCF_dic_cctorch = {d: data[i] for i, d in enumerate(date_dt_cctorch)}
    
        npts = data.shape[1]
        t_cctorch = (np.arange(npts) - npts // 2) / 20
    
        vmin = np.min(data)
        vmax = np.max(data)
        vmax_cctorch = max(abs(vmin), abs(vmax))
    
        print(f"CCF_dic_cctorch length: {len(CCF_dic_cctorch)}, t_cctorch length: {len(t_cctorch)}, vmin: {vmin}, vmax: {vmax}, vmax_cctorch: {vmax_cctorch}")

        return date_dt_cctorch, CCF_dic_cctorch, t_cctorch, vmax_cctorch, reference

    except Exception as e:
        print(f"Error loading {pair_list}: {e}")
        return None, None, None, None, None

def build_daily_grid(date_dt_cctorch, CCF_dic_cctorch, npts):
    """Resample onto a fully-populated calendar-day grid (missing days = NaN).

    This keeps every real day's CCF as its own flat, non-interpolated column
    (no blending across neighboring days) while making the time axis uniform,
    so pcolormesh renders data gaps as genuinely blank instead of stretching
    the surrounding days across the gap.
    """
    start = date_dt_cctorch[0]
    end = date_dt_cctorch[-1]
    n_days = (end - start).days + 1
    all_days = [start + timedelta(days=i) for i in range(n_days)]

    grid = np.full((n_days, npts), np.nan)
    for date in date_dt_cctorch:
        grid[(date - start).days] = CCF_dic_cctorch[date]

    return all_days, grid

def plot_ccf_zfile(date_dt_cctorch, CCF_dic_cctorch, t_cctorch, vmax_cctorch, reference, station_pair, filter_name, component, z_folder, v_max_rescale_list):
    all_days, grid = build_daily_grid(date_dt_cctorch, CCF_dic_cctorch, len(t_cctorch))

    for v_max_rescale in v_max_rescale_list:
        vlim = vmax_cctorch * v_max_rescale

        fig, (ax_mesh, ax_ref) = plt.subplots(
            1, 2, figsize=(14, 4), sharey=True,
            gridspec_kw={'width_ratios': [5, 1]},
            constrained_layout=True,
        )

        ax_mesh.pcolormesh(all_days, t_cctorch, grid.T, cmap='seismic', shading='auto',
                            vmin=-vlim, vmax=vlim)

        ax_mesh.tick_params(axis='both', labelsize=14)
        ax_mesh.set_xlim([date_dt_cctorch[0], date_dt_cctorch[-1]])
        ax_mesh.set_ylim([-70, 70])
        ax_mesh.set_xlabel('Date', fontsize=16)
        ax_mesh.set_ylabel('Lag-Time (s)', fontsize=16)
        ax_mesh.set_title(f"CCF from CCTorch ({station_pair}, {mwcs_low_dic[filter_name]}-{mwcs_high_dic[filter_name]} Hz) [{component}]")

        # Reference CCF, sharing the same lag-time (y) axis as the pcolormesh.
        ax_ref.plot(reference, t_cctorch, color='k', linewidth=0.8)
        ax_ref.axvline(0, color='gray', linewidth=0.5)
        ax_ref.set_xlim(-vlim, vlim)
        ax_ref.set_xlabel('Reference', fontsize=16)
        ax_ref.tick_params(axis='x', labelsize=14)
        ax_ref.tick_params(axis='y', labelleft=False)

        save_path = z_folder.replace('STACKS', 'img/STACKS')
        os.makedirs(save_path, exist_ok=True)
        plt.savefig(f"{save_path}/{station_pair}_{v_max_rescale}.png", dpi=300)
        plt.close()
        # plt.show()
    



stack_folder = 'STACKS'
filter_list = get_dirs(stack_folder)

for filter_name in filter_list:
    filter_folder = os.path.join(stack_folder, filter_name)
    stack_day_list = get_dirs(filter_folder)
    for stack_day in stack_day_list:
        stack_day_folder = os.path.join(filter_folder, stack_day)
        component_list = get_dirs(stack_day_folder)
        for component in component_list:
            z_folder = os.path.join(stack_day_folder, component)
            pair_list = [pair for pair in get_dirs(z_folder) if pair.endswith(".zarr")]

            for pair in pair_list:
                z_file = os.path.join(z_folder, pair)
                station_pair = pair.removesuffix(".zarr")
                date_dt_cctorch, CCF_dic_cctorch, t_cctorch, vmax_cctorch, reference = load_ccf_zfile(z_file)
                plot_ccf_zfile(date_dt_cctorch, CCF_dic_cctorch, t_cctorch, vmax_cctorch, reference, station_pair, int(filter_name), component, z_folder, v_max_rescale_list)


