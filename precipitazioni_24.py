# ============================================================
# McSPARK METEO
# PRECIPITAZIONI CUMULATE A 24 ORE (GIORNATA SOLARE 00-24 UTC)
# ECMWF IFS + GFS NOAA/NCEP
#
# Calcolo dinamico degli step:
# - Rileva l'ora del run ECMWF disponibile (00 UTC o 06 UTC)
# - Calcola lo step di inizio (00:00 del giorno successivo)
#   e lo step di fine (00:00 di due giorni dopo)
# - Esegue la sottrazione (step_fine - step_inizio) su entrambi
#   i modelli per isolare esattamente le 24 ore solari
# ============================================================

import os
import sys
import requests
import numpy as np
import xarray as xr
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import cartopy.crs as ccrs
import cartopy.feature as cfeature

# ECMWF Open Data
from ecmwf.opendata import Client


# ============================================================
# CONFIGURAZIONE
# ============================================================

# Area Italia
LON_MIN = 6
LON_MAX = 19
LAT_MIN = 35
LAT_MAX = 48

# Directory
OUT_DIR = "precipitazioni_multimodello"
os.makedirs(OUT_DIR, exist_ok=True)

ECMWF_FILE = os.path.join(OUT_DIR, "ecmwf_tp_24h_solare.grib2")
GFS_FILE_START = os.path.join(OUT_DIR, "gfs_apcp_start.grib2")
GFS_FILE_END = os.path.join(OUT_DIR, "gfs_apcp_end.grib2")
OUTPUT_PNG = os.path.join(OUT_DIR, "precipitazioni_24h_ECMWF_GFS.png")


# ============================================================
# FUNZIONI
# ============================================================

def normalize_longitude(ds):
    """Porta le longitudini nel formato -180/+180 e ordina la griglia."""
    if "longitude" in ds.coords:
        lon = ds.longitude
        if float(lon.max()) > 180:
            ds = ds.assign_coords(longitude=((lon + 180) % 360) - 180)
            ds = ds.sortby("longitude")
    elif "lon" in ds.coords:
        lon = ds.lon
        if float(lon.max()) > 180:
            ds = ds.assign_coords(lon=((lon + 180) % 360) - 180)
            ds = ds.sortby("lon")
    return ds


def get_lat_lon(ds):
    if "latitude" in ds.coords:
        return "latitude", "longitude"
    elif "lat" in ds.coords:
        return "lat", "lon"
    else:
        raise ValueError("Coordinate lat/lon non riconosciute.")


def clip_area(ds):
    lat_name, lon_name = get_lat_lon(ds)
    lat = ds[lat_name]
    if lat[0] < lat[-1]:
        return ds.sel({lat_name: slice(LAT_MIN, LAT_MAX), lon_name: slice(LON_MIN, LON_MAX)})
    else:
        return ds.sel({lat_name: slice(LAT_MAX, LAT_MIN), lon_name: slice(LON_MIN, LON_MAX)})


def download_gfs_step(gfs_date, gfs_cycle, step_hours, out_path):
    """Scarica un singolo step APCP da NOMADS GFS 0.25."""
    base_url = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
    file_name = f"gfs.t{gfs_cycle}z.pgrb2.0p25.f{step_hours:03d}"
    params = {
        "dir": f"/gfs.{gfs_date}/{gfs_cycle}/atmos",
        "file": file_name,
        "lev_surface": "on",
        "var_APCP": "on"
    }
    url = base_url + "?" + urlencode(params)
    print(f"Scarico GFS step +{step_hours:03d}h ({file_name})...")
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        print(f"\nERRORE durante il download GFS (+{step_hours}h):", e)
        sys.exit(1)

    if len(resp.content) < 10000:
        print(f"\nERRORE: file GFS (+{step_hours}h) incompleto o non ancora disponibile.")
        print("URL:", url)
        sys.exit(1)

    with open(out_path, "wb") as f:
        f.write(resp.content)
    print(f"OK ({len(resp.content) / 1024 / 1024:.1f} MB)")


def read_gfs_apcp(grib_path):
    """Legge la variabile APCP dal file GRIB GFS."""
    ds = xr.open_dataset(grib_path, engine="cfgrib")
    for candidate in ["tp", "apcp", "unknown"]:
        if candidate in ds.data_vars:
            da = ds[candidate]
            units = str(da.attrs.get("units", "")).lower()
            if "kg" in units or "mm" in units:
                return da
            else:
                raise ValueError(f"Unità GFS non riconosciute: {units}")
    raise ValueError("Variabile APCP non trovata nel file GFS.")


# ============================================================
# 1. ECMWF IFS OPEN DATA (RILEVAMENTO RUN E CALCOLO FINESTRA 24H)
# ============================================================

print("\n==============================================")
print(" ECMWF IFS OPEN DATA (ACCUMULO 24H SOLARE)")
print("==============================================")

client = Client(source="ecmwf")

# Step preliminare per conoscere esattamente il run ECMWF attivo
TEMP_TEST = os.path.join(OUT_DIR, "ecmwf_test_run.grib2")
try:
    res_test = client.retrieve(
        type="fc",
        stream="oper",
        levtype="sfc",
        param="tp",
        step=24,
        target=TEMP_TEST
    )
except Exception as e:
    print("\nERRORE ECMWF DI TEST:", e)
    sys.exit(1)

ecmwf_run_datetime = res_test.datetime
if ecmwf_run_datetime.tzinfo is None:
    ecmwf_run_datetime = ecmwf_run_datetime.replace(tzinfo=timezone.utc)

# Finestra solare: dalle 00:00 UTC del giorno dopo alle 00:00 UTC di due giorni dopo
target_day_start = datetime.combine(
    ecmwf_run_datetime.date() + timedelta(days=1),
    datetime.min.time(),
    tzinfo=timezone.utc
)
target_day_end = target_day_start + timedelta(hours=24)

step_start = int((target_day_start - ecmwf_run_datetime).total_seconds() / 3600)
step_end = int((target_day_end - ecmwf_run_datetime).total_seconds() / 3600)

print(f"Run ECMWF rilevato : {ecmwf_run_datetime.strftime('%Y-%m-%d %H:%M UTC')}")
print(f"Finestra accumulo  : {target_day_start.strftime('%d/%m/%Y %H:%M')} -> {target_day_end.strftime('%d/%m/%Y %H:%M UTC')}")
print(f"Step calcolati     : +{step_start}h (inizio) e +{step_end}h (fine)")

print("\nScarico file ECMWF con entrambi gli step...")
try:
    client.retrieve(
        type="fc",
        stream="oper",
        levtype="sfc",
        param="tp",
        step=[step_start, step_end],
        target=ECMWF_FILE
    )
except Exception as e:
    print("\nERRORE DOWNLOAD ECMWF:", e)
    sys.exit(1)


# ============================================================
# 2. GFS NOAA/NCEP (SCARICO ENTRAMBI GLI STEP)
# ============================================================

print("\n==============================================")
print(" GFS NOAA/NCEP")
print("==============================================")

gfs_run = ecmwf_run_datetime
gfs_date = gfs_run.strftime("%Y%m%d")
gfs_cycle = gfs_run.strftime("%H")

print(f"Run GFS target: {gfs_run.strftime('%Y-%m-%d %H:%M UTC')}")
download_gfs_step(gfs_date, gfs_cycle, step_start, GFS_FILE_START)
download_gfs_step(gfs_date, gfs_cycle, step_end, GFS_FILE_END)


# ============================================================
# 3. LETTURA E SOTTRAZIONE (STEP_END - STEP_START)
# ============================================================

print("\n==============================================")
print(" ELABORAZIONE ACCUMULO 24 ORE")
print("==============================================")

# --- ECMWF ---
ds_ecmwf = xr.open_dataset(ECMWF_FILE, engine="cfgrib")
if "tp" not in ds_ecmwf:
    print("\nERRORE: variabile 'tp' non trovata nel GRIB ECMWF.")
    sys.exit(1)

tp_ecmwf_all = ds_ecmwf["tp"] * 1000.0  # metri -> mm

# Seleziona gli step lungo la dimensione 'step'
step_dim = next((d for d in tp_ecmwf_all.dims if "step" in d), None)
if step_dim is None or tp_ecmwf_all.sizes[step_dim] < 2:
    print("\nERRORE: il dataset ECMWF non contiene entrambi gli step richiesti.")
    sys.exit(1)

tp_ecmwf_start = tp_ecmwf_all.isel({step_dim: 0})
tp_ecmwf_end = tp_ecmwf_all.isel({step_dim: 1})
tp_ecmwf_24h = tp_ecmwf_end - tp_ecmwf_start
tp_ecmwf_24h.name = "precipitation_24h"

# --- GFS ---
# Nota: nel GFS, APCP a step f024 o f048 può essere cumulato dall'inizio del run
# oppure su finestre da 6h a seconda del parametro nel GRIB.
# Verifichiamo startStep per decidere se sottrarre o sommare.
apcp_start_raw = read_gfs_apcp(GFS_FILE_START)
apcp_end_raw = read_gfs_apcp(GFS_FILE_END)

start_step_attr = apcp_end_raw.attrs.get("GRIB_startStep", 0)
if float(start_step_attr) == 0.0:
    # Cumulato dall'inizio del run (0 -> step_end)
    apcp_gfs_24h = apcp_end_raw - apcp_start_raw
    print("GFS: accumulo continuo rilevato, eseguo sottrazione (end - start).")
else:
    # Se GFS fornisce bucket a 6h, scarichiamo tutti gli step intermedi
    print("GFS: rilevati bucket parziali, scarico gli step intermedi ogni 6h...")
    intermediate_steps = list(range(step_start + 6, step_end + 1, 6))
    apcp_gfs_24h = xr.zeros_like(apcp_end_raw)
    for st in intermediate_steps:
        tmp_f = os.path.join(OUT_DIR, f"gfs_apcp_f{st:03d}.grib2")
        download_gfs_step(gfs_date, gfs_cycle, st, tmp_f)
        apcp_gfs_24h = apcp_gfs_24h + read_gfs_apcp(tmp_f)

apcp_gfs_24h.name = "precipitation_24h"


# ============================================================
# 4. NORMALIZZAZIONE, CLIP E INTERPOLAZIONE
# ============================================================

tp_ecmwf_24h = clip_area(normalize_longitude(tp_ecmwf_24h))
apcp_gfs_24h = clip_area(normalize_longitude(apcp_gfs_24h))

# Pulizia piccoli negativi dovuti ad arrotondamenti GRIB
tp_ecmwf_24h = xr.where(tp_ecmwf_24h < 0, 0, tp_ecmwf_24h)
apcp_gfs_24h = xr.where(apcp_gfs_24h < 0, 0, apcp_gfs_24h)

lat_ecmwf, lon_ecmwf = get_lat_lon(tp_ecmwf_24h)
lat_gfs, lon_gfs = get_lat_lon(apcp_gfs_24h)

apcp_gfs_interp = apcp_gfs_24h.interp(
    {
        lat_gfs: tp_ecmwf_24h[lat_ecmwf],
        lon_gfs: tp_ecmwf_24h[lon_ecmwf]
    },
    method="linear"
)

# Media multimodello
precip_mean = (tp_ecmwf_24h + apcp_gfs_interp) / 2.0
precip_mean.name = "multimodel_precipitation_24h"

print("\n----------------------------------------------")
print(" RISULTATI ACCUMULO 24 ORE")
print("----------------------------------------------")
print(f"ECMWF : {float(tp_ecmwf_24h.min()):.1f} -> {float(tp_ecmwf_24h.max()):.1f} mm")
print(f"GFS   : {float(apcp_gfs_interp.min()):.1f} -> {float(apcp_gfs_interp.max()):.1f} mm")
print(f"MEDIA : {float(precip_mean.min()):.1f} -> {float(precip_mean.max()):.1f} mm")


# ============================================================
# 5. MAPPA CON PALETTE PROFESSIONALE E COSTE NERE
# ============================================================

print("\nCreo la mappa...")

fig = plt.figure(figsize=(12, 10))
ax = plt.axes(projection=ccrs.PlateCarree())
ax.set_extent([LON_MIN, LON_MAX, LAT_MIN, LAT_MAX], crs=ccrs.PlateCarree())

# Soglie in millimetri (mm)
levels = [0.1, 1, 3, 5, 10, 15, 20, 30, 45, 60, 100, 150, 200]

# Palette professionale multi-colore
colors_list = [
    "#b8f3ff", # 0.1 - 1 mm (Celeste chiaro)
    "#82dcf8", # 1 - 3 mm (Celeste)
    "#46b4e6", # 3 - 5 mm (Celeste scuro)
    "#1e82dc", # 5 - 10 mm (Blu)
    "#005ac8", # 10 - 15 mm (Blu profondo)
    "#00a000", # 15 - 20 mm (Verde)
    "#50f050", # 20 - 30 mm (Verde chiaro)
    "#f0f000", # 30 - 45 mm (Giallo)
    "#ffc800", # 45 - 60 mm (Arancione chiaro)
    "#ff7800", # 60 - 100 mm (Arancione / Rosso)
    "#e11400", # 100 - 150 mm (Rosso vivo)
    "#960032", # 150 - 200 mm (Bordeaux / Viola)
    "#640064"  # > 200 mm (Viola scuro)
]

cmap = mcolors.ListedColormap(colors_list)
cmap.set_under("white", alpha=0)
cmap.set_over("#320032", alpha=1)

norm = mcolors.BoundaryNorm(levels, ncolors=cmap.N, clip=False)

lon = tp_ecmwf_24h[lon_ecmwf]
lat = tp_ecmwf_24h[lat_ecmwf]

mesh = ax.contourf(
    lon,
    lat,
    precip_mean,
    levels=levels,
    cmap=cmap,
    norm=norm,
    extend="max",
    transform=ccrs.PlateCarree(),
    alpha=0.9
)

# ============================================================
# 6. GEOGRAFIA (COSTE E CONFINI IN NERO)
# ============================================================

ax.add_feature(
    cfeature.COASTLINE,
    linewidth=1.1,
    edgecolor="black"
)

ax.add_feature(
    cfeature.BORDERS,
    linewidth=0.8,
    edgecolor="black"
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
# 7. COLORBAR E TESTI
# ============================================================

cbar = plt.colorbar(
    mesh,
    ax=ax,
    orientation="vertical",
    pad=0.02,
    shrink=0.85,
    ticks=levels
)

cbar.set_label(
    "Precipitazione cumulata 24 h (mm)",
    fontsize=11,
    fontweight="bold"
)
cbar.ax.tick_params(labelsize=8.5)

run_text = ecmwf_run_datetime.strftime("%d/%m/%Y %H UTC")
day_label = target_day_start.strftime("%d/%m/%Y")
valid_range_text = f"00:00 - 24:00 UTC del {day_label}"

ax.set_title(
    f"McSPARK METEO - Precipitazioni cumulate 24 ore ({day_label})\n"
    "Media multimodello ECMWF IFS + GFS",
    fontsize=13,
    fontweight="bold",
    pad=15
)

ax.text(
    0.5,
    -0.055,
    f"Run ECMWF: {run_text}   |   Run GFS: {run_text}   |   Accumulo: {valid_range_text} (+{step_start}h / +{step_end}h)",
    transform=ax.transAxes,
    ha="center",
    va="top",
    fontsize=9
)

# ============================================================
# 8. GRID E SALVATAGGIO
# ============================================================

gl = ax.gridlines(
    draw_labels=True,
    linewidth=0.4,
    alpha=0.4,
    linestyle="--"
)
gl.top_labels = False
gl.right_labels = False

plt.tight_layout()
plt.savefig(OUTPUT_PNG, dpi=180, bbox_inches="tight")

if not os.environ.get("CI"):
    plt.show()

plt.close()

# ============================================================
# 9. SALVATAGGIO NETCDF
# ============================================================

OUTPUT_NC = os.path.join(OUT_DIR, "precipitazioni_multimodello_24h.nc")
precip_mean.to_dataset().to_netcdf(OUTPUT_NC)

print("\n==============================================")
print(" ELABORAZIONE COMPLETATA")
print("==============================================")
print(f"Mappa salvata in : {OUTPUT_PNG}")
print(f"NetCDF salvato in: {OUTPUT_NC}")
print(f"Periodo coperto  : {valid_range_text}")
