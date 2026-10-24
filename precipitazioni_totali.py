# ============================================================
# McSpark Meteo
# PRECIPITAZIONI CUMULATE A 72 ORE
# ECMWF IFS + GFS NOAA/NCEP
#
# Confronto multimodello:
# - stesso ciclo di inizializzazione
# - stesso istante di validità
# - accumulo 0-72 h
#
# Python / Anaconda
# ============================================================

import os
import sys
import requests
import numpy as np
import xarray as xr
import matplotlib.pyplot as plt

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.io.shapereader import natural_earth

# ECMWF Open Data
from ecmwf.opendata import Client


# ============================================================
# CONFIGURAZIONE
# ============================================================

LEAD_HOURS = 72

# Area Italia
LON_MIN = 6
LON_MAX = 19
LAT_MIN = 35
LAT_MAX = 48

# Directory
OUT_DIR = "precipitazioni_multimodello"
os.makedirs(OUT_DIR, exist_ok=True)

ECMWF_FILE = os.path.join(
    OUT_DIR,
    "ecmwf_tp_72h.grib2"
)

GFS_FILE = os.path.join(
    OUT_DIR,
    "gfs_apcp_72h.grib2"
)

OUTPUT_PNG = os.path.join(
    OUT_DIR,
    "precipitazioni_72h_ECMWF_GFS.png"
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

    lat_name, lon_name = get_lat_lon(ds)

    lat = ds[lat_name]

    # Gestisce sia latitudini crescenti sia decrescenti
    if lat[0] < lat[-1]:
        ds = ds.sel(
            {
                lat_name: slice(LAT_MIN, LAT_MAX),
                lon_name: slice(LON_MIN, LON_MAX)
            }
        )
    else:
        ds = ds.sel(
            {
                lat_name: slice(LAT_MAX, LAT_MIN),
                lon_name: slice(LON_MIN, LON_MAX)
            }
        )

    return ds


# ============================================================
# 1. ECMWF IFS OPEN DATA
# ============================================================

print("\n==============================================")
print(" ECMWF IFS OPEN DATA")
print("==============================================")

client = Client(source="ecmwf")

print("Richiedo ultima corsa ECMWF disponibile...")

try:

    ecmwf_result = client.retrieve(
        type="fc",
        stream="oper",
        levtype="sfc",
        param="tp",
        step=LEAD_HOURS,
        target=ECMWF_FILE
    )

except Exception as e:

    print("\nERRORE ECMWF:")
    print(e)
    sys.exit(1)


# ------------------------------------------------------------
# Data/ora della corsa ECMWF
# ------------------------------------------------------------

ecmwf_run_datetime = ecmwf_result.datetime

if ecmwf_run_datetime.tzinfo is None:
    ecmwf_run_datetime = ecmwf_run_datetime.replace(
        tzinfo=timezone.utc
    )

valid_time = (
    ecmwf_run_datetime
    + timedelta(hours=LEAD_HOURS)
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
    f"Lead time : +{LEAD_HOURS} h"
)


# ============================================================
# 2. GFS NOAA/NCEP
#
# IMPORTANTISSIMO:
# cerchiamo ESATTAMENTE lo stesso run ECMWF.
# ============================================================

print("\n==============================================")
print(" GFS NOAA/NCEP")
print("==============================================")

gfs_run = ecmwf_run_datetime.replace(
    tzinfo=timezone.utc
)

gfs_date = gfs_run.strftime("%Y%m%d")
gfs_cycle = gfs_run.strftime("%H")

gfs_step = LEAD_HOURS


# URL NOMADS
base_url = (
    "https://nomads.ncep.noaa.gov/cgi-bin/"
    "filter_gfs_0p25.pl"
)

file_name = (
    f"gfs.t{gfs_cycle}z.pgrb2.0p25.f"
    f"{gfs_step:03d}"
)

params = {
    "dir": f"/gfs.{gfs_date}/{gfs_cycle}/atmos",
    "file": file_name,

    "lev_surface": "on",
    "var_APCP": "on"
}

gfs_url = (
    base_url
    + "?"
    + urlencode(params)
)

print(
    f"Run GFS   : "
    f"{gfs_run.strftime('%Y-%m-%d %H:%M UTC')}"
)

print(
    f"Validità  : "
    f"{valid_time.strftime('%Y-%m-%d %H:%M UTC')}"
)

print(
    f"Lead time : +{gfs_step} h"
)

print("\nVerifico disponibilità GFS...")

try:

    response = requests.get(
        gfs_url,
        timeout=60
    )

    response.raise_for_status()

except Exception as e:

    print("\nERRORE durante il collegamento al GFS:")
    print(e)
    sys.exit(1)


# ------------------------------------------------------------
# Controllo minimo del file
# ------------------------------------------------------------

if len(response.content) < 10000:

    print(
        "\nERRORE: il file GFS ricevuto "
        "sembra incompleto o non disponibile."
    )

    print("\nURL richiesto:")
    print(gfs_url)

    sys.exit(1)


with open(GFS_FILE, "wb") as f:
    f.write(response.content)

print(
    f"GFS scaricato: "
    f"{len(response.content) / 1024 / 1024:.1f} MB"
)


# ============================================================
# 3. LETTURA ECMWF
# ============================================================

print("\n==============================================")
print(" LETTURA DATI")
print("==============================================")

try:

    ds_ecmwf = xr.open_dataset(
        ECMWF_FILE,
        engine="cfgrib"
    )

except Exception as e:

    print("\nErrore lettura ECMWF:")
    print(e)
    sys.exit(1)


print("\nVariabili ECMWF:")
print(list(ds_ecmwf.data_vars))


# ------------------------------------------------------------
# Individuazione TP
# ------------------------------------------------------------

if "tp" not in ds_ecmwf:

    print(
        "\nERRORE: variabile 'tp' "
        "non trovata nel GRIB ECMWF."
    )

    sys.exit(1)


tp_ecmwf = ds_ecmwf["tp"]


# ============================================================
# 4. CONTROLLO METADATI ECMWF
# ============================================================

print("\n----------------------------------------------")
print(" METADATI ECMWF TP")
print("----------------------------------------------")

print("Unità:", tp_ecmwf.attrs.get("units"))

print(
    "step:",
    tp_ecmwf.attrs.get("GRIB_stepType")
)

print(
    "stepRange:",
    tp_ecmwf.attrs.get("GRIB_stepRange")
)

print(
    "startStep:",
    tp_ecmwf.attrs.get("GRIB_startStep")
)

print(
    "endStep:",
    tp_ecmwf.attrs.get("GRIB_endStep")
)


# ============================================================
# 5. CONVERSIONE ECMWF
# ============================================================

tp_ecmwf_mm = tp_ecmwf * 1000.0

tp_ecmwf_mm.name = "precipitation_72h"


# ============================================================
# 6. LETTURA GFS
# ============================================================

try:

    ds_gfs = xr.open_dataset(
        GFS_FILE,
        engine="cfgrib"
    )

except Exception as e:

    print("\nErrore lettura GFS:")
    print(e)
    sys.exit(1)


print("\nVariabili GFS:")
print(list(ds_gfs.data_vars))


# ------------------------------------------------------------
# Trova la variabile APCP
# ------------------------------------------------------------

gfs_var = None

if "tp" in ds_gfs.data_vars:
    gfs_var = "tp"

elif "apcp" in ds_gfs.data_vars:
    gfs_var = "apcp"

elif "unknown" in ds_gfs.data_vars:
    gfs_var = "unknown"


if gfs_var is None:

    print(
        "\nERRORE: non riesco a individuare "
        "APCP nel file GFS."
    )

    sys.exit(1)


apcp_gfs = ds_gfs[gfs_var]


# ============================================================
# 7. CONTROLLO METADATI GFS
# ============================================================

print("\n----------------------------------------------")
print(" METADATI GFS APCP")
print("----------------------------------------------")

print("Variabile:", gfs_var)

print(
    "Unità:",
    apcp_gfs.attrs.get("units")
)

print(
    "stepType:",
    apcp_gfs.attrs.get("GRIB_stepType")
)

print(
    "stepRange:",
    apcp_gfs.attrs.get("GRIB_stepRange")
)

print(
    "startStep:",
    apcp_gfs.attrs.get("GRIB_startStep")
)

print(
    "endStep:",
    apcp_gfs.attrs.get("GRIB_endStep")
)


# ============================================================
# 8. CONTROLLO CRITICO: IL GFS DEVE ESSERE UN ACCUMULO 0-72 H
# ============================================================

step_range = apcp_gfs.attrs.get(
    "GRIB_stepRange"
)

start_step = apcp_gfs.attrs.get(
    "GRIB_startStep"
)

end_step = apcp_gfs.attrs.get(
    "GRIB_endStep"
)


print("\nControllo intervallo accumulo GFS...")


duration_hours = None


if start_step is not None and end_step is not None:

    try:

        duration_hours = (
            float(end_step)
            - float(start_step)
        )

    except Exception:
        pass


elif step_range is not None:

    try:

        if "-" in str(step_range):

            parts = str(step_range).split("-")

            duration_hours = (
                float(parts[-1])
                - float(parts[0])
            )

    except Exception:
        pass


print(
    "Durata accumulo GFS:",
    duration_hours,
    "ore"
)


if duration_hours is not None:

    if abs(duration_hours - LEAD_HOURS) > 0.1:

        print(
            "\nERRORE: l'APCP GFS non rappresenta "
            f"un accumulo di {LEAD_HOURS} ore."
        )

        print(
            "Durata trovata:",
            duration_hours,
            "ore"
        )

        print(
            "\nLa media multimodello NON viene "
            "calcolata."
        )

        sys.exit(1)


# ============================================================
# 9. GFS IN mm
# ============================================================

units_gfs = str(
    apcp_gfs.attrs.get("units", "")
).lower()


if (
    "kg" in units_gfs
    or "mm" in units_gfs
):

    apcp_gfs_mm = apcp_gfs

else:

    print(
        "\nATTENZIONE: unità GFS non riconosciute:"
    )

    print(
        apcp_gfs.attrs.get("units")
    )

    print(
        "Non effettuo conversioni automatiche."
    )

    sys.exit(1)


apcp_gfs_mm.name = "precipitation_72h"


# ============================================================
# 10. NORMALIZZAZIONE LONGITUDINI
# ============================================================

tp_ecmwf_mm = normalize_longitude(
    tp_ecmwf_mm
)

apcp_gfs_mm = normalize_longitude(
    apcp_gfs_mm
)


# ============================================================
# 11. CLIP AREA ITALIANA
# ============================================================

tp_ecmwf_mm = clip_area(
    tp_ecmwf_mm
)

apcp_gfs_mm = clip_area(
    apcp_gfs_mm
)


# ============================================================
# 12. CONTROLLO VALORI
# ============================================================

print("\n----------------------------------------------")
print(" CONTROLLO DATI")
print("----------------------------------------------")

print(
    "ECMWF:",
    float(tp_ecmwf_mm.min()),
    "→",
    float(tp_ecmwf_mm.max()),
    "mm"
)

print(
    "GFS:",
    float(apcp_gfs_mm.min()),
    "→",
    float(apcp_gfs_mm.max()),
    "mm"
)


tp_ecmwf_mm = xr.where(
    tp_ecmwf_mm < 0,
    0,
    tp_ecmwf_mm
)

apcp_gfs_mm = xr.where(
    apcp_gfs_mm < 0,
    0,
    apcp_gfs_mm
)


# ============================================================
# 13. INTERPOLAZIONE GFS SULLA GRIGLIA ECMWF
# ============================================================

print("\nInterpolazione GFS sulla griglia ECMWF...")

lat_ecmwf, lon_ecmwf = get_lat_lon(
    tp_ecmwf_mm
)

lat_gfs, lon_gfs = get_lat_lon(
    apcp_gfs_mm
)


apcp_gfs_interp = apcp_gfs_mm.interp(
    {
        lat_gfs: tp_ecmwf_mm[lat_ecmwf],
        lon_gfs: tp_ecmwf_mm[lon_ecmwf]
    },
    method="linear"
)


# ============================================================
# 14. MEDIA MULTIMODELLO
# ============================================================

print("\nCalcolo media ECMWF + GFS...")

precip_mean = (
    tp_ecmwf_mm
    + apcp_gfs_interp
) / 2.0

precip_mean.name = "multimodel_precipitation_72h"


# ============================================================
# 15. CONTROLLO FINALE
# ============================================================

print("\n----------------------------------------------")
print(" RISULTATI")
print("----------------------------------------------")

print(
    "ECMWF:",
    f"{float(tp_ecmwf_mm.min()):.1f}",
    "→",
    f"{float(tp_ecmwf_mm.max()):.1f}",
    "mm"
)

print(
    "GFS:",
    f"{float(apcp_gfs_interp.min()):.1f}",
    "→",
    f"{float(apcp_gfs_interp.max()):.1f}",
    "mm"
)

print(
    "MEDIA:",
    f"{float(precip_mean.min()):.1f}",
    "→",
    f"{float(precip_mean.max()):.1f}",
    "mm"
)


# ============================================================
# 16. MAPPA (Con scala colori più scura e definita)
# ============================================================

print("\nCreo la mappa...")

from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm

fig = plt.figure(
    figsize=(12, 10)
)

ax = plt.axes(
    projection=ccrs.PlateCarree()
)

ax.set_extent(
    [
        LON_MIN,
        LON_MAX,
        LAT_MIN,
        LAT_MAX
    ],
    crs=ccrs.PlateCarree()
)

# Livelli precipitazione
levels = [
    0.2, 1, 3, 5, 10, 15, 20, 30, 40, 50, 70, 100, 150, 200
]

# Personalizzazione della palette Blues: partiamo da 0.35 per avere azzurri subito decisi
base_cmap = plt.get_cmap("Blues")
colors = base_cmap(np.linspace(0.35, 1.0, len(levels) - 1))
cmap = LinearSegmentedColormap.from_list("custom_blues", colors)

norm = BoundaryNorm(levels, ncolors=cmap.N, clip=True)

lon = tp_ecmwf_mm[lon_ecmwf]
lat = tp_ecmwf_mm[lat_ecmwf]

mesh = ax.contourf(
    lon,
    lat,
    precip_mean,
    levels=levels,
    cmap=cmap,
    norm=norm,
    extend="max",
    transform=ccrs.PlateCarree()
)


# ============================================================
# 17. GEOGRAFIA
# ============================================================

ax.add_feature(
    cfeature.COASTLINE,
    linewidth=1.0
)

ax.add_feature(
    cfeature.BORDERS,
    linewidth=0.7
)

ax.add_feature(
    cfeature.LAKES,
    alpha=0.3
)

ax.add_feature(
    cfeature.RIVERS,
    alpha=0.3
)


# ============================================================
# 18. COLORBAR
# ============================================================

cbar = plt.colorbar(
    mesh,
    ax=ax,
    orientation="vertical",
    pad=0.02,
    shrink=0.85
)

cbar.set_label(
    "Precipitazione cumulata 72 h (mm)",
    fontsize=11
)


# ============================================================
# 19. TITOLO
# ============================================================

run_text = ecmwf_run_datetime.strftime(
    "%d/%m/%Y %H UTC"
)

valid_text = valid_time.strftime(
    "%d/%m/%Y %H UTC"
)


ax.set_title(
    "Mc Spark Meteo PRECIPITAZIONI CUMULATE 72 ORE\n"
    "Media multimodello ECMWF IFS + GFS",
    fontsize=15,
    fontweight="bold",
    pad=25
)


ax.text(
    0.5,
    1.02,
    (
        f"Run: {run_text}   |   "
        f"Validità: {valid_text}   |   "
        f"Accumulo: 0–72 h"
    ),
    transform=ax.transAxes,
    ha="center",
    va="bottom",
    fontsize=10
)


# ============================================================
# 20. GRID
# ============================================================

gl = ax.gridlines(
    draw_labels=True,
    linewidth=0.4,
    alpha=0.4,
    linestyle="--"
)

gl.top_labels = False
gl.right_labels = False


# ============================================================
# 21. SALVATAGGIO
# ============================================================

plt.tight_layout()

plt.savefig(
    OUTPUT_PNG,
    dpi=180,
    bbox_inches="tight"
)

plt.show()


# ============================================================
# 22. SALVATAGGIO NETCDF
# ============================================================

OUTPUT_NC = os.path.join(
    OUT_DIR,
    "precipitazioni_multimodello_72h.nc"
)


precip_mean.to_dataset().to_netcdf(
    OUTPUT_NC
)


# ============================================================
# FINE
# ============================================================

print("\n==============================================")
print(" ELABORAZIONE COMPLETATA")
print("==============================================")

print(
    "\nMappa:",
    OUTPUT_PNG
)

print(
    "NetCDF:",
    OUTPUT_NC
)

print(
    "\nRun comune:",
    ecmwf_run_datetime.strftime(
        "%Y-%m-%d %H UTC"
    )
)

print(
    "Validità:",
    valid_time.strftime(
        "%Y-%m-%d %H UTC"
    )
)

print(
    "Accumulo: 0–72 ore"
)

print(
    "\nMedia multimodello ECMWF + GFS calcolata "
    "solo con lo stesso ciclo."
)