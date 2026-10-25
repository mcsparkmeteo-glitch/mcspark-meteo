# ============================================================
# McSpark Meteo
# PRESSIONE AL LIVELLO DEL MARE (MSLP)
# ECMWF IFS + GFS NOAA/NCEP
#
# Confronto multimodello:
# - stessa validità
# - preferibilmente stesso ciclo di inizializzazione
# - lead time ECMWF = +72 h
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

# Lead time ECMWF
LEAD_HOURS_ECMWF = 72

# Area Italia
LON_MIN = 6
LON_MAX = 19
LAT_MIN = 35
LAT_MAX = 48

# Directory di lavoro
OUT_DIR = "mslp_multimodello"
os.makedirs(OUT_DIR, exist_ok=True)

# File ECMWF
ECMWF_FILE = os.path.join(
    OUT_DIR,
    "ecmwf_msl_72h.grib2"
)

# File GFS
GFS_FILE = os.path.join(
    OUT_DIR,
    "gfs_prmsl.grib2"
)

# Output
OUTPUT_PNG = os.path.join(
    OUT_DIR,
    "mslp_72h_ECMWF_GFS.png"
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
    "Richiedo ultima corsa ECMWF disponibile..."
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
#
# Prima proviamo lo stesso ciclo dell'ECMWF.
# Poi procediamo a ritroso:
#
# ECMWF 06 UTC:
#   GFS 06
#   GFS 00
#   GFS 18 del giorno precedente
#   GFS 12 del giorno precedente
#
# In questo modo non utilizziamo mai un run GFS
# successivo al run ECMWF.
# ------------------------------------------------------------

ecmwf_cycle = ecmwf_run_datetime.hour

candidate_runs = []

for hours_back in range(0, 25, 6):

    candidate_time = (
        ecmwf_run_datetime
        - timedelta(hours=hours_back)
    )

    candidate_cycle = candidate_time.hour

    # Consideriamo soltanto i normali cicli GFS
    if candidate_cycle in GFS_CYCLES:

        candidate_runs.append(
            candidate_time.replace(
                minute=0,
                second=0,
                microsecond=0
            )
        )


# Eliminiamo eventuali duplicati
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

    # --------------------------------------------------------
    # Calcolo del lead time necessario per arrivare
    # alla STESSA validità ECMWF
    # --------------------------------------------------------

    candidate_lead = (
        valid_time - candidate_run
    ).total_seconds() / 3600

    candidate_lead = int(round(candidate_lead))


    # Non accettiamo lead negativi
    if candidate_lead < 0:

        continue


    # GFS operativo usa step interi
    # e la richiesta deve essere coerente.
    if candidate_lead > 384:

        continue


    gfs_date = candidate_run.strftime(
        "%Y%m%d"
    )

    gfs_cycle = candidate_run.strftime(
        "%H"
    )


    # --------------------------------------------------------
    # Nome file GFS
    # --------------------------------------------------------

    file_name = (
        f"gfs.t{gfs_cycle}z."
        f"pgrb2.0p25."
        f"f{candidate_lead:03d}"
    )


    # --------------------------------------------------------
    # Parametri NOMADS
    # --------------------------------------------------------

    params = {

        "dir":
            f"/gfs.{gfs_date}/"
            f"{gfs_cycle}/atmos",

        "file":
            file_name,

        # Pressione ridotta al livello del mare
        "var_PRMSL":
            "on",

        # PARAMETRO CORRETTO NOMADS
        "lev_mean_sea_level":
            "on",

        # Area geografica richiesta
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


    # --------------------------------------------------------
    # Informazioni a video
    # --------------------------------------------------------

    print("\n----------------------------------------------")

    print(
        "Provo run GFS:"
    )

    print(
        f"  {candidate_run.strftime('%Y-%m-%d %H UTC')}"
    )

    print(
        f"Lead GFS necessario: "
        f"+{candidate_lead} h"
    )

    print(
        f"File: {file_name}"
    )


    # ========================================================
    # TENTATIVI DI DOWNLOAD
    # ========================================================

    run_success = False

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        print(
            f"Tentativo "
            f"{attempt}/{MAX_RETRIES}..."
        )

        try:

            response = requests.get(
                gfs_url,
                timeout=120
            )


            # ------------------------------------------------
            # Controllo HTTP
            # ------------------------------------------------

            response.raise_for_status()


            content = response.content


            # ------------------------------------------------
            # Controllo dimensione
            # ------------------------------------------------

            if len(content) < 5000:

                print(
                    "Risposta troppo piccola."
                )

                if attempt < MAX_RETRIES:

                    print(
                        f"Attendo "
                        f"{RETRY_DELAY} secondi..."
                    )

                    time.sleep(
                        RETRY_DELAY
                    )

                continue


            # ------------------------------------------------
            # Controllo che sia realmente GRIB
            # ------------------------------------------------

            if not content.startswith(
                b"GRIB"
            ):

                print(
                    "La risposta ricevuta "
                    "non sembra essere un "
                    "file GRIB valido."
                )

                if attempt < MAX_RETRIES:

                    print(
                        f"Attendo "
                        f"{RETRY_DELAY} secondi..."
                    )

                    time.sleep(
                        RETRY_DELAY
                    )

                continue


            # ------------------------------------------------
            # Salvataggio
            # ------------------------------------------------

            with open(
                GFS_FILE,
                "wb"
            ) as f:

                f.write(content)


            print(
                "\nGFS scaricato con successo."
            )

            print(
                f"Dimensione: "
                f"{len(content) / 1024 / 1024:.2f} MB"
            )


            # ------------------------------------------------
            # Memorizziamo il run utilizzato
            # ------------------------------------------------

            gfs_run = candidate_run

            gfs_lead_hours = candidate_lead

            gfs_valid_time = (
                gfs_run
                + timedelta(
                    hours=gfs_lead_hours
                )
            )


            success = True
            run_success = True

            break


        except requests.exceptions.HTTPError as e:

            print(
                f"Errore HTTP NOMADS: {e}"
            )

            if attempt < MAX_RETRIES:

                print(
                    f"Attendo "
                    f"{RETRY_DELAY} secondi..."
                )

                time.sleep(
                    RETRY_DELAY
                )


        except requests.exceptions.RequestException as e:

            print(
                f"Errore di connessione: {e}"
            )

            if attempt < MAX_RETRIES:

                print(
                    f"Attendo "
                    f"{RETRY_DELAY} secondi..."
                )

                time.sleep(
                    RETRY_DELAY
                )


        except Exception as e:

            print(
                f"Errore inatteso: {e}"
            )

            break


    # --------------------------------------------------------
    # Se abbiamo trovato un run valido, usciamo dal ciclo
    # --------------------------------------------------------

    if run_success:

        break


# ============================================================
# CONTROLLO FINALE GFS
# ============================================================

if not success:

    print("\n==============================================")
    print(" ERRORE CRITICO GFS")
    print("==============================================")

    print(
        "Nessun run GFS valido è stato "
        "scaricato da NOMADS."
    )

    sys.exit(1)


# ============================================================
# VERIFICA DELLA VALIDITÀ
# ============================================================

print("\n==============================================")
print(" GFS ACQUISITO")
print("==============================================")

print(
    f"Run GFS   : "
    f"{gfs_run.strftime('%Y-%m-%d %H:%M UTC')}"
)

print(
    f"Validità  : "
    f"{gfs_valid_time.strftime('%Y-%m-%d %H:%M UTC')}"
)

print(
    f"Lead time : "
    f"+{gfs_lead_hours} h"
)


# ------------------------------------------------------------
# Controllo fondamentale:
# ECMWF e GFS devono avere la stessa validità
# ------------------------------------------------------------

if gfs_valid_time != valid_time:

    print(
        "\nERRORE: ECMWF e GFS non hanno "
        "la stessa validità."
    )

    print(
        f"ECMWF: {valid_time}"
    )

    print(
        f"GFS  : {gfs_valid_time}"
    )

    sys.exit(1)


print(
    "\nOK: ECMWF e GFS hanno "
    "la stessa identica validità."
)


# ============================================================
# 3. LETTURA ECMWF
# ============================================================

print("\n==============================================")
print(" LETTURA DATI ECMWF")
print("==============================================")


try:

    ds_ecmwf = xr.open_dataset(
        ECMWF_FILE,
        engine="cfgrib"
    )

except Exception as e:

    print(
        "\nErrore lettura ECMWF:"
    )

    print(e)

    sys.exit(1)


# ------------------------------------------------------------
# Controllo variabile
# ------------------------------------------------------------

if "msl" not in ds_ecmwf:

    print(
        "\nERRORE: variabile "
        "'msl' non trovata nel GRIB ECMWF."
    )

    print(
        "Variabili disponibili:"
    )

    print(
        list(ds_ecmwf.data_vars)
    )

    sys.exit(1)


msl_ecmwf = ds_ecmwf["msl"]


# ------------------------------------------------------------
# Conversione Pa → hPa
# ------------------------------------------------------------

msl_ecmwf_hpa = (
    msl_ecmwf / 100.0
)

msl_ecmwf_hpa.name = "mslp"


# ============================================================
# 4. LETTURA GFS
# ============================================================

print("\n==============================================")
print(" LETTURA DATI GFS")
print("==============================================")


try:

    ds_gfs = xr.open_dataset(
        GFS_FILE,
        engine="cfgrib"
    )

except Exception as e:

    print(
        "\nErrore lettura GFS:"
    )

    print(e)

    sys.exit(1)


# ------------------------------------------------------------
# Individuazione variabile PRMSL
# ------------------------------------------------------------

gfs_var = None


if "prmsl" in ds_gfs.data_vars:

    gfs_var = "prmsl"

elif "msl" in ds_gfs.data_vars:

    gfs_var = "msl"

elif "unknown" in ds_gfs.data_vars:

    gfs_var = "unknown"


if gfs_var is None:

    print(
        "\nERRORE: non riesco a individuare "
        "la pressione al livello del mare nel GFS."
    )

    print(
        "Variabili disponibili:"
    )

    print(
        list(ds_gfs.data_vars)
    )

    sys.exit(1)


print(
    f"Variabile GFS utilizzata: {gfs_var}"
)


msl_gfs = ds_gfs[gfs_var]


# ------------------------------------------------------------
# Conversione Pa → hPa
# ------------------------------------------------------------

units_gfs = str(
    msl_gfs.attrs.get(
        "units",
        ""
    )
).lower()


if (
    "pa" in units_gfs
    and "hpa" not in units_gfs
):

    msl_gfs_hpa = (
        msl_gfs / 100.0
    )

else:

    msl_gfs_hpa = msl_gfs


msl_gfs_hpa.name = "mslp"


# ============================================================
# 5. NORMALIZZAZIONE E CLIP
# ============================================================

print("\n==============================================")
print(" NORMALIZZAZIONE GRIGLIE")
print("==============================================")


msl_ecmwf_hpa = normalize_longitude(
    msl_ecmwf_hpa
)

msl_gfs_hpa = normalize_longitude(
    msl_gfs_hpa
)


msl_ecmwf_hpa = clip_area(
    msl_ecmwf_hpa
)

msl_gfs_hpa = clip_area(
    msl_gfs_hpa
)


# ============================================================
# 6. INTERPOLAZIONE E MEDIA MULTIMODELLO
# ============================================================

print("\n==============================================")
print(" INTERPOLAZIONE E MEDIA MULTIMODELLO")
print("==============================================")


lat_ecmwf, lon_ecmwf = (
    get_lat_lon(
        msl_ecmwf_hpa
    )
)


lat_gfs, lon_gfs = (
    get_lat_lon(
        msl_gfs_hpa
    )
)


print(
    "Interpolo il GFS sulla griglia ECMWF..."
)


msl_gfs_interp = (
    msl_gfs_hpa.interp(
        {
            lat_gfs:
                msl_ecmwf_hpa[lat_ecmwf],

            lon_gfs:
                msl_ecmwf_hpa[lon_ecmwf]
        },

        method="linear"
    )
)


# ------------------------------------------------------------
# Media ECMWF + GFS
# ------------------------------------------------------------

msl_mean = (
    msl_ecmwf_hpa
    + msl_gfs_interp
) / 2.0


msl_mean.name = (
    "multimodel_mslp"
)


print(
    "Media multimodello calcolata."
)


# ============================================================
# 7. MAPPA MSLP
# ============================================================

print("\n==============================================")
print(" CREAZIONE MAPPA MSLP")
print("==============================================")


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


# ------------------------------------------------------------
# Livelli pressione
# ------------------------------------------------------------

levels_fill = np.arange(
    990,
    1045,
    2
)


levels_contour = np.arange(
    990,
    1045,
    4
)


# ------------------------------------------------------------
# Palette
# ------------------------------------------------------------

cmap = plt.get_cmap(
    "YlGnBu_r",
    len(levels_fill) - 1
)


lon = (
    msl_ecmwf_hpa[
        lon_ecmwf
    ]
)


lat = (
    msl_ecmwf_hpa[
        lat_ecmwf
    ]
)


# ============================================================
# RIEMPIMENTO
# ============================================================

mesh = ax.contourf(

    lon,
    lat,
    msl_mean,

    levels=levels_fill,

    cmap=cmap,

    extend="both",

    transform=ccrs.PlateCarree(),

    alpha=0.75
)


# ============================================================
# ISOBARE
# ============================================================

contours = ax.contour(

    lon,
    lat,
    msl_mean,

    levels=levels_contour,

    colors="darkblue",

    linewidths=0.9,

    transform=ccrs.PlateCarree()
)


ax.clabel(

    contours,

    inline=True,

    fmt="%d hPa",

    fontsize=8
)


# ============================================================
# 8. GEOGRAFIA
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
# GRIGLIA
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
# 9. COLORBAR
# ============================================================

cbar = plt.colorbar(

    mesh,

    ax=ax,

    orientation="vertical",

    pad=0.02,

    shrink=0.85
)


cbar.set_label(

    "Pressione al Livello del Mare - MSLP (hPa)",

    fontsize=11
)


# ============================================================
# 10. TESTI
# ============================================================

run_ecmwf_text = (
    ecmwf_run_datetime.strftime(
        "%d/%m/%Y %H UTC"
    )
)


run_gfs_text = (
    gfs_run.strftime(
        "%d/%m/%Y %H UTC"
    )
)


valid_text = (
    valid_time.strftime(
        "%d/%m/%Y %H UTC"
    )
)


# ------------------------------------------------------------
# Titolo
# ------------------------------------------------------------

ax.set_title(

    "McSpark Meteo PRESSIONE AL LIVELLO DEL MARE (MSLP) - 72 ORE\n"
    "Media multimodello ECMWF IFS + GFS",

    fontsize=15,

    fontweight="bold",

    pad=25
)


# ------------------------------------------------------------
# Informazioni sui run
# ------------------------------------------------------------

ax.text(

    0.5,

    1.02,

    f"ECMWF: {run_ecmwf_text}   |   "
    f"GFS: {run_gfs_text}   |   "
    f"Validità: {valid_text}",

    transform=ax.transAxes,

    ha="center",

    va="bottom",

    fontsize=9.5
)


# ------------------------------------------------------------
# Informazione lead time
# ------------------------------------------------------------

ax.text(

    0.5,

    -0.055,

    f"Lead ECMWF: +{LEAD_HOURS_ECMWF} h   |   "
    f"Lead GFS: +{gfs_lead_hours} h",

    transform=ax.transAxes,

    ha="center",

    va="top",

    fontsize=9
)


# ============================================================
# 11. SALVATAGGIO
# ============================================================

plt.tight_layout()

plt.savefig(
    OUTPUT_PNG,
    dpi=180,
    bbox_inches="tight"
)

# Mostra la finestra grafica SOLO in locale (salta su GitHub Actions)
if not os.environ.get("CI"):
    plt.show()

plt.close()


# ============================================================
# 12. FINE
# ============================================================

print("\n==============================================")
print(" ELABORAZIONE MSLP COMPLETATA")
print("==============================================")


print(
    f"Run ECMWF : "
    f"{ecmwf_run_datetime.strftime('%Y-%m-%d %H UTC')}"
)


print(
    f"Run GFS   : "
    f"{gfs_run.strftime('%Y-%m-%d %H UTC')}"
)


print(
    f"Validità  : "
    f"{valid_time.strftime('%Y-%m-%d %H UTC')}"
)


print(
    f"Lead ECMWF: +{LEAD_HOURS_ECMWF} h"
)


print(
    f"Lead GFS  : +{gfs_lead_hours} h"
)


print(
    f"Mappa salvata in: "
    f"{OUTPUT_PNG}"
)
