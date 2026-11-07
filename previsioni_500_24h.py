# ============================================================
# McSPARK METEO
#
# MEDIA MULTIMODELLO ECMWF + GFS
# Geopotenziale a 500 hPa (Area Euro-Atlantica) - Previsione +24h
#
# ECMWF IFS Open Data
# GFS NOAA/NCEP
# ============================================================


# ============================================================
# IMPORT
# ============================================================

import os
import sys
import time
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

# Nuova estensione geografica (stile WXcharts)
LON_MIN = -25.0
LON_MAX = 40.0
LAT_MIN = 30.0
LAT_MAX = 72.0

# Risoluzione ECMWF Open Data
ECMWF_RESOLUTION = "0p25"

# Directory di lavoro
BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "dati_multimodello"
DATA_DIR.mkdir(exist_ok=True)

# Logo
LOGO_FILE = BASE_DIR / "logo.jpg"

# File temporanei aggiornati a 24h
ECMWF_FILE = DATA_DIR / "ecmwf_z500_24h.grib2"
GFS_FILE = DATA_DIR / "gfs_z500_24h.grib2"

# Output
OUTPUT_FILE = (
    BASE_DIR /
    f"McSpark_Meteo_Media_ECMWF_GFS_+{LEAD_HOURS}h.png"
)

# Numero massimo di cicli GFS da controllare
MAX_GFS_ATTEMPTS = 8


# ============================================================
# FUNZIONI DI SUPPORTO
# ============================================================

def messaggio(testo):
    print()
    print("=" * 70)
    print(testo)
    print("=" * 70)


def controlla_file(path):
    """
    Controlla che il file esista e non sia vuoto.
    """
    if not path.exists():
        return False

    if path.stat().st_size < 1000:
        return False

    return True


# ============================================================
# 1. DATA/ORA UTC
# ============================================================

now_utc = dt.datetime.now(dt.timezone.utc)

print()
print("McSPARK METEO")
print("Media multimodello ECMWF + GFS (Euro-Atlantico - +24h)")
print()
print(
    "Ora UTC:",
    now_utc.strftime("%Y-%m-%d %H:%M")
)


# ============================================================
# 2. DOWNLOAD ECMWF
# ============================================================

messaggio("RICERCA RUN ECMWF PIÙ RECENTE (+24h)")

ecmwf_client = Client(
    source="ecmwf",
    model="ifs",
    resol=ECMWF_RESOLUTION
)

print("Richiedo ECMWF IFS...")
print("Parametro: geopotenziale")
print("Livello: 500 hPa")
print(f"Lead time: +{LEAD_HOURS} h")


try:
    ecmwf_result = ecmwf_client.retrieve(
        type="fc",
        step=LEAD_HOURS,
        param="gh",
        levelist=500,
        target=str(ECMWF_FILE)
    )

except Exception as e:
    print()
    print("ERRORE DURANTE IL DOWNLOAD ECMWF:")
    print(e)
    sys.exit(1)


if not controlla_file(ECMWF_FILE):
    print("Il file ECMWF non è stato creato correttamente.")
    sys.exit(1)


print()
print("ECMWF scaricato correttamente.")

if not hasattr(ecmwf_result, "datetime"):
    print()
    print("ERRORE: impossibile determinare la data/ora del run ECMWF.")
    sys.exit(1)


# ============================================================
# RUN ECMWF E VALIDITÀ REALE
# ============================================================

ecmwf_run_datetime = ecmwf_result.datetime

print("Run ECMWF:", ecmwf_run_datetime)
print("File:", ECMWF_FILE)

valid_time = (
    ecmwf_run_datetime
    + dt.timedelta(hours=LEAD_HOURS)
)

print()
print("Validità reale:", valid_time.strftime("%Y-%m-%d %H:%M UTC"))


# ============================================================
# 3. INDIVIDUAZIONE RUN GFS
# ============================================================

messaggio("RICERCA RUN GFS COMPATIBILE CON LA VALIDITÀ ECMWF")

session = requests.Session()
session.headers.update({
    "User-Agent": "McSpark-Meteo/1.0 meteorological research script"
})


def gfs_file_url(date_string, cycle, gfs_step):
    return (
        "https://nomads.ncep.noaa.gov/cgi-bin/"
        "filter_gfs_0p25.pl?"
        f"file=gfs.t{cycle:02d}z.pgrb2.0p25.f{gfs_step:03d}"
        "&lev_500_mb=on"
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

candidate_base = ecmwf_run_datetime.replace(
    minute=0, second=0, microsecond=0
)

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

        print()
        print("RUN GFS TROVATO:", f"{date_string} {cycle:02d} UTC")
        print("Step GFS:", f"+{gfs_step:03d} h")
        print("Validità GFS:", valid_time.strftime("%Y-%m-%d %H:%M UTC"))
        break


if gfs_url is None:
    print()
    print("ERRORE: non è stato trovato un run GFS compatibile con la validità ECMWF.")
    sys.exit(1)


# ============================================================
# 4. DOWNLOAD GFS
# ============================================================

messaggio("DOWNLOAD GFS")
print("URL:")
print(gfs_url)

try:
    response = session.get(gfs_url, timeout=180)
    response.raise_for_status()
    with open(GFS_FILE, "wb") as f:
        f.write(response.content)
except Exception as e:
    print()
    print("ERRORE DURANTE IL DOWNLOAD GFS:")
    print(e)
    sys.exit(1)

if not controlla_file(GFS_FILE):
    print("Il file GFS non è stato creato correttamente.")
    sys.exit(1)

print()
print("GFS scaricato correttamente.")
print("File:", GFS_FILE)


# ============================================================
# 5. LETTURA GRIB ECMWF & GFS
# ============================================================

messaggio("LETTURA DATI ECMWF E GFS")

ds_ecmwf = xr.open_dataset(ECMWF_FILE, engine="cfgrib")
ds_gfs = xr.open_dataset(GFS_FILE, engine="cfgrib")

z_ecmwf = ds_ecmwf["gh"] / 10.0
z_ecmwf.name = "z500_ecmwf"
z_ecmwf.attrs["units"] = "dam"

if "gh" in ds_gfs:
    z_gfs = ds_gfs["gh"]
elif "hgt" in ds_gfs:
    z_gfs = ds_gfs["hgt"]
elif "HGT" in ds_gfs:
    z_gfs = ds_gfs["HGT"]
else:
    print("ERRORE: campo geopotenziale HGT non trovato nel file GFS.")
    sys.exit(1)

z_gfs = z_gfs / 10.0
z_gfs.name = "z500_gfs"
z_gfs.attrs["units"] = "dam"


# ============================================================
# 6. NORMALIZZAZIONE E TAGLIO AREA EURO-ATLANTICA
# ============================================================

messaggio("NORMALIZZAZIONE GRIGLIE E TAGLIO EURO-ATLANTICO")

lat_ecmwf_name = "latitude" if "latitude" in ds_ecmwf.coords else "lat"
lon_ecmwf_name = "longitude" if "longitude" in ds_ecmwf.coords else "lon"
lat_gfs_name = "latitude" if "latitude" in ds_gfs.coords else "lat"
lon_gfs_name = "longitude" if "longitude" in ds_gfs.coords else "lon"

z_ecmwf = z_ecmwf.rename({lat_ecmwf_name: "lat", lon_ecmwf_name: "lon"})
z_gfs = z_gfs.rename({lat_gfs_name: "lat", lon_gfs_name: "lon"})

def normalizza_longitudine(da):
    lon = da["lon"]
    lon_normalizzata = ((lon + 180) % 360) - 180
    da = da.assign_coords(lon=lon_normalizzata)
    return da.sortby("lon")

z_ecmwf = normalizza_longitudine(z_ecmwf)
z_gfs = normalizza_longitudine(z_gfs)

z_ecmwf = z_ecmwf.sel(lat=slice(LAT_MAX, LAT_MIN), lon=slice(LON_MIN, LON_MAX))
z_gfs = z_gfs.sel(lat=slice(LAT_MAX, LAT_MIN), lon=slice(LON_MIN, LON_MAX))


# ============================================================
# 7. INTERPOLAZIONE E MEDIA MULTIMODELLO
# ============================================================

messaggio("INTERPOLAZIONE E CALCOLO MEDIA MULTIMODELLO")

z_gfs_interp = z_gfs.interp(
    lat=z_ecmwf["lat"],
    lon=z_ecmwf["lon"],
    method="linear"
)

z_media = (z_ecmwf + z_gfs_interp) / 2.0
z_media.name = "z500_media"
z_media.attrs["units"] = "dam"

# Differenza per le statistiche
z_diff = z_ecmwf - z_gfs_interp
z_diff.name = "differenza_ecmwf_gfs"
z_diff.attrs["units"] = "dam"


# ============================================================
# 8. STATISTICHE
# ============================================================

print()
print("STATISTICHE")
print("-" * 50)
print(f"ECMWF minimo:  {float(z_ecmwf.min()):.1f} dam")
print(f"ECMWF massimo: {float(z_ecmwf.max()):.1f} dam")
print(f"GFS minimo:    {float(z_gfs_interp.min()):.1f} dam")
print(f"GFS massimo:   {float(z_gfs_interp.max()):.1f} dam")
print(f"Media minimo:  {float(z_media.min()):.1f} dam")
print(f"Media massimo: {float(z_media.max()):.1f} dam")
print(f"Scarto medio assoluto ECMWF-GFS: {float(np.abs(z_diff).mean()):.2f} dam")
print(f"Scarto massimo assoluto:         {float(np.abs(z_diff).max()):.2f} dam")


# ============================================================
# 9. TESTI PER TITOLO E INFORMAZIONI
# ============================================================

ecmwf_run_text = ecmwf_run_datetime.strftime("%d/%m %H UTC")
gfs_run_text = f"{gfs_run_date[6:8]}/{gfs_run_date[4:6]} {gfs_run_cycle:02d} UTC"
valid_time_text = valid_time.strftime("%d/%m/%Y %H:%M UTC")


# ============================================================
# 10. CREAZIONE MAPPA EURO-ATLANTICA
# ============================================================

messaggio("CREAZIONE MAPPA FINALE")

fig = plt.figure(figsize=(15, 9))
ax = plt.axes(projection=ccrs.PlateCarree())

ax.set_extent([LON_MIN, LON_MAX, LAT_MIN, LAT_MAX], crs=ccrs.PlateCarree())

zmin = float(z_media.min())
zmax = float(z_media.max())
zmin = np.floor(zmin / 4) * 4
zmax = np.ceil(zmax / 4) * 4
levels = np.arange(zmin, zmax + 4, 4)

contour_fill = ax.contourf(
    z_media["lon"],
    z_media["lat"],
    z_media,
    levels=levels,
    cmap="turbo",
    alpha=0.85,
    extend="both",
    transform=ccrs.PlateCarree()
)

cbar = plt.colorbar(
    contour_fill,
    orientation="horizontal",
    pad=0.04,
    shrink=0.65
)
cbar.set_label("Altezza di Geopotenziale a 500 hPa (dam)", fontsize=10, fontweight="bold")
cbar.ax.tick_params(labelsize=9)

contours = ax.contour(
    z_media["lon"],
    z_media["lat"],
    z_media,
    levels=levels,
    colors="black",
    linewidths=1.2,
    alpha=0.8,
    transform=ccrs.PlateCarree()
)
ax.clabel(contours, inline=True, fontsize=9, fmt="%d")

# Geografia e dettagli
ax.coastlines(resolution="50m", linewidth=0.9, color="darkslategray")
ax.add_feature(cfeature.BORDERS, linestyle=":", linewidth=0.7, alpha=0.7)
ax.add_feature(cfeature.LAKES, alpha=0.25)

gl = ax.gridlines(draw_labels=True, linestyle="--", linewidth=0.5, alpha=0.25)
gl.top_labels = False
gl.right_labels = False

plt.title(
    "McSPARK METEO – Geopotenziali a 500 hPa (Euro-Atlantico)\n"
    f"Media multimodello ECMWF + GFS | +{LEAD_HOURS} ore (+1 giorno)\n"
    f"Validità: {valid_time_text}",
    fontsize=14,
    fontweight="bold",
    pad=15
)

fig.text(
    0.5,
    0.03,
    f"ECMWF IFS: {ecmwf_run_text}   |   "
    f"GFS: {gfs_run_text} (+{gfs_step} h)   |   "
    "Linee: media ECMWF + GFS (dam)",
    ha="center",
    fontsize=9
)

TEMP_FILE = DATA_DIR / "mappa_multimodello_temp.png"
plt.savefig(TEMP_FILE, dpi=300, bbox_inches="tight", pad_inches=0.3, facecolor="white")
plt.close()


# ============================================================
# 11. INSERIMENTO LOGO E SALVATAGGIO FINALE
# ============================================================

messaggio("INSERIMENTO LOGO")

try:
    base_img = Image.open(TEMP_FILE).convert("RGB")
    logo = Image.open(LOGO_FILE).convert("RGB")

    basewidth = 150
    rapporto = basewidth / float(logo.size[0])
    hsize = int(float(logo.size[1]) * rapporto)
    logo = logo.resize((basewidth, hsize), Image.Resampling.LANCZOS)

    img_width, img_height = base_img.size
    logo_width, logo_height = logo.size
    margin = 5
    position = (img_width - logo_width - margin, img_height - logo_height - margin)

    base_img.paste(logo, position)
    base_img.save(OUTPUT_FILE, format="PNG")

except FileNotFoundError:
    print("\nATTENZIONE: logo.jpg non trovato. Salvato senza logo.")
    OUTPUT_FILE = TEMP_FILE

# Salvataggio NetCDF dei dati medi
NETCDF_FILE = DATA_DIR / f"media_ECMWF_GFS_Z500_+{LEAD_HOURS}h.nc"
z_media.to_dataset(name="z500_media").to_netcdf(NETCDF_FILE, engine="netcdf4")

messaggio("OPERAZIONE COMPLETATA")
print("Mappa finale:", OUTPUT_FILE)
print("Dati numerici:", NETCDF_FILE)