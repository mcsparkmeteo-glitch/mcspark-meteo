# ============================================================
# McSPARK METEO
#
# MEDIA MULTIMODELLO ECMWF + GFS
# Temperatura a 850 hPa
#
# ECMWF IFS Open Data
# GFS NOAA/NCEP
#
# Il programma:
#   1. individua il run più recente disponibile ECMWF
#   2. scarica ECMWF +72 h
#   3. determina la validità reale ECMWF
#   4. cerca un run GFS compatibile con la stessa validità
#   5. scarica il campo GFS corrispondente
#   6. estrae la temperatura a 850 hPa
#   7. converte tutto da Kelvin a °C
#   8. interpola GFS sulla griglia ECMWF
#   9. calcola la media ECMWF + GFS
#  10. produce la carta finale brandizzata
#
# NOTA:
# la media è una semplice media aritmetica dei due modelli.
# I due campi sono riferiti alla STESSA VALIDITÀ TEMPORALE.
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


# ============================================================
# CONFIGURAZIONE
# ============================================================

LEAD_HOURS = 72

# Livello atmosferico
PRESSURE_LEVEL = 850

# Area della carta
LON_MIN = -10
LON_MAX = 30
LAT_MIN = 35
LAT_MAX = 60

# Risoluzione ECMWF Open Data
ECMWF_RESOLUTION = "0p25"

# Directory di lavoro
BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "dati_multimodello"
DATA_DIR.mkdir(exist_ok=True)

# Logo
LOGO_FILE = BASE_DIR / "logo.jpg"

# File temporanei
ECMWF_FILE = DATA_DIR / "ecmwf_t850_72h.grib2"
GFS_FILE = DATA_DIR / "gfs_t850_72h.grib2"

# Output
OUTPUT_FILE = (
    BASE_DIR /
    f"McSpark_Meteo_Media_ECMWF_GFS_T850_+{LEAD_HOURS // 24}g.png"
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
print("Media multimodello ECMWF + GFS")
print("Temperatura a 850 hPa")
print()

print(
    "Ora UTC:",
    now_utc.strftime("%Y-%m-%d %H:%M")
)


# ============================================================
# 2. DOWNLOAD ECMWF
# ============================================================

messaggio("RICERCA RUN ECMWF PIÙ RECENTE")

ecmwf_client = Client(
    source="ecmwf",
    model="ifs",
    resol=ECMWF_RESOLUTION
)

print("Richiedo ECMWF IFS...")
print("Parametro: temperatura")
print(f"Livello: {PRESSURE_LEVEL} hPa")
print(f"Lead time: +{LEAD_HOURS} h")


try:

    ecmwf_result = ecmwf_client.retrieve(

        # Non specifichiamo date/time:
        # il client cerca il run più recente disponibile
        type="fc",

        step=LEAD_HOURS,

        param="t",

        levelist=PRESSURE_LEVEL,

        target=str(ECMWF_FILE)
    )

except Exception as e:

    print()
    print("ERRORE DURANTE IL DOWNLOAD ECMWF:")
    print(e)

    sys.exit(1)


if not controlla_file(ECMWF_FILE):

    print(
        "Il file ECMWF non è stato creato "
        "correttamente."
    )

    sys.exit(1)


print()
print("ECMWF scaricato correttamente.")


if not hasattr(ecmwf_result, "datetime"):

    print()
    print(
        "ERRORE: impossibile determinare "
        "la data/ora del run ECMWF."
    )

    sys.exit(1)


# ============================================================
# RUN ECMWF E VALIDITÀ REALE
# ============================================================

ecmwf_run_datetime = ecmwf_result.datetime

print(
    "Run ECMWF:",
    ecmwf_run_datetime
)

print(
    "File:",
    ECMWF_FILE
)


# ------------------------------------------------------------
# VALIDITÀ REALE
#
# La validità viene calcolata dal RUN ECMWF,
# non dall'ora in cui viene eseguito lo script.
# ------------------------------------------------------------

valid_time = (
    ecmwf_run_datetime
    + dt.timedelta(hours=LEAD_HOURS)
)

print()
print(
    "Validità reale:",
    valid_time.strftime("%Y-%m-%d %H:%M UTC")
)


# ============================================================
# 3. INDIVIDUAZIONE RUN GFS
# ============================================================

messaggio(
    "RICERCA RUN GFS COMPATIBILE CON LA VALIDITÀ ECMWF"
)

session = requests.Session()

session.headers.update({
    "User-Agent":
        "McSpark-Meteo/1.0 meteorological research script"
})


# ============================================================
# FUNZIONE URL GFS
# ============================================================

def gfs_file_url(date_string, cycle, gfs_step):

    return (
        "https://nomads.ncep.noaa.gov/cgi-bin/"
        "filter_gfs_0p25.pl?"
        f"file=gfs.t{cycle:02d}z.pgrb2.0p25.f{gfs_step:03d}"
        "&lev_850_mb=on"
        "&var_TMP=on"
        f"&dir=%2Fgfs.{date_string}%2F{cycle:02d}%2Fatmos"
    )


# ============================================================
# VERIFICA URL
# ============================================================

def verifica_gfs_url(url):

    try:

        response = session.head(
            url,
            timeout=20,
            allow_redirects=True
        )

        if response.status_code == 200:
            return True

        # Alcuni server non gestiscono bene HEAD.
        # Proviamo quindi una GET minimale.
        response = session.get(
            url,
            timeout=30,
            stream=True
        )

        ok = response.status_code == 200

        response.close()

        return ok

    except requests.RequestException:

        return False


# ============================================================
# RICERCA GFS
# ============================================================

gfs_url = None
gfs_run_date = None
gfs_run_cycle = None
gfs_step = None


# ------------------------------------------------------------
# Partiamo dal run ECMWF.
#
# Cerchiamo un run GFS precedente o coincidente che abbia
# una previsione valida ESATTAMENTE allo stesso istante
# dell'ECMWF.
# ------------------------------------------------------------

candidate_base = ecmwf_run_datetime.replace(
    minute=0,
    second=0,
    microsecond=0
)


for attempt in range(MAX_GFS_ATTEMPTS):

    candidate = (
        candidate_base
        - dt.timedelta(hours=6 * attempt)
    )

    date_string = candidate.strftime("%Y%m%d")
    cycle = candidate.hour

    # Calcolo dello step GFS necessario per arrivare
    # esattamente alla validità ECMWF.
    delta = valid_time - candidate

    gfs_step_hours = int(
        delta.total_seconds() / 3600
    )

    # Il run candidato deve precedere la validità.
    if gfs_step_hours < 0:
        continue

    print(
        f"Controllo GFS {date_string} "
        f"{cycle:02d} UTC "
        f"+{gfs_step_hours:03d} h..."
    )

    test_url = gfs_file_url(
        date_string,
        cycle,
        gfs_step_hours
    )

    if verifica_gfs_url(test_url):

        gfs_url = test_url
        gfs_run_date = date_string
        gfs_run_cycle = cycle
        gfs_step = gfs_step_hours

        print()
        print(
            "RUN GFS TROVATO:",
            f"{date_string} {cycle:02d} UTC"
        )

        print(
            "Step GFS:",
            f"+{gfs_step:03d} h"
        )

        print(
            "Validità GFS:",
            valid_time.strftime(
                "%Y-%m-%d %H:%M UTC"
            )
        )

        break


if gfs_url is None:

    print()
    print(
        "ERRORE: non è stato trovato "
        "un run GFS compatibile con "
        "la validità ECMWF."
    )

    sys.exit(1)


# ============================================================
# 4. DOWNLOAD GFS
# ============================================================

messaggio("DOWNLOAD GFS")

print("URL:")
print(gfs_url)

try:

    response = session.get(
        gfs_url,
        timeout=180
    )

    response.raise_for_status()

    with open(GFS_FILE, "wb") as f:
        f.write(response.content)

except Exception as e:

    print()
    print("ERRORE DURANTE IL DOWNLOAD GFS:")
    print(e)

    sys.exit(1)


if not controlla_file(GFS_FILE):

    print(
        "Il file GFS non è stato creato "
        "correttamente."
    )

    sys.exit(1)


print()
print("GFS scaricato correttamente.")
print("File:", GFS_FILE)


# ============================================================
# 5. LETTURA GRIB ECMWF
# ============================================================

messaggio("LETTURA DATI ECMWF")

try:

    ds_ecmwf = xr.open_dataset(
        ECMWF_FILE,
        engine="cfgrib"
    )

except Exception as e:

    print()
    print("Errore nella lettura ECMWF:")
    print(e)

    sys.exit(1)


print("Variabili ECMWF:")
print(list(ds_ecmwf.data_vars))


# ============================================================
# 6. INDIVIDUAZIONE TEMPERATURA ECMWF
# ============================================================

if "t" in ds_ecmwf:

    t_ecmwf = ds_ecmwf["t"]

else:

    print(
        "ERRORE: variabile 't' non trovata "
        "nel file ECMWF."
    )

    sys.exit(1)


# ------------------------------------------------------------
# ECMWF t è espresso in Kelvin.
#
# Conversione:
#
#       °C = Kelvin - 273.15
# ------------------------------------------------------------

t_ecmwf = t_ecmwf - 273.15

t_ecmwf.name = "t850_ecmwf"

t_ecmwf.attrs["units"] = "degC"


# ============================================================
# 7. LETTURA GRIB GFS
# ============================================================

messaggio("LETTURA DATI GFS")

try:

    ds_gfs = xr.open_dataset(
        GFS_FILE,
        engine="cfgrib"
    )

except Exception as e:

    print()
    print("Errore nella lettura GFS:")
    print(e)

    sys.exit(1)


print("Variabili GFS:")
print(list(ds_gfs.data_vars))


# ============================================================
# 8. INDIVIDUAZIONE TEMPERATURA GFS
# ============================================================

if "t" in ds_gfs:

    t_gfs = ds_gfs["t"]

elif "tmp" in ds_gfs:

    t_gfs = ds_gfs["tmp"]

elif "TMP" in ds_gfs:

    t_gfs = ds_gfs["TMP"]

else:

    print(
        "ERRORE: campo temperatura TMP "
        "non trovato nel file GFS."
    )

    sys.exit(1)


# ------------------------------------------------------------
# GFS TMP è espresso in Kelvin.
#
# Conversione:
#
#       °C = Kelvin - 273.15
# ------------------------------------------------------------

t_gfs = t_gfs - 273.15

t_gfs.name = "t850_gfs"

t_gfs.attrs["units"] = "degC"


# ============================================================
# 9. NORMALIZZAZIONE COORDINATE
# ============================================================

messaggio("NORMALIZZAZIONE GRIGLIE")

print(
    "Coordinate ECMWF:",
    list(ds_ecmwf.coords)
)

print(
    "Coordinate GFS:",
    list(ds_gfs.coords)
)


def trova_coord(ds, possibili):

    for nome in possibili:

        if nome in ds.coords:
            return nome

    return None


lat_ecmwf_name = trova_coord(
    ds_ecmwf,
    ["latitude", "lat"]
)

lon_ecmwf_name = trova_coord(
    ds_ecmwf,
    ["longitude", "lon"]
)

lat_gfs_name = trova_coord(
    ds_gfs,
    ["latitude", "lat"]
)

lon_gfs_name = trova_coord(
    ds_gfs,
    ["longitude", "lon"]
)


if None in [
    lat_ecmwf_name,
    lon_ecmwf_name,
    lat_gfs_name,
    lon_gfs_name
]:

    print(
        "ERRORE: coordinate lat/lon "
        "non riconosciute."
    )

    sys.exit(1)


# ============================================================
# 10. RINOMINA COORDINATE
# ============================================================

t_ecmwf = t_ecmwf.rename({
    lat_ecmwf_name: "lat",
    lon_ecmwf_name: "lon"
})

t_gfs = t_gfs.rename({
    lat_gfs_name: "lat",
    lon_gfs_name: "lon"
})


# ============================================================
# 11. NORMALIZZAZIONE LONGITUDINI
# ============================================================

def normalizza_longitudine(da):

    lon = da["lon"]

    lon_normalizzata = (
        ((lon + 180) % 360) - 180
    )

    da = da.assign_coords(
        lon=lon_normalizzata
    )

    da = da.sortby("lon")

    return da


t_ecmwf = normalizza_longitudine(
    t_ecmwf
)

t_gfs = normalizza_longitudine(
    t_gfs
)


# ============================================================
# 12. SELEZIONE AREA EUROPEA
# ============================================================

t_ecmwf = t_ecmwf.sel(
    lat=slice(LAT_MAX, LAT_MIN),
    lon=slice(LON_MIN, LON_MAX)
)

t_gfs = t_gfs.sel(
    lat=slice(LAT_MAX, LAT_MIN),
    lon=slice(LON_MIN, LON_MAX)
)


# ============================================================
# 13. INTERPOLAZIONE GFS SULLA GRIGLIA ECMWF
# ============================================================

messaggio(
    "INTERPOLAZIONE GFS SULLA GRIGLIA ECMWF"
)

t_gfs_interp = t_gfs.interp(
    lat=t_ecmwf["lat"],
    lon=t_ecmwf["lon"],
    method="linear"
)


# ============================================================
# 14. MEDIA ECMWF + GFS
# ============================================================

messaggio("CALCOLO MEDIA MULTIMODELLO")

t_media = (
    t_ecmwf + t_gfs_interp
) / 2.0

t_media.name = "t850_media"

t_media.attrs["units"] = "degC"


# ============================================================
# 15. DIFFERENZA ECMWF - GFS
# ============================================================

t_diff = (
    t_ecmwf - t_gfs_interp
)

t_diff.name = "differenza_ecmwf_gfs"

t_diff.attrs["units"] = "degC"


# ============================================================
# 16. STATISTICHE
# ============================================================

print()
print("STATISTICHE")
print("-" * 50)

print(
    f"ECMWF minimo: "
    f"{float(t_ecmwf.min()):.1f} °C"
)

print(
    f"ECMWF massimo: "
    f"{float(t_ecmwf.max()):.1f} °C"
)

print(
    f"GFS minimo: "
    f"{float(t_gfs_interp.min()):.1f} °C"
)

print(
    f"GFS massimo: "
    f"{float(t_gfs_interp.max()):.1f} °C"
)

print(
    f"Media minimo: "
    f"{float(t_media.min()):.1f} °C"
)

print(
    f"Media massimo: "
    f"{float(t_media.max()):.1f} °C"
)

print(
    f"Scarto medio assoluto ECMWF-GFS: "
    f"{float(np.abs(t_diff).mean()):.2f} °C"
)

print(
    f"Scarto massimo assoluto: "
    f"{float(np.abs(t_diff).max()):.2f} °C"
)


# ============================================================
# 17. DATA/ORA DEL RUN
# ============================================================

ecmwf_run_text = (
    ecmwf_run_datetime.strftime(
        "%d/%m %H UTC"
    )
)


gfs_run_text = (
    f"{gfs_run_date[6:8]}/"
    f"{gfs_run_date[4:6]} "
    f"{gfs_run_cycle:02d} UTC"
)


# ============================================================
# 18. DATA/ORA DI VALIDITÀ
# ============================================================

valid_time_text = valid_time.strftime(
    "%d/%m/%Y %H:%M UTC"
)


# ============================================================
# 19. CREAZIONE MAPPA
# ============================================================

messaggio("CREAZIONE MAPPA FINALE")

fig = plt.figure(
    figsize=(13, 10)
)

ax = plt.axes(
    projection=ccrs.PlateCarree()
)


# ------------------------------------------------------------
# ESTENSIONE
# ------------------------------------------------------------

ax.set_extent(
    [
        LON_MIN,
        LON_MAX,
        LAT_MIN,
        LAT_MAX
    ],
    crs=ccrs.PlateCarree()
)


# ============================================================
# 20-21. ISOTERME E SHADING DELLA TEMPERATURA
# ============================================================

tmin = float(t_media.min())
tmax = float(t_media.max())

# Arrotondamento a intervalli di 2 °C
tmin = np.floor(tmin / 2) * 2
tmax = np.ceil(tmax / 2) * 2

levels = np.arange(
    tmin,
    tmax + 2,
    2
)


# ------------------------------------------------------------
# Shading
#
# Blu = temperature più basse
# Rosso = temperature più alte
# ------------------------------------------------------------

contour_fill = ax.contourf(
    t_media["lon"],
    t_media["lat"],
    t_media,
    levels=levels,
    cmap="RdYlBu_r",
    alpha=0.88,
    extend="both",
    transform=ccrs.PlateCarree()
)


# ------------------------------------------------------------
# Colorbar
# ------------------------------------------------------------

cbar = plt.colorbar(
    contour_fill,
    orientation="horizontal",
    pad=0.04,
    shrink=0.7
)

cbar.set_label(
    "Temperatura a 850 hPa (°C)",
    fontsize=10,
    fontweight="bold"
)

cbar.ax.tick_params(
    labelsize=9
)


# ------------------------------------------------------------
# ISOTERME
# ------------------------------------------------------------

contours = ax.contour(
    t_media["lon"],
    t_media["lat"],
    t_media,
    levels=levels,
    colors="black",
    linewidths=1.1,
    alpha=0.8,
    transform=ccrs.PlateCarree()
)

ax.clabel(
    contours,
    inline=True,
    fontsize=9,
    fmt="%.0f°C"
)


# ============================================================
# 22. GEOGRAFIA
# ============================================================

ax.coastlines(
    resolution="50m",
    linewidth=1.0,
    color="darkslategray"
)

ax.add_feature(
    cfeature.BORDERS,
    linestyle=":",
    linewidth=0.7,
    alpha=0.7
)

ax.add_feature(
    cfeature.LAKES,
    alpha=0.25
)


# ============================================================
# 23. GRIGLIA
# ============================================================

gl = ax.gridlines(
    draw_labels=True,
    linestyle="--",
    linewidth=0.5,
    alpha=0.25
)

gl.top_labels = False
gl.right_labels = False


# ============================================================
# 24. TITOLO
# ============================================================

plt.title(
    "McSPARK METEO – Temperatura a 850 hPa\n"
    f"Media multimodello ECMWF + GFS | +{LEAD_HOURS // 24} giorni\n"
    f"Validità: {valid_time_text}",
    fontsize=14,
    fontweight="bold",
    pad=15
)


# ============================================================
# 25. INFORMAZIONI RUN
# ============================================================

fig.text(
    0.5,
    0.035,
    f"ECMWF IFS: {ecmwf_run_text}   |   "
    f"GFS: {gfs_run_text} (+{gfs_step} h)   |   "
    "Linee: media ECMWF + GFS (°C)",
    ha="center",
    fontsize=9
)


# ============================================================
# 26. SALVATAGGIO TEMPORANEO
# ============================================================

TEMP_FILE = (
    DATA_DIR /
    "mappa_t850_multimodello_temp.png"
)


plt.savefig(
    TEMP_FILE,
    dpi=300,
    bbox_inches="tight",
    pad_inches=0.3,
    facecolor="white"
)

plt.close()


# ============================================================
# 27. INSERIMENTO LOGO
# ============================================================

messaggio("INSERIMENTO LOGO")

try:

    base_img = Image.open(
        TEMP_FILE
    ).convert("RGB")

    logo = Image.open(
        LOGO_FILE
    ).convert("RGB")


    # --------------------------------------------------------
    # Dimensione logo
    # --------------------------------------------------------

    basewidth = 150

    rapporto = (
        basewidth /
        float(logo.size[0])
    )

    hsize = int(
        float(logo.size[1])
        * rapporto
    )

    logo = logo.resize(
        (basewidth, hsize),
        Image.Resampling.LANCZOS
    )


    # --------------------------------------------------------
    # Posizione
    # --------------------------------------------------------

    img_width, img_height = (
        base_img.size
    )

    logo_width, logo_height = (
        logo.size
    )

    margin = 5

    position = (
        img_width - logo_width - margin,
        img_height - logo_height - margin
    )


    base_img.paste(
        logo,
        position
    )


    # --------------------------------------------------------
    # Salvataggio finale
    # --------------------------------------------------------

    base_img.save(
        OUTPUT_FILE,
        format="PNG"
    )


except FileNotFoundError:

    print()
    print(
        "ATTENZIONE: logo.jpg non trovato."
    )

    print(
        "La mappa senza logo è comunque "
        f"disponibile in:\n{TEMP_FILE}"
    )

    OUTPUT_FILE = TEMP_FILE


# ============================================================
# 28. SALVATAGGIO DATI NUMERICI
# ============================================================

NETCDF_FILE = (
    DATA_DIR /
    f"media_ECMWF_GFS_T850_+{LEAD_HOURS}h.nc"
)

t_media.to_dataset(
    name="t850_media"
).to_netcdf(
    NETCDF_FILE
)


# ============================================================
# 29. FINE
# ============================================================

messaggio("OPERAZIONE COMPLETATA")

print(
    "Mappa finale:"
)

print(
    OUTPUT_FILE
)

print()

print(
    "Dati numerici:"
)

print(
    NETCDF_FILE
)

print()

print(
    f"ECMWF run: {ecmwf_run_text}"
)

print(
    f"GFS run:   {gfs_run_text}"
)

print(
    f"GFS step:  +{gfs_step} h"
)

print(
    f"Validità:  {valid_time_text}"
)

print()

print(
    "La carta rappresenta la media "
    "aritmetica delle temperature ECMWF "
    "e GFS a 850 hPa alla stessa validità "
    "temporale."
)

print()
print("McSPARK METEO")