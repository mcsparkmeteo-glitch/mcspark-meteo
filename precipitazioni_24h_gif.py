# ============================================================
# McSPARK METEO - ANIMAZIONE MOVIMENTO PRECIPITAZIONI (PASSO 3H)
# Giornata solare 00:00 - 24:00 UTC (Differenza step a 3 ore)
# ECMWF IFS + GFS NOAA/NCEP -> Formato MP4
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
from pathlib import Path

import cartopy.crs as ccrs
import cartopy.feature as cfeature

from PIL import Image
import imageio.v2 as imageio_v2

# ECMWF Open Data
from ecmwf.opendata import Client
import matplotlib
matplotlib.use('Agg')  # Forza il salvataggio senza interfaccia grafica


# ============================================================
# CONFIGURAZIONE
# ============================================================

# Area Italia
LON_MIN = 6.0
LON_MAX = 19.0
LAT_MIN = 35.0
LAT_MAX = 48.0

ECMWF_RESOLUTION = "0p25"

# Directory di lavoro
BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "precipitazioni_multimodello"
OUT_DIR.mkdir(exist_ok=True)

FRAMES_DIR = OUT_DIR / "frames_animazione_movimento_3h"
FRAMES_DIR.mkdir(exist_ok=True)

LOGO_FILE = BASE_DIR / "logo.jpg"
OUTPUT_MP4_FILE = BASE_DIR / "McSpark_Meteo_Movimento_Precipitazioni_3h.mp4"


# ============================================================
# FUNZIONI DI SUPPORTO
# ============================================================

def messaggio(testo):
    print()
    print("=" * 70)
    print(testo)
    print("=" * 70)

def normalize_longitude(ds):
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
    base_url = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
    file_name = f"gfs.t{gfs_cycle}z.pgrb2.0p25.f{step_hours:03d}"
    params = {
        "dir": f"/gfs.{gfs_date}/{gfs_cycle}/atmos",
        "file": file_name,
        "lev_surface": "on",
        "var_APCP": "on"
    }
    url = base_url + "?" + urlencode(params)
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        return False

    if len(resp.content) < 10000:
        return False

    with open(out_path, "wb") as f:
        f.write(resp.content)
    return True

def read_gfs_apcp(grib_path):
    ds = xr.open_dataset(grib_path, engine="cfgrib")
    for candidate in ["tp", "apcp", "unknown"]:
        if candidate in ds.data_vars:
            da = ds[candidate]
            units = str(da.attrs.get("units", "")).lower()
            if "kg" in units or "mm" in units:
                return da
    raise ValueError("Variabile APCP non trovata nel file GFS.")


# ============================================================
# 1. RILEVAMENTO RUN E CALCOLO STEP GIORNATA SOLARE
# ============================================================

messaggio("RICERCA RUN ECMWF E DEFINIZIONE FINESTRA 24H (00-24 UTC)")

client = Client(source="ecmwf", model="ifs", resol=ECMWF_RESOLUTION)

# Test preliminare per trovare l'orario del run attivo
TEMP_TEST = OUT_DIR / "ecmwf_test_run.grib2"
try:
    res_test = client.retrieve(type="fc", step=24, stream="oper", levtype="sfc", param="tp", target=str(TEMP_TEST))
except Exception as e:
    print("ERRORE ECMWF DI TEST:", e)
    sys.exit(1)

ecmwf_run_datetime = res_test.datetime
if ecmwf_run_datetime.tzinfo is None:
    ecmwf_run_datetime = ecmwf_run_datetime.replace(tzinfo=timezone.utc)

print(f"Run ECMWF rilevato: {ecmwf_run_datetime.strftime('%Y-%m-%d %H:%M UTC')}")

# Vogliamo la prima giornata solare completa successiva al run (dalle 00:00 alle 24:00)
# Se il run è alle 00:00, la giornata va da +24h a +48h.
target_day_start = datetime.combine(ecmwf_run_datetime.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
target_day_end = target_day_start + timedelta(hours=24)

base_start_h = int((target_day_start - ecmwf_run_datetime).total_seconds() / 3600)
base_end_h = int((target_day_end - ecmwf_run_datetime).total_seconds() / 3600)

# Gli step della giornata ogni 3 ore (es. da 24 a 48 con passo 3)
# Per fare la differenza (corrente - precedente), ci serve anche lo step immediatamente precedente (base_start_h - 3)
step_list_needed = list(range(base_start_h - 3, base_end_h + 1, 3))

print(f"Giornata target: {target_day_start.strftime('%d/%m/%Y')} (Step da +{base_start_h}h a +{base_end_h}h)")
print(f"Step GRIB da scaricare (inclusi i precedenti per il calcolo differenziale): {step_list_needed}")


# ============================================================
# 2. DOWNLOAD ECMWF (A BLOCCHI O UNICO)
# ============================================================

ECMWF_FILE = OUT_DIR / "ecmwf_tp_movimento_3h.grib2"
try:
    client.retrieve(
        type="fc",
        step=step_list_needed,
        stream="oper",
        levtype="sfc",
        param="tp",
        target=str(ECMWF_FILE)
    )
except Exception as e:
    print("ERRORE DOWNLOAD ECMWF:", e)
    sys.exit(1)

ds_ecmwf = xr.open_dataset(ECMWF_FILE, engine="cfgrib")
tp_ecmwf_all = ds_ecmwf["tp"] * 1000.0  # metri -> mm


# ============================================================
# 3. GENERAZIONE FRAME CON INTERPOLAZIONE ORARIA (FLUIDO)
# ============================================================

# Definiamo la data e il ciclo GFS agganciandoci al run ECMWF rilevato
gfs_run = ecmwf_run_datetime
gfs_date = gfs_run.strftime("%Y%m%d")
gfs_cycle = gfs_run.strftime("%H")

frame_filenames = []
messaggio("GENERAZIONE FRAME FLUIDI (Interpolazione Oraria)")

giornata_steps = list(range(base_start_h, base_end_h + 1, 3))
precip_cache = {}

# 1. Carichiamo e salviamo in cache i dati reali a 3 ore
for current_step in giornata_steps:
    
    prev_step = current_step - 3
    gfs_file_curr = OUT_DIR / f"gfs_f{current_step:03d}.grib2"
    gfs_file_prev = OUT_DIR / f"gfs_f{prev_step:03d}.grib2"
    
    if not download_gfs_step(gfs_date, gfs_cycle, current_step, gfs_file_curr) or \
       not download_gfs_step(gfs_date, gfs_cycle, prev_step, gfs_file_prev):
        continue

    try:
        tp_e_curr = tp_ecmwf_all.sel(step=np.timedelta64(current_step, 'h'))
        tp_e_prev = tp_ecmwf_all.sel(step=np.timedelta64(prev_step, 'h'))
        tp_e_3h = tp_e_curr - tp_e_prev

        gfs_curr_raw = read_gfs_apcp(gfs_file_curr)
        gfs_prev_raw = read_gfs_apcp(gfs_file_prev)
        
        start_step_attr = gfs_curr_raw.attrs.get("GRIB_startStep", 0)
        gfs_3h = (gfs_curr_raw - gfs_prev_raw) if float(start_step_attr) == 0.0 else gfs_curr_raw

        tp_e_norm = clip_area(normalize_longitude(tp_e_3h))
        gfs_norm = clip_area(normalize_longitude(gfs_3h))

        tp_e_norm = xr.where(tp_e_norm < 0, 0, tp_e_norm)
        gfs_norm = xr.where(gfs_norm < 0, 0, gfs_norm)

        lat_e, lon_e = get_lat_lon(tp_e_norm)
        lat_g, lon_g = get_lat_lon(gfs_norm)

        gfs_interp = gfs_norm.interp({lat_g: tp_e_norm[lat_e], lon_g: tp_e_norm[lon_e]}, method="linear")
        precip_mean = (tp_e_norm + gfs_interp) / 2.0
        precip_cache[current_step] = precip_mean
    except Exception as ex:
        print(f"Errore caricamento step +{current_step}h: {ex}")

# 2. Creiamo i fotogrammi ora per ora interpolando i dati
all_hourly_steps = list(range(base_start_h, base_end_h + 1, 1))

for h in all_hourly_steps:
    lower_step = (h // 3) * 3
    upper_step = lower_step + 3
    
    if lower_step not in precip_cache or upper_step not in precip_cache:
        continue
        
    weight = (h - lower_step) / 3.0
    precip_interpolated = (1.0 - weight) * precip_cache[lower_step] + weight * precip_cache[upper_step]
    
    valid_time = ecmwf_run_datetime + timedelta(hours=h)
    if valid_time.tzinfo is None:
        valid_time = valid_time.replace(tzinfo=timezone.utc)

    # Plot Matplotlib
    fig = plt.figure(figsize=(10, 10), dpi=120)
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent([LON_MIN, LON_MAX, LAT_MIN, LAT_MAX], crs=ccrs.PlateCarree())

    levels = [0.1, 0.5, 1, 2, 4, 7, 10, 15, 20, 30, 45, 60, 80]
    colors_list = [
        "#b8f3ff", "#82dcf8", "#46b4e6", "#1e82dc", "#005ac8",
        "#00a000", "#50f050", "#f0f000", "#ffc800", "#ff7800",
        "#e11400", "#960032", "#640064"
    ]
    cmap = mcolors.ListedColormap(colors_list)
    cmap.set_under("white", alpha=0)
    cmap.set_over("#320032", alpha=1)
    norm_cbar = mcolors.BoundaryNorm(levels, ncolors=cmap.N, clip=False)

    sample_da = precip_cache[lower_step]
    lat_e, lon_e = get_lat_lon(sample_da)
    lon_vals = sample_da[lon_e]
    lat_vals = sample_da[lat_e]

    mesh = ax.contourf(
            lon_vals, lat_vals, precip_interpolated,
            levels=levels, cmap=cmap, norm=norm_cbar, extend="max",
            transform=ccrs.PlateCarree(), alpha=0.9
        )

        # AGGIUNTA SCALA COLORI (COLORBAR)
    cbar = plt.colorbar(mesh, ax=ax, orientation='horizontal', pad=0.05, shrink=0.8)
    cbar.set_label('Precipitazioni (mm / 3h)', fontsize=10, fontweight='bold')
    cbar.set_ticks(levels[::2])
    cbar.ax.tick_params(labelsize=8)

    ax.add_feature(cfeature.COASTLINE, linewidth=1.1, edgecolor="black")
    ax.add_feature(cfeature.BORDERS, linewidth=0.8, edgecolor="black")
    ax.add_feature(cfeature.LAKES, alpha=0.3)
    ax.add_feature(cfeature.RIVERS, alpha=0.3)

    gl = ax.gridlines(draw_labels=True, linewidth=0.4, alpha=0.4, linestyle="--")
    gl.top_labels = False
    gl.right_labels = False

    day_label = target_day_start.strftime("%d/%m/%Y")
    valid_text = valid_time.strftime("%H:%M UTC")
    ax.set_title(
        f"McSPARK METEO – Precipitazioni in movimento ({day_label})\n"
        f"Evoluzione oraria | Validità: {valid_text}",
        fontsize=12, fontweight="bold", pad=12
    )

    temp_frame_path = FRAMES_DIR / f"frame_interp_{h:03d}.png"
    plt.savefig(temp_frame_path, dpi=120, bbox_inches="tight", pad_inches=0.2, facecolor="white")
    plt.close(fig)

    # Controllo dimensioni pari e logo con Pillow
    with Image.open(temp_frame_path) as img:
        w, h_img = img.size
        new_w = w if w % 2 == 0 else w + 1
        new_h = h_img if h_img % 2 == 0 else h_img + 1
        if new_w != w or new_h != h_img:
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        if LOGO_FILE.exists():
            logo = Image.open(LOGO_FILE).convert("RGB")
            basewidth = 120
            wpercent = (basewidth / float(logo.size[0]))
            hsize = int(float(logo.size[1]) * wpercent)
            logo = logo.resize((basewidth, hsize), Image.Resampling.LANCZOS)
            
            lw, lh = logo.size
            img.paste(logo, (new_w - lw - 10, new_h - lh - 10))
        
        img.save(temp_frame_path)

    frame_filenames.append(temp_frame_path)

ds_ecmwf.close()

# ============================================================
# 4. ASSEMBLAGGIO VIDEO MP4 FLUIDO (FPS 5)
# ============================================================

if frame_filenames:
    messaggio("CREAZIONE VIDEO MP4 FLUIDO (FPS 5)")
    frames = [imageio_v2.imread(str(f)) for f in frame_filenames]
    
    imageio_v2.mimsave(
        OUTPUT_MP4_FILE, 
        frames, 
        fps=3,  # Corretto senza virgole doppie
        codec='libx264', 
        quality=8, 
        macro_block_size=None
    )
    print(f"Video MP4 fluido completato! Salvato in: {OUTPUT_MP4_FILE}")