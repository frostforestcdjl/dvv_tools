import os
from datetime import datetime
import calendar
from concurrent.futures import ThreadPoolExecutor, as_completed

from obspy import read, UTCDateTime
from obspy.clients.fdsn import Client

client = Client("https://webservices.ingv.it")

# --- parameters ---
network="IV"

station_list = ["EPIT", "EMCN", "EVRN", "EPOZ"]
station_lst = ",".join(station_list)

location_list = [""]

channel_list = ["HHE", "HHN", "HHZ"]

year_list = [2015+i for i in range(12)]

print(f"years for download: {year_list}")

year_today = datetime.now().year
jday_today = datetime.now().timetuple().tm_yday
print(f"Today is jday={jday_today} in {year_today}")


# --- download data ---
def download_one(args):
    year, jday, station, location, channel = args

    starttime = UTCDateTime(year, 1, 1) + (jday - 1) * 86400
    endtime = starttime + 86400

    folder = f"../data/{year}/{network}/{station}/{channel}.D/"
    os.makedirs(folder, exist_ok=True)

    file_name_save = (
        f"{folder}"
        f"{network}.{station}.{location}.{channel}.D."
        f"{year}.{jday:03d}"
    )

    # Skip files already downloaded
    if os.path.exists(file_name_save):
        return (
            f"{network},{station},{location},{channel},"
            f"{year},{jday:03d},Exists"
        )

    try:
        st = client.get_waveforms(
            network,
            station,
            location,
            channel,
            starttime,
            endtime
        )

        st.write(file_name_save, format="MSEED")

        return (
            f"{network},{station},{location},{channel},"
            f"{year},{jday:03d},Done"
        )

    except Exception as e:
        return (
            f"{network},{station},{location},{channel},"
            f"{year},{jday:03d},NotFound,{type(e).__name__}"
        )


# --------------------------------------------------
# Build download list
# --------------------------------------------------

tasks = []

for year in year_list:
    if year == year_today:
        # Download through yesterday
        jday_list = range(1, jday_today)
    else:
        ndays = 366 if calendar.isleap(year) else 365
        jday_list = range(1, ndays + 1)

    for station in station_list:
        for location in location_list:
            for channel in channel_list:
                for jday in jday_list:
                    tasks.append(
                        (year, jday, station, location, channel)
                    )

# --------------------------------------------------
# Parallel download
# --------------------------------------------------

total = len(tasks)
log = []

print(f"Total files: {total}")

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {
        executor.submit(download_one, task): task
        for task in tasks
    }

    for count, future in enumerate(as_completed(futures), 1):

        msg = future.result()
        log.append(msg)

        print(f"({count}/{total}) {msg}")

# --------------------------------------------------
# Save log
# --------------------------------------------------

with open("data_download.log", "w") as f:
    f.write("\n".join(log) + "\n")
