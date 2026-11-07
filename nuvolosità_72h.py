# ============================================================
# McSPARK METEO - FOCUS ITALIA
# MEDIA MULTIMODELLO ECMWF + GFS
# Copertura Nuvolosa Totale (Total Cloud Cover) - Previsione +72h
# ============================================================

import os
import sys
import datetime as dt
from pathlib import Path

import numpy as np
import xarray as xr
import requests

import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature

from PIL import Image
from ecmwf.opendata import Client
import matplotlib
matplotlib.use('Agg')  # Forza il salvataggio senza interfaccia grafica

# ============================================================
# CONFIGURAZIONE (AREA ITALIA)
# ============================================================

LEAD_HOURS = 72

# Focalizzazione sull'area italiana
LON_MIN = 6.0
LON_MAX = 19.0
LAT_MIN = 35.5
LAT_MAX = 47.5

ECMWF_RESOLUTION = "0p25"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "dati_multimodello"
DATA_DIR.mkdir(exist_ok=True)

LOGO_FILE = BASE_DIR / "logo.jpg"
MAX_GFS_ATTEMPTS = 8

# File di output e temporanei aggiornati a 72h
OUTPUT_FILE = BASE_DIR / "copertura_nuvolosa_italia_72h.png"
ECMWF_FILE = DATA_DIR / "ecmwf_tcc_72h.grib2"
GFS_FILE = DATA_DIR / "gfs_tcdc_72h.grib2"

def messaggio(testo):
    print()
    print("=" * 70)
    print(testo)
    print("=" * 70)

def controlla_file(path):
    return path.exists() and path.stat().st_size >= 1000

# ============================================================
# 1. DATA/ORA UTC E DOWNLOAD ECMWF
# ============================================================

now_utc = dt.datetime.now(dt.timezone.utc)
messaggio("RICERCA RUN ECMWF PIÙ RECENTE - COPERTURA NUVOLOSA (+72h)")

ecmwf_client = Client(
    source="ecmwf",
    model="ifs",
    resol=ECMWF_RESOLUTION
)

print("Richiedo ECMWF IFS...")
print("Parametro: Copertura nuvolosa totale (tcc)")
print(f"Lead time: +{LEAD_HOURS} h")

try:
    ecmwf_result = ecmwf_client.retrieve(
        type="fc",
        step=LEAD_HOURS,
        param="tcc",
        target=str(ECMWF_FILE)
    )
except Exception as e:
    print("ERRORE DURANTE IL DOWNLOAD ECMWF:", e)
    sys.exit(1)

if not controlla_file(ECMWF_FILE):
    print("Il file ECMWF non è stato creato correttamente.")
    sys.exit(1)

ecmwf_run_datetime = ecmwf_result.datetime
if ecmwf_run_datetime.tzinfo is None:
    ecmwf_run_datetime = ecmwf_run_datetime.replace(tzinfo=dt.timezone.utc)

valid_time = ecmwf_run_datetime + dt.timedelta(hours=LEAD_HOURS)
print("Run ECMWF:", ecmwf_run_datetime)
print("Validità reale:", valid_time.strftime("%Y-%m-%d %H:%M UTC"))

# ============================================================
# 2. INDIVIDUAZIONE E DOWNLOAD RUN GFS COMPATIBILE
# ============================================================

messaggio("RICERCA RUN GFS COMPATIBILE")

session = requests.Session()
session.headers.update({"User-Agent": "McSpark-Meteo/1.0"})

def gfs_file_url(date_string, cycle, gfs_step):
    return (
        "https://nomads.ncep.noaa.gov/cgi-bin/"
        "filter_gfs_0p25.pl?"
        f"file=gfs.t{cycle:02d}z.pgrb2.0p25.f{gfs_step:03d}"
        "&lev_entire_atmosphere=on"
        "&var_TCDC=on"
        f"&dir=%2Fgfs.{date_string}%2F{cycle:02d}%2Fatmos"
    )

def verifica_gfs_url(url):
    try:
        response = session.head(url, timeout=20, allow_redirects=True)
        if response.status_code == 200:
            return True
        response = session.get(url, timeout=30, stream=True)
        ok = response.status_code == 200
        response.close()
        return ok
    except requests.RequestException:
        return False

gfs_url = None
gfs_run_date = None
gfs_run_cycle = None
gfs_step = None

candidate_base = ecmwf_run_datetime.replace(minute=0, second=0, microsecond=0)

for attempt in range(MAX_GFS_ATTEMPTS):
    candidate = candidate_base - dt.timedelta(hours=6 * attempt)
    date_string = candidate.strftime("%Y%m%d")
    cycle = candidate.hour
    delta = valid_time - candidate
    gfs_step_hours = int(delta.total_seconds() / 3600)

    if gfs_step_hours < 0:
        continue

    print(f"Controllo GFS {date_string} {cycle:02d} UTC +{gfs_step_hours:03d} h...")
    test_url = gfs_file_url(date_string, cycle, gfs_step_hours)

    if verifica_gfs_url(test_url):
        gfs_url = test_url
        gfs_run_date = date_string
        gfs_run_cycle = cycle
        gfs_step = gfs_step_hours
        print(f"\nRUN GFS TROVATO: {date_string} {cycle:02d} UTC (+{gfs_step}h)")
        break

if not gfs_url:
    print("ERRORE: GFS non trovato per la validità richiesta.")
    sys.exit(1)

try:
    resp = session.get(gfs_url, timeout=180)
    resp.raise_for_status()
    with open(GFS_FILE, "wb") as f:
        f.write(resp.content)
except Exception as e:
    print("Errore download GFS:", e)
    sys.exit(1)

# ============================================================
# 3. LETTURA ED ELABORAZIONE DATI NUVOLOSITÀ (%)
# ============================================================

messaggio("LETTURA ED ELABORAZIONE DATI")

ds_ecmwf = xr.open_dataset(ECMWF_FILE, engine="cfgrib")
tcc_e_var = next((v for v in ["tcc", "TCC"] if v in ds_ecmwf), None)
cloud_ecmwf = ds_ecmwf[tcc_e_var]

# Lettura GFS filtrando lo stepType per evitare conflitti
ds_gfs = xr.open_dataset(
    GFS_FILE,
    engine="cfgrib",
    backend_kwargs={'filter_by_keys': {'stepType': 'instant'}}
)
tcc_g_var = next((v for v in ["tcdc", "TCDC", "tcc"] if v in ds_gfs), None)
cloud_gfs = ds_gfs[tcc_g_var]

# Normalizzazione coordinate
def trova_coord(ds, possibili):
    return next((n for n in possibili if n in ds.coords), None)

lat_e, lon_e = trova_coord(ds_ecmwf, ["latitude", "lat"]), trova_coord(ds_ecmwf, ["longitude", "lon"])
lat_g, lon_g = trova_coord(ds_gfs, ["latitude", "lat"]), trova_coord(ds_gfs, ["longitude", "lon"])

cloud_ecmwf = cloud_ecmwf.rename({lat_e: "lat", lon_e: "lon"})
cloud_gfs = cloud_gfs.rename({lat_g: "lat", lon_g: "lon"})

def normalizza_longitudine(da):
    lon = da["lon"]
    return da.assign_coords(lon=((lon + 180) % 360) - 180).sortby("lon")

cloud_ecmwf = normalizza_longitudine(cloud_ecmwf)
cloud_gfs = normalizza_longitudine(cloud_gfs)

# Taglio area Italia
cloud_ecmwf = cloud_ecmwf.sel(lat=slice(LAT_MAX, LAT_MIN), lon=slice(LON_MIN, LON_MAX))
cloud_gfs = cloud_gfs.sel(lat=slice(LAT_MAX, LAT_MIN), lon=slice(LON_MIN, LON_MAX))

# Standardizzazione in percentuale (0-100%)
if float(cloud_ecmwf.max()) <= 1.1:
    cloud_ecmwf = cloud_ecmwf * 100.0
if float(cloud_gfs.max()) <= 1.1:
    cloud_gfs = cloud_gfs * 100.0

cloud_ecmwf.name = "cloud_ecmwf"
cloud_gfs.name = "cloud_gfs"

# Interpolazione GFS su griglia ECMWF e calcolo media multimodello
cloud_gfs_interp = cloud_gfs.interp(lat=cloud_ecmwf["lat"], lon=cloud_ecmwf["lon"], method="linear")
cloud_media = (cloud_ecmwf + cloud_gfs_interp) / 2.0
cloud_media = cloud_media.clip(0, 100)
cloud_media.name = "copertura_nuvolosa_media"
cloud_media.attrs["units"] = "%"

cloud_diff = cloud_ecmwf - cloud_gfs_interp

# Statistiche a terminale
print()
print("STATISTICHE COPERTURA NUVOLOSA (+72h)")
print("-" * 50)
print(f"Minima copertura: {float(cloud_media.min()):.1f} %")
print(f"Massima copertura: {float(cloud_media.max()):.1f} %")
print(f"Scarto medio assoluto ECMWF-GFS: {float(np.abs(cloud_diff).mean()):.2f} %")

ecmwf_run_text = ecmwf_run_datetime.strftime("%d/%m %H UTC")
gfs_run_text = f"{gfs_run_date[6:8]}/{gfs_run_date[4:6]} {gfs_run_cycle:02d} UTC"
valid_text = valid_time.strftime("%d/%m/%Y %H:%M UTC")

# ============================================================
# 4. PLOTTING DELLA MAPPA (FOCUS ITALIA)
# ============================================================

messaggio("CREAZIONE MAPPA COPERTURA NUVOLOSA ITALIA (+72h)")

fig = plt.figure(figsize=(11, 10))
ax = plt.axes(projection=ccrs.PlateCarree())
ax.set_extent([LON_MIN, LON_MAX, LAT_MIN, LAT_MAX], crs=ccrs.PlateCarree())

levels = np.arange(0, 105, 10)

contour_fill = ax.contourf(
    cloud_media["lon"], cloud_media["lat"], cloud_media,
    levels=levels, cmap="Blues", alpha=0.85,
    extend="neither", transform=ccrs.PlateCarree()
)

cbar = plt.colorbar(contour_fill, orientation="horizontal", pad=0.04, shrink=0.75)
cbar.set_label("Copertura Nuvolosa Totale (%) - Previsione +72h", fontsize=10, fontweight="bold")
cbar.ax.tick_params(labelsize=9)

contours = ax.contour(
    cloud_media["lon"], cloud_media["lat"], cloud_media,
    levels=[20, 50, 80], colors="black", linewidths=0.8, alpha=0.6,
    transform=ccrs.PlateCarree()
)
ax.clabel(contours, inline=True, fontsize=8, fmt="%d%%")

ax.coastlines(resolution="10m", linewidth=1.1, color="darkslategray")
ax.add_feature(cfeature.BORDERS, linestyle=":", linewidth=0.8, alpha=0.7)
ax.add_feature(cfeature.LAKES, alpha=0.25)

gl = ax.gridlines(draw_labels=True, linestyle="--", linewidth=0.5, alpha=0.25)
gl.top_labels = False
gl.right_labels = False

plt.title(
    "McSPARK METEO – Copertura Nuvolosa Totale Italia (+72h)\n"
    f"Media multimodello ECMWF + GFS | Validità: {valid_text}",
    fontsize=14, fontweight="bold", pad=15
)

fig.text(
    0.5, 0.03,
    f"ECMWF IFS: {ecmwf_run_text}   |   GFS: {gfs_run_text} (+{gfs_step} h)   |   Linee: media ECMWF + GFS (%)",
    ha="center", fontsize=9
)

TEMP_FILE = DATA_DIR / "copertura_nuvolosa_italia_temp_72h.png"
plt.savefig(TEMP_FILE, dpi=300, bbox_inches="tight", pad_inches=0.3, facecolor="white")
plt.close()

# ============================================================
# 5. INSERIMENTO LOGO E SALVATAGGIO NETCDF
# ============================================================

try:
    base_img = Image.open(TEMP_FILE).convert("RGB")
    logo = Image.open(LOGO_FILE).convert("RGB")
    basewidth = 150
    rapporto = basewidth / float(logo.size[0])
    hsize = int(float(logo.size[1]) * rapporto)
    logo = logo.resize((basewidth, hsize), Image.Resampling.LANCZOS)
    
    img_width, img_height = base_img.size
    logo_width, logo_height = logo.size
    position = (img_width - logo_width - 5, img_height - logo_height - 5)
    base_img.paste(logo, position)
    base_img.save(OUTPUT_FILE, format="PNG")
except FileNotFoundError:
    TEMP_FILE.rename(OUTPUT_FILE)

NETCDF_FILE = DATA_DIR / "media_ECMWF_GFS_Nuvolosita_+72h.nc"
cloud_media.to_dataset(name="copertura_nuvolosa").to_netcdf(NETCDF_FILE, engine="netcdf4")

messaggio("OPERAZIONE COMPLETATA (+72h)")
print("Mappa Copertura Nuvolosa Italia:", OUTPUT_FILE)
print("Dati numerici NetCDF:", NETCDF_FILE)