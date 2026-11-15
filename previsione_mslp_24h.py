# ============================================================
# McSpark Meteo
# PRESSIONE AL LIVELLO DEL MARE (MSLP)
# ECMWF IFS + GFS NOAA/NCEP
#
# Confronto multimodello:
# - stessa validità
# - preferibilmente stesso ciclo di inizializzazione
# - lead time ECMWF = +36 h (ore 12:00 UTC del giorno dopo)
#
# Il GFS viene cercato automaticamente.
# Se il medesimo ciclo ECMWF non è disponibile su NOMADS,
# viene utilizzato il ciclo GFS precedente disponibile,
# mantenendo comunque la stessa identica validità.
#
# Python / Anaconda
# ============================================================


import os
import sys
import time
import requests
import numpy as np
import xarray as xr
import matplotlib.pyplot as plt

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import cartopy.crs as ccrs
import cartopy.feature as cfeature

# ECMWF Open Data
from ecmwf.opendata import Client


# ============================================================
# CONFIGURAZIONE
# ============================================================

# Lead time ECMWF impostato a 36 ore (ore 12:00 del giorno dopo)
LEAD_HOURS_ECMWF = 36

# Area Italia
LON_MIN = 6
LON_MAX = 19
LAT_MIN = 35
LAT_MAX = 48

# Directory di lavoro
OUT_DIR = "mslp_multimodello"
os.makedirs(OUT_DIR, exist_ok=True)

# File ECMWF aggiornati a 36h
ECMWF_FILE = os.path.join(
    OUT_DIR,
    "ecmwf_msl_36h.grib2"
)

# File GFS aggiornati a 36h
GFS_FILE = os.path.join(
    OUT_DIR,
    "gfs_prmsl_36h.grib2"
)

# Output
OUTPUT_PNG = os.path.join(
    OUT_DIR,
    "mslp_36h_ECMWF_GFS.png"
)


# ============================================================
# FUNZIONI
# ============================================================

def normalize_longitude(ds):
    """
    Porta le longitudini nel formato -180/+180
    e ordina la griglia.
    """

    if "longitude" in ds.coords:

        lon = ds.longitude

        if float(lon.max()) > 180:

            ds = ds.assign_coords(
                longitude=((lon + 180) % 360) - 180
            )

            ds = ds.sortby("longitude")

    elif "lon" in ds.coords:

        lon = ds.lon

        if float(lon.max()) > 180:

            ds = ds.assign_coords(
                lon=((lon + 180) % 360) - 180
            )

            ds = ds.sortby("lon")

    return ds


def get_lat_lon(ds):
    """
    Individua automaticamente i nomi delle coordinate
    di latitudine e longitudine.
    """

    if "latitude" in ds.coords:

        lat_name = "latitude"
        lon_name = "longitude"

    elif "lat" in ds.coords:

        lat_name = "lat"
        lon_name = "lon"

    else:

        raise ValueError(
            "Coordinate lat/lon non riconosciute."
        )

    return lat_name, lon_name


def clip_area(ds):
    """
    Ritaglia il dataset sull'area italiana.
    Gestisce sia latitudini crescenti sia decrescenti.
    """

    lat_name, lon_name = get_lat_lon(ds)

    lat = ds[lat_name]

    if float(lat[0]) < float(lat[-1]):

        ds = ds.sel(
            {
                lat_name: slice(
                    LAT_MIN,
                    LAT_MAX
                ),

                lon_name: slice(
                    LON_MIN,
                    LON_MAX
                )
            }
        )

    else:

        ds = ds.sel(
            {
                lat_name: slice(
                    LAT_MAX,
                    LAT_MIN
                ),

                lon_name: slice(
                    LON_MIN,
                    LON_MAX
                )
            }
        )

    return ds


# ============================================================
# 1. ECMWF IFS OPEN DATA
# ============================================================

print("\n==============================================")
print(" ECMWF IFS OPEN DATA (MSL)")
print("==============================================")

client = Client(source="ecmwf")

print(
    "Richiedo ultima corsa ECMWF disponibile (+36h)..."
)

try:

    ecmwf_result = client.retrieve(
        type="fc",
        stream="oper",
        levtype="sfc",
        param="msl",
        step=LEAD_HOURS_ECMWF,
        target=ECMWF_FILE
    )

except Exception as e:

    print("\nERRORE ECMWF:")
    print(e)

    sys.exit(1)


# ------------------------------------------------------------
# Run ECMWF
# ------------------------------------------------------------

ecmwf_run_datetime = ecmwf_result.datetime

if ecmwf_run_datetime.tzinfo is None:

    ecmwf_run_datetime = (
        ecmwf_run_datetime.replace(
            tzinfo=timezone.utc
        )
    )

else:

    ecmwf_run_datetime = (
        ecmwf_run_datetime.astimezone(
            timezone.utc
        )
    )


# ------------------------------------------------------------
# Validità ECMWF
# ------------------------------------------------------------

valid_time = (
    ecmwf_run_datetime
    + timedelta(hours=LEAD_HOURS_ECMWF)
)


print(
    f"Run ECMWF : "
    f"{ecmwf_run_datetime.strftime('%Y-%m-%d %H:%M UTC')}"
)

print(
    f"Validità  : "
    f"{valid_time.strftime('%Y-%m-%d %H:%M UTC')}"
)

print(
    f"Lead time : "
    f"+{LEAD_HOURS_ECMWF} h"
)


# ============================================================
# 2. GFS NOAA/NCEP
# ============================================================

print("\n==============================================")
print(" GFS NOAA/NCEP (PRESSIONE AL LIVELLO DEL MARE)")
print("==============================================")


# ============================================================
# CICLI GFS
# ============================================================

GFS_CYCLES = [0, 6, 12, 18]


# ------------------------------------------------------------
# Costruiamo i candidati GFS.
# ------------------------------------------------------------

candidate_runs = []

for hours_back in range(0, 25, 6):

    candidate_time = (
        ecmwf_run_datetime
        - timedelta(hours=hours_back)
    )

    candidate_cycle = candidate_time.hour

    if candidate_cycle in GFS_CYCLES:

        candidate_runs.append(
            candidate_time.replace(
                minute=0,
                second=0,
                microsecond=0
            )
        )


candidate_runs = list(
    dict.fromkeys(candidate_runs)
)


# ============================================================
# PARAMETRI NOMADS
# ============================================================

base_url = (
    "https://nomads.ncep.noaa.gov/"
    "cgi-bin/filter_gfs_0p25.pl"
)


success = False

gfs_run = None
gfs_valid_time = None
gfs_lead_hours = None


# Numero massimo di tentativi per ciascun run
MAX_RETRIES = 3

# Attesa tra tentativi
RETRY_DELAY = 10


# ============================================================
# RICERCA AUTOMATICA DEL RUN GFS
# ============================================================

for candidate_run in candidate_runs:

    candidate_lead = (
        valid_time - candidate_run
    ).total_seconds() / 3600

    candidate_lead = int(round(candidate_lead))

    if candidate_lead < 0:
        continue

    if candidate_lead > 384:
        continue

    gfs_date = candidate_run.strftime(
        "%Y%m%d"
    )

    gfs_cycle = candidate_run.strftime(
        "%H"
    )

    file_name = (
        f"gfs.t{gfs_cycle}z."
        f"pgrb2.0p25."
        f"f{candidate_lead:03d}"
    )

    params = {

        "dir":
            f"/gfs.{gfs_date}/"
            f"{gfs_cycle}/atmos",

        "file":
            file_name,

        "var_PRMSL":
            "on",

        "lev_mean_sea_level":
            "on",

        "leftlon":
            str(LON_MIN),

        "rightlon":
            str(LON_MAX),

        "toplat":
            str(LAT_MAX),

        "bottomlat":
            str(LAT_MIN)
    }

    gfs_url = (
        base_url
        + "?"
        + urlencode(params)
    )

    print("\n----------------------------------------------")
    print("Provo run GFS:")
    print(f"  {candidate_run.strftime('%Y-%m-%d %H UTC')}")
    print(f"Lead GFS necessario: +{candidate_lead} h")
    print(f"File: {file_name}")

    run_success = False

    for attempt in range(1, MAX_RETRIES + 1):

        print(f"Tentativo {attempt}/{MAX_RETRIES}...")

        try:

            response = requests.get(
                gfs_url,
                timeout=120
            )

            response.raise_for_status()
            content = response.content

            if len(content) < 5000:
                print("Risposta troppo piccola.")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                continue

            if not content.startswith(b"GRIB"):
                print("La risposta ricevuta non sembra un file GRIB valido.")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                continue

            with open(GFS_FILE, "wb") as f:
                f.write(content)

            print("\nGFS scaricato con successo.")
            print(f"Dimensione: {len(content) / 1024 / 1024:.2f} MB")

            gfs_run = candidate_run
            gfs_lead_hours = candidate_lead
            gfs_valid_time = (
                gfs_run
                + timedelta(hours=gfs_lead_hours)
            )

            success = True
            run_success = True
            break

        except Exception as e:
            print(f"Errore durante il download: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    if run_success:
        break


# ============================================================
# CONTROLLO FINALE GFS
# ============================================================

if not success:
    print("\nERRORE CRITICO GFS: Nessun run GFS valido trovato.")
    sys.exit(1)


# ============================================================
# VERIFICA DELLA VALIDITÀ
# ============================================================

if gfs_valid_time != valid_time:
    print(f"\nERRORE: ECMWF ({valid_time}) e GFS ({gfs_valid_time}) non hanno la stessa validità.")
    sys.exit(1)

print("\nOK: ECMWF e GFS hanno la stessa identica validità.")


# ============================================================
# 3. LETTURA DATI E CALCOLO MEDIA
# ============================================================

print("\n==============================================")
print(" LETTURA ED ELABORAZIONE DATI")
print("==============================================")

ds_ecmwf = xr.open_dataset(ECMWF_FILE, engine="cfgrib")
msl_ecmwf_hpa = ds_ecmwf["msl"] / 100.0
msl_ecmwf_hpa.name = "mslp"

ds_gfs = xr.open_dataset(GFS_FILE, engine="cfgrib")
gfs_var = "prmsl" if "prmsl" in ds_gfs.data_vars else ("msl" if "msl" in ds_gfs.data_vars else "unknown")
msl_gfs = ds_gfs[gfs_var]

units_gfs = str(msl_gfs.attrs.get("units", "")).lower()
msl_gfs_hpa = (msl_gfs / 100.0) if ("pa" in units_gfs and "hpa" not in units_gfs) else msl_gfs
msl_gfs_hpa.name = "mslp"

msl_ecmwf_hpa = normalize_longitude(msl_ecmwf_hpa)
msl_gfs_hpa = normalize_longitude(msl_gfs_hpa)

msl_ecmwf_hpa = clip_area(msl_ecmwf_hpa)
msl_gfs_hpa = clip_area(msl_gfs_hpa)

lat_ecmwf, lon_ecmwf = get_lat_lon(msl_ecmwf_hpa)
lat_gfs, lon_gfs = get_lat_lon(msl_gfs_hpa)

msl_gfs_interp = msl_gfs_hpa.interp(
    {
        lat_gfs: msl_ecmwf_hpa[lat_ecmwf],
        lon_gfs: msl_ecmwf_hpa[lon_ecmwf]
    },
    method="linear"
)

msl_mean = (msl_ecmwf_hpa + msl_gfs_interp) / 2.0
msl_mean.name = "multimodel_mslp"


# ============================================================
# 7. MAPPA MSLP (Aggiornata a ore 12:00)
# ============================================================

fig = plt.figure(figsize=(12, 10))
ax = plt.axes(projection=ccrs.PlateCarree())
ax.set_extent([LON_MIN, LON_MAX, LAT_MIN, LAT_MAX], crs=ccrs.PlateCarree())

levels_fill = np.arange(990, 1045, 2)
levels_contour = np.arange(990, 1045, 4)
cmap = plt.get_cmap("YlGnBu_r", len(levels_fill) - 1)

lon = msl_ecmwf_hpa[lon_ecmwf]
lat = msl_ecmwf_hpa[lat_ecmwf]

mesh = ax.contourf(
    lon, lat, msl_mean,
    levels=levels_fill, cmap=cmap, extend="both",
    transform=ccrs.PlateCarree(), alpha=0.75
)

contours = ax.contour(
    lon, lat, msl_mean,
    levels=levels_contour, colors="darkblue", linewidths=0.9,
    transform=ccrs.PlateCarree()
)
ax.clabel(contours, inline=True, fmt="%d hPa", fontsize=8)

ax.add_feature(cfeature.COASTLINE, linewidth=1.0)
ax.add_feature(cfeature.BORDERS, linewidth=0.7)
ax.add_feature(cfeature.LAKES, alpha=0.3)
ax.add_feature(cfeature.RIVERS, alpha=0.3)

gl = ax.gridlines(draw_labels=True, linewidth=0.4, alpha=0.4, linestyle="--")
gl.top_labels = False
gl.right_labels = False

cbar = plt.colorbar(mesh, ax=ax, orientation="vertical", pad=0.02, shrink=0.85)
cbar.set_label("Pressione al Livello del Mare - MSLP (hPa)", fontsize=11)

run_ecmwf_text = ecmwf_run_datetime.strftime("%d/%m/%Y %H UTC")
run_gfs_text = gfs_run.strftime("%d/%m/%Y %H UTC")
valid_text = valid_time.strftime("%d/%m/%Y %H UTC")

ax.set_title(
    "McSpark Meteo PRESSIONE AL LIVELLO DEL MARE (MSLP) - ORE 12:00 UTC\n"
    "Media multimodello ECMWF IFS + GFS",
    fontsize=15, fontweight="bold", pad=25
)

ax.text(
    0.5, 1.02,
    f"ECMWF: {run_ecmwf_text}   |   GFS: {run_gfs_text}   |   Validità: {valid_text}",
    transform=ax.transAxes, ha="center", va="bottom", fontsize=9.5
)

ax.text(
    0.5, -0.055,
    f"Lead ECMWF: +{LEAD_HOURS_ECMWF} h   |   Lead GFS: +{gfs_lead_hours} h",
    transform=ax.transAxes, ha="center", va="top", fontsize=9
)

plt.tight_layout()
plt.savefig(OUTPUT_PNG, dpi=180, bbox_inches="tight")

if not os.environ.get("CI"):
    plt.show()

plt.close()

print("\n==============================================")
print(" ELABORAZIONE MSLP (36H) COMPLETATA")
print("==============================================")
print(f"Mappa salvata in: {OUTPUT_PNG}")
