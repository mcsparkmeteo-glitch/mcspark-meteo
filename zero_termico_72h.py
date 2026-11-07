# ============================================================
# McSPARK METEO - FOCUS ITALIA
# MEDIA MULTIMODELLO ECMWF + GFS
# Zero Termico (Quota Isoterma 0 °C) - Previsione +72h
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

# Restringiamo l'area geografica focalizzandoci sull'Italia
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
OUTPUT_FILE = BASE_DIR / "zero_termico_italia_72h.png"
ECMWF_FILE = DATA_DIR / "ecmwf_pl_72h.grib2"
GFS_FILE = DATA_DIR / "gfs_zero_72h.grib2"

def messaggio(testo):
    print()
    print("=" * 70)
    print(testo)
    print("=" * 70)

def controlla_file(path):
    return path.exists() and path.stat().st_size >= 1000

# ============================================================
# 1. DATA/ORA UTC E DOWNLOAD ECMWF (LIVELLI DI PRESSIONE)
# ============================================================

now_utc = dt.datetime.now(dt.timezone.utc)
messaggio("RICERCA RUN ECMWF PIÙ RECENTE - ZERO TERMICO (+72h)")

ecmwf_client = Client(
    source="ecmwf",
    model="ifs",
    resol=ECMWF_RESOLUTION
)

print("Richiedo ECMWF IFS (Livelli di pressione per calcolo zero termico)...")
print(f"Lead time: +{LEAD_HOURS} h")

try:
    ecmwf_result = ecmwf_client.retrieve(
        type="fc",
        step=LEAD_HOURS,
        levtype="pl",
        levelist=[1000, 925, 850, 700, 600, 500],
        param=["t", "gh"],
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
        "&lev_0C_isotherm=on"
        "&var_HGT=on"
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
# 3. ELABORAZIONE ZERO TERMICO ECMWF DA PROFILO VERTICALE
# ============================================================

messaggio("CALCOLO ZERO TERMICO DA PROFILI VERTICALI ECMWF (+72h)")

ds_ecmwf = xr.open_dataset(ECMWF_FILE, engine="cfgrib")

t_pl = ds_ecmwf["t"]
gh_pl = ds_ecmwf["gh"]

# Identificazione nome coordinata pressione e coordinate spaziali
press_coord = next((c for c in t_pl.dims if c in ["isobaricInhPa", "lev", "level", "pressure"]), None)
lat_e = next((n for n in ["latitude", "lat"] if n in ds_ecmwf.coords), None)
lon_e = next((n for n in ["longitude", "lon"] if n in ds_ecmwf.coords), None)

t_pl = t_pl.rename({lat_e: "lat", lon_e: "lon"})
gh_pl = gh_pl.rename({lat_e: "lat", lon_e: "lon"})

def normalizza_longitudine(da):
    lon = da["lon"]
    return da.assign_coords(lon=((lon + 180) % 360) - 180).sortby("lon")

t_pl = normalizza_longitudine(t_pl)
gh_pl = normalizza_longitudine(gh_pl)

# Taglio area Italia
t_pl = t_pl.sel(lat=slice(LAT_MAX, LAT_MIN), lon=slice(LON_MIN, LON_MAX))
gh_pl = gh_pl.sel(lat=slice(LAT_MAX, LAT_MIN), lon=slice(LON_MIN, LON_MAX))

# Ordinamento pressione decrescente (superficie -> quota)
t_pl = t_pl.sortby(press_coord, ascending=False)
gh_pl = gh_pl.sortby(press_coord, ascending=False)

# Algoritmo di estrazione zero termico (altezza dove T = 273.15 K)
t_vals = t_pl.values  # (lev, lat, lon)
gh_vals = gh_pl.values # (lev, lat, lon)
target = 273.15
n_lev, n_lat, n_lon = t_vals.shape
zero_height = np.full((n_lat, n_lon), np.nan)

for i in range(n_lat):
    for j in range(n_lon):
        profile_t = t_vals[:, i, j]
        profile_gh = gh_vals[:, i, j]
        found = False
        for k in range(n_lev - 1):
            t1, t2 = profile_t[k], profile_t[k+1]
            h1, h2 = profile_gh[k], profile_gh[k+1]
            if (t1 >= target >= t2) or (t1 <= target <= t2):
                if t1 == t2:
                    zero_height[i, j] = h1
                else:
                    zero_height[i, j] = h1 + (target - t1) * (h2 - h1) / (t2 - t1)
                found = True
                break
        if not found:
            if profile_t[0] < target:
                zero_height[i, j] = 0.0
            else:
                zero_height[i, j] = profile_gh[-1]

z_ecmwf = xr.DataArray(
    zero_height,
    coords={"lat": t_pl["lat"], "lon": t_pl["lon"]},
    dims=["lat", "lon"],
    name="zero_ecmwf",
    attrs={"units": "m"}
)

# ============================================================
# 4. LETTURA GFS E MEDIA MULTIMODELLO
# ============================================================

ds_gfs = xr.open_dataset(GFS_FILE, engine="cfgrib")
z_g_var = next((v for v in ["hgt", "HGT", "gh", "GH"] if v in ds_gfs), None)
z_gfs = ds_gfs[z_g_var]

lat_g = next((n for n in ["latitude", "lat"] if n in ds_gfs.coords), None)
lon_g = next((n for n in ["longitude", "lon"] if n in ds_gfs.coords), None)
z_gfs = z_gfs.rename({lat_g: "lat", lon_g: "lon"})
z_gfs = normalizza_longitudine(z_gfs)
z_gfs = z_gfs.sel(lat=slice(LAT_MAX, LAT_MIN), lon=slice(LON_MIN, LON_MAX))

# Interpolazione GFS su griglia ECMWF e calcolo media
z_gfs_interp = z_gfs.interp(lat=z_ecmwf["lat"], lon=z_ecmwf["lon"], method="linear")
z_media = (z_ecmwf + z_gfs_interp) / 2.0
z_media.name = "zero_termico_media"
z_media.attrs["units"] = "m"

z_diff = z_ecmwf - z_gfs_interp

# Statistiche a terminale
print()
print("STATISTICHE ZERO TERMICO (+72h)")
print("-" * 50)
print(f"Minimo quota 0°C: {float(z_media.min()):.0f} m")
print(f"Massimo quota 0°C: {float(z_media.max()):.0f} m")
print(f"Scarto medio assoluto ECMWF-GFS: {float(np.abs(z_diff).mean()):.1f} m")

ecmwf_run_text = ecmwf_run_datetime.strftime("%d/%m %H UTC")
gfs_run_text = f"{gfs_run_date[6:8]}/{gfs_run_date[4:6]} {gfs_run_cycle:02d} UTC"
valid_text = valid_time.strftime("%d/%m/%Y %H:%M UTC")

# ============================================================
# 5. PLOTTING DELLA MAPPA (FOCUS ITALIA)
# ============================================================

messaggio("CREAZIONE MAPPA ZERO TERMICO ITALIA (+72h)")

fig = plt.figure(figsize=(11, 10))
ax = plt.axes(projection=ccrs.PlateCarree())
ax.set_extent([LON_MIN, LON_MAX, LAT_MIN, LAT_MAX], crs=ccrs.PlateCarree())

zmin = max(0, np.floor(float(z_media.min()) / 300) * 300)
zmax = np.ceil(float(z_media.max()) / 300) * 300
levels = np.arange(zmin, zmax + 300, 300)

contour_fill = ax.contourf(
    z_media["lon"], z_media["lat"], z_media,
    levels=levels, cmap="terrain", alpha=0.85,
    extend="both", transform=ccrs.PlateCarree()
)

cbar = plt.colorbar(contour_fill, orientation="horizontal", pad=0.04, shrink=0.75)
cbar.set_label("Quota Zero Termico (metri s.l.m.) - Previsione +72h", fontsize=10, fontweight="bold")
cbar.ax.tick_params(labelsize=9)

contours = ax.contour(
    z_media["lon"], z_media["lat"], z_media,
    levels=levels, colors="black", linewidths=1.0, alpha=0.75,
    transform=ccrs.PlateCarree()
)
ax.clabel(contours, inline=True, fontsize=9, fmt="%d m")

ax.coastlines(resolution="10m", linewidth=1.1, color="darkslategray")
ax.add_feature(cfeature.BORDERS, linestyle=":", linewidth=0.8, alpha=0.7)
ax.add_feature(cfeature.LAKES, alpha=0.25)

gl = ax.gridlines(draw_labels=True, linestyle="--", linewidth=0.5, alpha=0.25)
gl.top_labels = False
gl.right_labels = False

plt.title(
    "McSPARK METEO – Quota Zero Termico Italia (+72h)\n"
    f"Media multimodello ECMWF + GFS | Validità: {valid_text}",
    fontsize=14, fontweight="bold", pad=15
)

fig.text(
    0.5, 0.03,
    f"ECMWF IFS: {ecmwf_run_text}   |   GFS: {gfs_run_text} (+{gfs_step} h)   |   Linee: media ECMWF + GFS (metri)",
    ha="center", fontsize=9
)

TEMP_FILE = DATA_DIR / "zero_termico_italia_temp_72h.png"
plt.savefig(TEMP_FILE, dpi=300, bbox_inches="tight", pad_inches=0.3, facecolor="white")
plt.close()

# ============================================================
# 6. INSERIMENTO LOGO E SALVATAGGIO NETCDF
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

NETCDF_FILE = DATA_DIR / "media_ECMWF_GFS_ZeroTermico_+72h.nc"
z_media.to_dataset(name="zero_termico").to_netcdf(NETCDF_FILE, engine="netcdf4")

messaggio("OPERAZIONE COMPLETATA (+72h)")
print("Mappa Zero Termico Italia:", OUTPUT_FILE)
print("Dati numerici NetCDF:", NETCDF_FILE)