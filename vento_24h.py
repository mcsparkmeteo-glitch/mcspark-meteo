# ============================================================
# McSPARK METEO
#
# MEDIA MULTIMODELLO ECMWF + GFS
# Vento al Suolo (Area Euro-Atlantica) in km/h - Previsione +24h (Domani)
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
# CONFIGURAZIONE (AREA EURO-ATLANTICA)
# ============================================================

LEAD_HOURS = 24

LON_MIN = -25.0
LON_MAX = 40.0
LAT_MIN = 30.0
LAT_MAX = 72.0

ECMWF_RESOLUTION = "0p25"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "dati_multimodello"
DATA_DIR.mkdir(exist_ok=True)

LOGO_FILE = BASE_DIR / "logo.jpg"

ECMWF_FILE = DATA_DIR / "ecmwf_vento_24h.grib2"
GFS_FILE = DATA_DIR / "gfs_vento_24h.grib2"

OUTPUT_FILE = (
    BASE_DIR /
    f"McSpark_Meteo_Media_ECMWF_GFS_Vento_kmh_+{LEAD_HOURS}h.png"
)

MAX_GFS_ATTEMPTS = 8

def messaggio(testo):
    print()
    print("=" * 70)
    print(testo)
    print("=" * 70)

def controlla_file(path):
    if not path.exists():
        return False
    if path.stat().st_size < 1000:
        return False
    return True

# ============================================================
# 1. DATA/ORA UTC E DOWNLOAD ECMWF
# ============================================================

now_utc = dt.datetime.now(dt.timezone.utc)
messaggio("RICERCA RUN ECMWF PIÙ RECENTE - VENTO (km/h) +24h")

ecmwf_client = Client(
    source="ecmwf",
    model="ifs",
    resol=ECMWF_RESOLUTION
)

print("Richiedo ECMWF IFS (Componenti 10u e 10v)...")
print(f"Lead time: +{LEAD_HOURS} h")

try:
    ecmwf_result = ecmwf_client.retrieve(
        type="fc",
        step=LEAD_HOURS,
        param=["10u", "10v"],
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
        "&lev_10_m_above_ground=on"
        "&var_UGRD=on"
        "&var_VGRD=on"
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
# 3. LETTURA ED ELABORAZIONE DATI (KM/H)
# ============================================================

messaggio("LETTURA ED ELABORAZIONE DATI VENTO")

ds_ecmwf = xr.open_dataset(ECMWF_FILE, engine="cfgrib")

try:
    ds_gfs = xr.open_dataset(GFS_FILE, engine="cfgrib")
except Exception:
    datasets_gfs = xr.open_datasets(GFS_FILE, engine="cfgrib")
    ds_gfs = next((d for d in datasets_gfs if any(v in d.variables for v in ["u10", "UGRD", "u", "10u"])), datasets_gfs[0])

# Conversione m/s -> km/h (* 3.6)
u_e = next(ds_ecmwf[v] for v in ["u10", "10u", "u"] if v in ds_ecmwf)
v_e = next(ds_ecmwf[v] for v in ["v10", "10v", "v"] if v in ds_ecmwf)
wind_ecmwf = np.sqrt(u_e**2 + v_e**2) * 3.6

u_g = next(ds_gfs[v] for v in ["u10", "UGRD", "u", "10u"] if v in ds_gfs)
v_g = next(ds_gfs[v] for v in ["v10", "VGRD", "v", "10v"] if v in ds_gfs)
wind_gfs = np.sqrt(u_g**2 + v_g**2) * 3.6

lat_e = "latitude" if "latitude" in ds_ecmwf.coords else "lat"
lon_e = "longitude" if "longitude" in ds_ecmwf.coords else "lon"
lat_g = "latitude" if "latitude" in ds_gfs.coords else "lat"
lon_g = "longitude" if "longitude" in ds_gfs.coords else "lon"

wind_ecmwf = wind_ecmwf.rename({lat_e: "lat", lon_e: "lon"})
wind_gfs = wind_gfs.rename({lat_g: "lat", lon_g: "lon"})

def normalizza_longitudine(da):
    lon = da["lon"]
    return da.assign_coords(lon=((lon + 180) % 360) - 180).sortby("lon")

wind_ecmwf = normalizza_longitudine(wind_ecmwf)
wind_gfs = normalizza_longitudine(wind_gfs)

wind_ecmwf = wind_ecmwf.sel(lat=slice(LAT_MAX, LAT_MIN), lon=slice(LON_MIN, LON_MAX))
wind_gfs = wind_gfs.sel(lat=slice(LAT_MAX, LAT_MIN), lon=slice(LON_MIN, LON_MAX))

wind_gfs_interp = wind_gfs.interp(lat=wind_ecmwf["lat"], lon=wind_ecmwf["lon"], method="linear")
wind_media = (wind_ecmwf + wind_gfs_interp) / 2.0
wind_media.name = "vento_media"
wind_media.attrs["units"] = "km/h"

wind_diff = wind_ecmwf - wind_gfs_interp

print()
print("STATISTICHE INTENSITÀ VENTO (10m)")
print("-" * 50)
print(f"Minimo vento medio: {float(wind_media.min()):.1f} km/h")
print(f"Massimo vento medio: {float(wind_media.max()):.1f} km/h")
print(f"Scarto medio assoluto ECMWF-GFS: {float(np.abs(wind_diff).mean()):.2f} km/h")

ecmwf_run_text = ecmwf_run_datetime.strftime("%d/%m %H UTC")
gfs_run_text = f"{gfs_run_date[6:8]}/{gfs_run_date[4:6]} {gfs_run_cycle:02d} UTC"
valid_text = valid_time.strftime("%d/%m/%Y %H:%M UTC")

# ============================================================
# 4. PLOTTING MAPPA EURO-ATLANTICA
# ============================================================

messaggio("CREAZIONE MAPPA VENTO EURO-ATLANTICO (+24H)")

fig = plt.figure(figsize=(15, 9))
ax = plt.axes(projection=ccrs.PlateCarree())
ax.set_extent([LON_MIN, LON_MAX, LAT_MIN, LAT_MAX], crs=ccrs.PlateCarree())

levels = np.arange(20, 110, 10)

contour_fill = ax.contourf(
    wind_media["lon"], wind_media["lat"], wind_media,
    levels=levels, cmap="Spectral_r", alpha=0.9,
    extend="max", transform=ccrs.PlateCarree()
)

cbar = plt.colorbar(contour_fill, orientation="horizontal", pad=0.04, shrink=0.65)
cbar.set_label("Intensità Vento a 10m (km/h) - Previsione +24h", fontsize=10, fontweight="bold")
cbar.ax.tick_params(labelsize=9)

contours = ax.contour(
    wind_media["lon"], wind_media["lat"], wind_media,
    levels=[30, 50, 70, 90], colors="black", linewidths=1.1, alpha=0.8,
    transform=ccrs.PlateCarree()
)
ax.clabel(contours, inline=True, fontsize=9, fmt="%d km/h")

ax.coastlines(resolution="50m", linewidth=0.9, color="darkslategray")
ax.add_feature(cfeature.BORDERS, linestyle=":", linewidth=0.7, alpha=0.7)
ax.add_feature(cfeature.LAKES, alpha=0.25)

gl = ax.gridlines(draw_labels=True, linestyle="--", linewidth=0.5, alpha=0.25)
gl.top_labels = False
gl.right_labels = False

plt.title(
    "McSPARK METEO – Vento al Suolo (Euro-Atlantico)\n"
    f"Media multimodello ECMWF + GFS | +24h (Domani)\n"
    f"Validità: {valid_text}",
    fontsize=14, fontweight="bold", pad=15
)

fig.text(
    0.5, 0.03,
    f"ECMWF IFS: {ecmwf_run_text}   |   GFS: {gfs_run_text} (+{gfs_step} h)   |   Linee: media ECMWF + GFS (km/h)",
    ha="center", fontsize=9
)

TEMP_FILE = DATA_DIR / "mappa_vento_24h_temp.png"
plt.savefig(TEMP_FILE, dpi=300, bbox_inches="tight", pad_inches=0.3, facecolor="white")
plt.close()

# ============================================================
# 5. INSERIMENTO LOGO E SALVATAGGIO FINALE
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

NETCDF_FILE = DATA_DIR / f"media_ECMWF_GFS_Vento_kmh_+{LEAD_HOURS}h.nc"
wind_media.to_dataset(name="vento_media").to_netcdf(NETCDF_FILE, engine="netcdf4")

messaggio("OPERAZIONE COMPLETATA")
print("Mappa Vento 24h Euro-Atlantico:", OUTPUT_FILE)
print("Dati numerici NetCDF:", NETCDF_FILE)