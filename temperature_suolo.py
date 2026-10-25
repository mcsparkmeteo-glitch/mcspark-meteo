# ============================================================
# McSPARK METEO
# MEDIA MULTIMODELLO ECMWF + GFS
# Temperatura al suolo (2 metri) - Ore 07:00 e 15:00 UTC
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

# ============================================================
# CONFIGURAZIONE
# ============================================================

# Area della carta (Europa / Italia)
LON_MIN = -10
LON_MAX = 30
LAT_MIN = 35
LAT_MAX = 60

ECMWF_RESOLUTION = "0p25"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "dati_multimodello"
DATA_DIR.mkdir(exist_ok=True)

LOGO_FILE = BASE_DIR / "logo.jpg"
MAX_GFS_ATTEMPTS = 8

def messaggio(testo):
    print()
    print("=" * 70)
    print(testo)
    print("=" * 70)

def controlla_file(path):
    return path.exists() and path.stat().st_size >= 1000

# ============================================================
# 1. DOWNLOAD ECMWF (INDIVIDUAZIONE RUN RECENTE)
# ============================================================

messaggio("RICERCA RUN ECMWF PIÙ RECENTE")

ecmwf_client = Client(
    source="ecmwf",
    model="ifs",
    resol=ECMWF_RESOLUTION
)

# Troviamo il run ECMWF più recente senza specificare il lead time fisso
# Per farlo, scarichiamo prima uno step di test o usiamo la struttura di ricerca.
# Con ECMWF Open Data, chiediamo direttamente il client per l'ultimo run.
# Usiamo un lead time temporaneo di 24h solo per ottenere l'oggetto metadati del run.
TEMP_ECMWF_FILE = DATA_DIR / "ecmwf_test_run.grib2"

try:
    ecmwf_result = ecmwf_client.retrieve(
        type="fc",
        step=24,
        param="2t",
        levtype="sfc",
        target=str(TEMP_ECMWF_FILE)
    )
except Exception as e:
    print("ERRORE DURANTE IL DOWNLOAD ECMWF:", e)
    sys.exit(1)

ecmwf_run_datetime = ecmwf_result.datetime
if ecmwf_run_datetime.tzinfo is None:
    ecmwf_run_datetime = ecmwf_run_datetime.replace(tzinfo=dt.timezone.utc)

# Fissiamo il run alle 00:00 UTC per avere tutti i passi orari stabili e disponibili
ecmwf_run_datetime = dt.datetime.combine(ecmwf_run_datetime.date(), dt.time(0, 0), tzinfo=dt.timezone.utc)
print("Run ECMWF utilizzato:", ecmwf_run_datetime)

# =================================O===========================
# DEFINIZIONE DEGLI ORARI TARGET (07:00 e 15:00 del giorno successivo)
# ============================================================
base_date = ecmwf_run_datetime.date()
tomorrow = base_date + dt.timedelta(days=1)

target_times = [
    {
        "ora": "06:00",
        "descrizione": "Minime stimate (06:00 UTC)",
        "valid_time": dt.datetime.combine(tomorrow, dt.time(6, 0), tzinfo=dt.timezone.utc),
        "output_png": BASE_DIR / "temperatura_suolo_06.png"
    },
    {
        "ora": "15:00",
        "descrizione": "Massime stimate (15:00 UTC)",
        "valid_time": dt.datetime.combine(tomorrow, dt.time(15, 0), tzinfo=dt.timezone.utc),
        "output_png": BASE_DIR / "temperatura_suolo_15.png"
    }
]

session = requests.Session()
session.headers.update({"User-Agent": "McSpark-Meteo/1.0"})

def gfs_file_url(date_string, cycle, gfs_step):
    return (
        "https://nomads.ncep.noaa.gov/cgi-bin/"
        "filter_gfs_0p25.pl?"
        f"file=gfs.t{cycle:02d}z.pgrb2.0p25.f{gfs_step:03d}"
        "&lev_2_m_above_ground=on"
        "&var_TMP=on"
        f"&dir=%2Fgfs.{date_string}%2F{cycle:02d}%2Fatmos"
    )

def normalizza_longitudine(da):
    lon = da["lon"]
    da = da.assign_coords(lon=((lon + 180) % 360) - 180)
    return da.sortby("lon")

# ============================================================
# CICLO SUI DUE ORARI (07:00 e 15:00)
# ============================================================

for target in target_times:
    valid_time = target["valid_time"]
    lead_hours = int((valid_time - ecmwf_run_datetime).total_seconds() / 3600)
    
    messaggio(f"ELABORAZIONE TEMPERATURA ORE {target['ora']} UTC (Lead time: +{lead_hours}h)")

    ECMWF_FILE = DATA_DIR / f"ecmwf_t2m_{lead_hours}h.grib2"
    GFS_FILE = DATA_DIR / f"gfs_t2m_{lead_hours}h.grib2"

    # 1. Download ECMWF per il lead time calcolato
    # 1. Download ECMWF per il lead time calcolato (usando il run esatto trovato)
    try:
        ecmwf_client.retrieve(
            type="fc",
            date=ecmwf_run_datetime.strftime("%Y-%m-%d"),
            time=f"{ecmwf_run_datetime.hour:02d}00",
            step=lead_hours,
            param="2t",
            levtype="sfc",
            target=str(ECMWF_FILE)
        )
    except Exception as e:
        print(f"Errore download ECMWF per +{lead_hours}h:", e)
        continue

    # 2. Ricerca e Download GFS compatibile
    candidate_base = ecmwf_run_datetime.replace(minute=0, second=0, microsecond=0)
    gfs_url = None
    gfs_run_date = None
    gfs_run_cycle = None
    gfs_step = None

    for attempt in range(MAX_GFS_ATTEMPTS):
        candidate = candidate_base - dt.timedelta(hours=6 * attempt)
        date_string = candidate.strftime("%Y%m%d")
        cycle = candidate.hour
        delta = valid_time - candidate
        gfs_step_hours = int(delta.total_seconds() / 3600)

        if gfs_step_hours < 0:
            continue

        test_url = gfs_file_url(date_string, cycle, gfs_step_hours)
        try:
            resp = session.head(test_url, timeout=10)
            if resp.status_code == 200:
                gfs_url = test_url
                gfs_run_date = date_string
                gfs_run_cycle = cycle
                gfs_step = gfs_step_hours
                break
        except:
            pass

    if not gfs_url:
        print(f"ERRORE: GFS non trovato per validità {valid_time}")
        continue

    # Scarica GFS
    try:
        resp = session.get(gfs_url, timeout=120)
        resp.raise_for_status()
        with open(GFS_FILE, "wb") as f:
            f.write(resp.content)
    except Exception as e:
        print("Errore download GFS:", e)
        continue

    # 3. Lettura e conversione in Celsius (°C)
    ds_ecmwf = xr.open_dataset(ECMWF_FILE, engine="cfgrib")
    t_ecmwf = ds_ecmwf["t2m"] - 273.15

    ds_gfs = xr.open_dataset(GFS_FILE, engine="cfgrib")
    # Trova variabile TMP nel GFS
    t_gfs_var = None
    for v in ["t2m", "t", "tmp", "TMP"]:
        if v in ds_gfs:
            t_gfs_var = v
            break
            
    if t_gfs_var is None:
        print(f"ERRORE: Variabile temperatura non trovata in GFS. Disponibili: {list(ds_gfs.data_vars)}")
        continue
        
    t_gfs = ds_gfs[t_gfs_var] - 273.15

    # 4. Normalizzazione e Taglio Area
    lat_e = "latitude" if "latitude" in ds_ecmwf.coords else "lat"
    lon_e = "longitude" if "longitude" in ds_ecmwf.coords else "lon"
    lat_g = "latitude" if "latitude" in ds_gfs.coords else "lat"
    lon_g = "longitude" if "longitude" in ds_gfs.coords else "lon"

    t_ecmwf = t_ecmwf.rename({lat_e: "lat", lon_e: "lon"})
    t_gfs = t_gfs.rename({lat_g: "lat", lon_g: "lon"})

    t_ecmwf = normalizza_longitudine(t_ecmwf)
    t_gfs = normalizza_longitudine(t_gfs)

    t_ecmwf = t_ecmwf.sel(lat=slice(LAT_MAX, LAT_MIN), lon=slice(LON_MIN, LON_MAX))
    t_gfs = t_gfs.sel(lat=slice(LAT_MAX, LAT_MIN), lon=slice(LON_MIN, LON_MAX))

    # 5. Interpolazione e Media Multimodello
    t_gfs_interp = t_gfs.interp(lat=t_ecmwf["lat"], lon=t_ecmwf["lon"], method="linear")
    t_media = (t_ecmwf + t_gfs_interp) / 2.0

    # 6. Plotting della Mappa
    fig = plt.figure(figsize=(13, 10))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent([LON_MIN, LON_MAX, LAT_MIN, LAT_MAX], crs=ccrs.PlateCarree())

    tmin = np.floor(float(t_media.min()) / 2) * 2
    tmax = np.ceil(float(t_media.max()) / 2) * 2
    levels = np.arange(tmin, tmax + 2, 2)

    contour_fill = ax.contourf(
        t_media["lon"], t_media["lat"], t_media,
        levels=levels, cmap="RdYlBu_r", alpha=0.88,
        extend="both", transform=ccrs.PlateCarree()
    )

    cbar = plt.colorbar(contour_fill, orientation="horizontal", pad=0.04, shrink=0.7)
    cbar.set_label(f"Temperatura a 2m (°C) - {target['descrizione']}", fontsize=10, fontweight="bold")

    contours = ax.contour(
        t_media["lon"], t_media["lat"], t_media,
        levels=levels, colors="black", linewidths=1.1, alpha=0.8,
        transform=ccrs.PlateCarree()
    )
    ax.clabel(contours, inline=True, fontsize=9, fmt="%.0f°C")

    ax.coastlines(resolution="50m", linewidth=1.0, color="darkslategray")
    ax.add_feature(cfeature.BORDERS, linestyle=":", linewidth=0.7, alpha=0.7)
    ax.add_feature(cfeature.LAKES, alpha=0.25)

    gl = ax.gridlines(
        draw_labels=True,
        linestyle="--",
        linewidth=0.5,
        alpha=0.25
    )
    gl.top_labels = False
    gl.right_labels = False

    valid_text = valid_time.strftime("%d/%m/%Y %H:%M UTC")
    plt.title(
        f"McSPARK METEO – Temperatura al Suolo ({target['ora']} UTC)\n"
        f"Media multimodello ECMWF + GFS | Validità: {valid_text}",
        fontsize=14, fontweight="bold", pad=15
    )

    TEMP_FILE = DATA_DIR / f"temp_suolo_{target['ora'].replace(':', '')}_temp.png"
    plt.savefig(TEMP_FILE, dpi=300, bbox_inches="tight", pad_inches=0.3, facecolor="white")
    plt.close()

    # Inserimento Logo opzionale
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
        base_img.save(target["output_png"], format="PNG")
    except FileNotFoundError:
        TEMP_FILE.rename(target["output_png"])

    print(f"Mappa generata con successo: {target['output_png']}")

print("\nElaborazione completata per tutte le mappe di temperatura al suolo.")