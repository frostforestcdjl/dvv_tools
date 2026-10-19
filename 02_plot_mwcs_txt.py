import os
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from msnoise.api import connect, get_filters

# --- 1. Retrive msnoise database to get filters ---
try:
    db = connect()
    filters = get_filters(db, all=True)

    mwcs_low_dic = {f.ref: f.mwcs_low for f in filters}
    mwcs_high_dic = {f.ref: f.mwcs_high for f in filters}

    db.close()
except:
    mwcs_low_dic = {1:0.1}
    mwcs_high_dic = {1:0.9}

print("mwcs_low_dic =", mwcs_low_dic)
print("mwcs_high_dic =", mwcs_high_dic)

# --- 2. Custom colormap for delay (same as color_bar.py / mwcs_colorbar.png): yellow at zero ---
colors = [
    (0.00, "#000080"),  # Dark blue
    (0.15, "#0000FF"),  # Blue
    (0.30, "#00FFFF"),  # Cyan
    (0.40, "#00FF00"),  # Green
    (0.50, "#FFFF00"),  # Yellow (0)
    (0.70, "#FFA500"),  # Orange
    (1.00, "#FF0000"),  # Red
]

cmap_mwcs = LinearSegmentedColormap.from_list(
    "custom_rainbow",
    colors,
    N=256
)

# --- 3. Plot Setting for each value column (column 2, 3, 4 of the txt files) ---
# key: column index in txt file (0 = lag-time window)
# symmetric=True  -> colorbar is [-vlim, vlim] centered at 0, vlim taken directly from 'v_lim_list' (diverging cmap)
# symmetric=False -> colorbar is [vmin, vmin + (vmax - vmin) * rescale], rescale from 'v_max_rescale_list' (sequential cmap)
# swap=True       -> also plot a version with x (Date) and y (Lag-Time) swapped, saved as *_swap_*.png
column_setting = {
    1: {'name': 'delay',     'label': 'Delay (s)',      'cmap': cmap_mwcs, 'symmetric': True,  'v_lim_list': [0.1, 0.2, 0.5, 1, 2], 'swap': True},
    2: {'name': 'error',     'label': 'Error (s)',      'cmap': 'viridis', 'symmetric': False, 'v_max_rescale_list': [0.1, 0.5, 1]},
    3: {'name': 'coherence', 'label': 'Mean Coherence', 'cmap': 'viridis', 'symmetric': False, 'v_max_rescale_list': [1]},
}

# --- 4. Functions ---
def get_dirs(folder):
    return [
        name for name in os.listdir(folder)
        if os.path.isdir(os.path.join(folder, name))
        and not name.startswith(".")
    ]

def load_mwcs_txt(pair_folder):
    txt_files = sorted(f for f in os.listdir(pair_folder) if f.endswith(".txt") and not f.startswith("."))

    date_dt_mwcs = []
    data_list = []
    t_mwcs = None
    for fname in txt_files:
        data = np.loadtxt(os.path.join(pair_folder, fname), ndmin=2)
        if t_mwcs is None:
            t_mwcs = data[:, 0]
        elif data.shape[0] != len(t_mwcs) or not np.allclose(data[:, 0], t_mwcs):
            print(f"  Skip {fname}: lag-time windows differ from the first file")
            continue
        date_str = fname.removesuffix(".txt")
        date_dt_mwcs.append(datetime.strptime(date_str, "%Y-%m-%d"))
        data_list.append(data)

    # shape: (n_days, n_windows, 4)
    data = np.array(data_list)
    MWCS_dic = {d: data[i] for i, d in enumerate(date_dt_mwcs)}

    print(f"MWCS_dic length: {len(MWCS_dic)}, t_mwcs length: {len(t_mwcs)}")

    return date_dt_mwcs, MWCS_dic, t_mwcs

def build_daily_grid(date_dt_mwcs, MWCS_dic, col, npts):
    """Resample one column onto a fully-populated calendar-day grid (missing days = NaN).

    This keeps every real day's values as its own flat, non-interpolated column
    (no blending across neighboring days) while making the time axis uniform,
    so pcolormesh renders data gaps as genuinely blank instead of stretching
    the surrounding days across the gap.
    """
    start = date_dt_mwcs[0]
    end = date_dt_mwcs[-1]
    n_days = (end - start).days + 1
    all_days = [start + timedelta(days=i) for i in range(n_days)]

    grid = np.full((n_days, npts), np.nan)
    for date in date_dt_mwcs:
        grid[(date - start).days] = MWCS_dic[date][:, col]

    return all_days, grid

def plot_mwcs_txt(date_dt_mwcs, MWCS_dic, t_mwcs, station_pair, filter_name, component, pair_folder_root, column_setting):
    save_path = pair_folder_root.replace('MWCS', 'img/MWCS')
    os.makedirs(save_path, exist_ok=True)

    for col, setting in column_setting.items():
        all_days, grid = build_daily_grid(date_dt_mwcs, MWCS_dic, col, len(t_mwcs))

        vmin_data = np.nanmin(grid)
        vmax_data = np.nanmax(grid)
        print(f"  [{setting['name']}] vmin: {vmin_data}, vmax: {vmax_data}")

        v_list = setting['v_lim_list'] if setting['symmetric'] else setting['v_max_rescale_list']
        for v in v_list:
            if setting['symmetric']:
                norm = TwoSlopeNorm(vmin=-v, vcenter=0, vmax=v)
                extend = 'both'
            else:
                norm = plt.Normalize(vmin=vmin_data, vmax=vmin_data + (vmax_data - vmin_data) * v)
                extend = 'neither'

            swap_list = [False, True] if setting.get('swap', False) else [False]
            for swap in swap_list:
                if not swap:
                    # x: Date, y: Lag-Time
                    fig, ax_mesh = plt.subplots(1, 1, figsize=(14, 4), constrained_layout=True)
                    mesh = ax_mesh.pcolormesh(all_days, t_mwcs, grid.T, cmap=setting['cmap'], shading='auto',
                                              norm=norm)
                    ax_mesh.set_xlim([date_dt_mwcs[0], date_dt_mwcs[-1]])
                    ax_mesh.set_ylim([t_mwcs[0], t_mwcs[-1]])
                    ax_mesh.set_xlabel('Date', fontsize=16)
                    ax_mesh.set_ylabel('Lag-Time (s)', fontsize=16)
                    fig_name = f"{station_pair}_{setting['name']}_{v}.png"
                else:
                    # x: Lag-Time, y: Date
                    fig, ax_mesh = plt.subplots(1, 1, figsize=(8, 10), constrained_layout=True)
                    mesh = ax_mesh.pcolormesh(t_mwcs, all_days, grid, cmap=setting['cmap'], shading='auto',
                                              norm=norm)
                    ax_mesh.set_xlim([t_mwcs[0], t_mwcs[-1]])
                    ax_mesh.set_ylim([date_dt_mwcs[0], date_dt_mwcs[-1]])
                    ax_mesh.set_xlabel('Lag-Time (s)', fontsize=16)
                    ax_mesh.set_ylabel('Date', fontsize=16)
                    fig_name = f"{station_pair}_{setting['name']}_swap_{v}.png"

                cbar = fig.colorbar(mesh, ax=ax_mesh, pad=0.01, extend=extend)
                cbar.set_label(setting['label'], fontsize=14)
                cbar.ax.tick_params(labelsize=12)

                ax_mesh.tick_params(axis='both', labelsize=14)
                ax_mesh.set_title(f"MWCS {setting['name']} ({station_pair}, {mwcs_low_dic[filter_name]}-{mwcs_high_dic[filter_name]} Hz) [{component}]")

                plt.savefig(f"{save_path}/{fig_name}", dpi=300)
                plt.close()
                # plt.show()


# --- 5. Setting and Running for Plot ---
mwcs_folder = 'MWCS'
filter_list = get_dirs(mwcs_folder)

for filter_name in filter_list:
    filter_folder = os.path.join(mwcs_folder, filter_name)
    stack_day_list = get_dirs(filter_folder)
    for stack_day in stack_day_list:
        stack_day_folder = os.path.join(filter_folder, stack_day)
        component_list = get_dirs(stack_day_folder)
        for component in component_list:
            pair_folder_root = os.path.join(stack_day_folder, component)
            pair_list = get_dirs(pair_folder_root)

            for pair in pair_list:
                print(f"Ploting with {filter_name} | {stack_day} | {component} | {pair}")
                pair_folder = os.path.join(pair_folder_root, pair)
                station_pair = pair
                date_dt_mwcs, MWCS_dic, t_mwcs = load_mwcs_txt(pair_folder)
                if not date_dt_mwcs:
                    print("  No txt files, skip")
                    continue
                plot_mwcs_txt(date_dt_mwcs, MWCS_dic, t_mwcs, station_pair, int(filter_name), component, pair_folder_root, column_setting)
