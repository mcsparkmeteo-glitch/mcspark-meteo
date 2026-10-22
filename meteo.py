from datetime import datetime, timedelta
import os
import time
import zoneinfo
import folium
import requests
from requests.adapters import HTTPAdapter
from shapely.geometry import Point, shape
from urllib3.util import Retry
from province_italia import PROVINCE_BY_REGIONE, REGIONI_COORDINATE

# ==========================================
# CONFIGURAZIONE SESSIONE HTTP RETRY
# ==========================================
session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
    raise_on_status=False,
)
adapter = HTTPAdapter(max_retries=retries)
session.mount("http://", adapter)
session.mount("https://", adapter)

# ==========================================
# CONFIGURAZIONE, TIMESTAMP E BRANDING
# ==========================================
NOME_SITO = "McSpark Meteo"
COPYRIGHT = f"© 2026 {NOME_SITO} - Tutti i diritti riservati"
FONTE_DATI = (
    "Dati: Protezione Civile, WeatherAPI & Forecast Models (GFS/ECMWF/ICON)"
)
FILE_LOGO_LOCAL = "unnamed.jpg"

ora_italiana = datetime.now(zoneinfo.ZoneInfo("Europe/Rome"))
STRINGA_AGGIORNAMENTO = ora_italiana.strftime(
    "Aggiornato il: %d/%m/%Y alle %H:%M"
)

print(f"🌊✨ McSpark Meteo: Avvio iniezione dati ({STRINGA_AGGIORNAMENTO})...")

API_KEY = "eca968be0d38479d87e193151260106"
CARTO_API_KEY = "cb1_2x4n_1_882094333b79f892981d14ba"

# ==========================================
# COORDINATE DEI MARI ITALIANI
# ==========================================
DIZIONARIO_MARI = {
    "Mar Ligure": {"lat": 43.90, "lon": 9.00},
    "Tirreno Settentrionale": {"lat": 42.60, "lon": 10.50},
    "Tirreno Centrale": {"lat": 41.00, "lon": 12.50},
    "Tirreno Meridionale": {"lat": 39.50, "lon": 14.00},
    "Alto Adriatico": {"lat": 44.80, "lon": 13.00},
    "Medio Adriatico": {"lat": 43.00, "lon": 14.80},
    "Basso Adriatico": {"lat": 41.20, "lon": 18.20},
    "Mar Ionio": {"lat": 38.00, "lon": 17.50},
    "Mare di Sicilia": {"lat": 36.80, "lon": 13.50},
    "Canale di Sardegna": {"lat": 38.80, "lon": 9.50},
}

CACHE_GEOJSON_DPC = {}


# ==========================================
# FUNZIONE ALLERTE PROTEZIONE CIVILE (DPC)
# ==========================================
def ottieni_allerta_dpc_spaziale(lat_float, lon_float, data_target_str):
    global CACHE_GEOJSON_DPC

    if "CACHE_GEOJSON_DPC" not in globals():
        CACHE_GEOJSON_DPC = {}

    try:
        data_clean = str(data_target_str).strip()
        if "/" in data_clean:
            data_target = datetime.strptime(data_clean, "%d/%m/%Y").date()
        else:
            data_target = datetime.strptime(data_clean, "%Y-%m-%d").date()

        oggi = datetime.now().date()
        diff_giorni = (data_target - oggi).days
    except Exception:
        diff_giorni = 0

    if diff_giorni not in [0, 1]:
        return "transparent", "VERDE"

    cache_key = f"dpc_geojson_{datetime.now().strftime('%Y%m%d_%H')}"

    if cache_key not in CACHE_GEOJSON_DPC:
        geojson_data = None
        try:
            commit_url = "https://api.github.com/repos/pcm-dpc/DPC-Bollettini-Criticita-Idrogeologica-Idraulica/commits?per_page=10"
            resp = session.get(commit_url, timeout=20)

            if resp.status_code == 200:
                commits = resp.json()
                download_url = None

                for commit in commits:
                    c_resp = session.get(commit.get("url"), timeout=20)
                    if c_resp.status_code == 200:
                        c_data = c_resp.json()
                        for f in c_data.get("files", []):
                            fname = f.get("filename", "").lower()
                            if (
                                fname.endswith(".json")
                                and "geojson" in fname
                                and "topojson" not in fname
                            ):
                                download_url = f.get("raw_url")
                                break
                    if download_url:
                        break

                if download_url:
                    r_json = session.get(download_url, timeout=20)
                    if r_json.status_code == 200:
                        geojson_data = r_json.json()
        except Exception as e:
            print(f"[DPC ERR] Errore connessione: {e}")

        CACHE_GEOJSON_DPC[cache_key] = geojson_data

    geojson = CACHE_GEOJSON_DPC.get(cache_key)
    if not geojson:
        return "transparent", "VERDE"

    punto_citta = Point(float(lon_float), float(lat_float)).buffer(0.08)
    livello = 0

    chiavi_allerta_valide = [
        "IDRO",
        "IDRA",
        "TEMP",
        "CRITICITA",
        "ALLERTA",
        "RISCHIO",
    ]
    chiavi_da_ignorare = [
        "VERS",
        "VERSIONE",
        "BOLLETTINO",
        "OBJECTID",
        "FID",
        "COD_",
        "ID_",
        "SHAPE_",
        "DATA_",
        "STATO",
        "NOTE",
    ]

    for feature in geojson.get("features", []):
        try:
            geom_raw = feature.get("geometry")
            if not geom_raw:
                continue
            poligono = shape(geom_raw).buffer(0)
            if poligono.intersects(punto_citta):
                props = feature.get("properties", {})
                for chiave, valore in props.items():
                    ch_upper = str(chiave).upper().strip()
                    if any(escl in ch_upper for escl in chiavi_da_ignorare):
                        continue
                    if any(ok in ch_upper for ok in chiavi_allerta_valide):
                        v_str = str(valore).strip().upper()
                        if any(
                            x in v_str for x in ["ROSSA", "ROSSO", "ELEVATA"]
                        ) or v_str in ["3", "3.0"]:
                            livello = max(livello, 3)
                        elif any(
                            x in v_str for x in ["ARANCIONE", "MODERATA"]
                        ) or v_str in ["2", "2.0"]:
                            livello = max(livello, 2)
                        elif any(
                            x in v_str for x in ["GIALLA", "GIALLO", "ORDINARIA"]
                        ) or v_str in ["1", "1.0"]:
                            livello = max(livello, 1)
        except Exception:
            continue

    colori = {3: "#ff4d4d", 2: "#ff9933", 1: "#ffff66", 0: "transparent"}
    nomi = {3: "ROSSO", 2: "ARANCIONE", 1: "GIALLO", 0: "VERDE"}
    return colori[livello], nomi[livello]


def estrai_colore_allerta_weatherapi(res_json, nome_provincia=""):
    return "transparent"


# ==========================================
# FUNZIONI TABELLE REGIONALI
# ==========================================
def tabella_regionale_pioggia(regione_nome, dati_tabelle_regionali):
    html = (
        f"<div class='scheda-meteo s-pioggia'>"
        f"<h3 style='margin:0 0 8px 0; color:#1f77b4; border-bottom:2px solid #1f77b4; "
        f"padding-bottom:4px; font-size:13px; text-align:center;'>{regione_nome}: Precipitazioni e Cielo</h3>"
        "<table style='width:100%; border-collapse:collapse; text-align:center; font-size:11px; "
        "border:1px solid #ddd; table-layout: fixed;'>"
        "<tr style='background-color:#f8f9fa; font-weight:bold; height:32px; font-size:10px;'>"
        "<th style='width:34%; padding:2px; font-weight:bold;'>Provincia</th>"
        "<th style='width:22%; padding:2px; font-weight:bold;'>Cielo</th>"
        "<th style='width:11%; padding:2px; font-weight:bold;'>GFS</th>"
        "<th style='width:11%; padding:2px; font-weight:bold;'>ICON</th>"
        "<th style='width:11%; padding:2px; font-weight:bold;'>ECMWF</th>"
        "<th style='width:11%; background-color:#e6f2ff; padding:2px; font-weight:bold; color:#1f77b4;'>MED</th>"
        "</tr>"
    )

    for p_nome, d in dati_tabelle_regionali.get(regione_nome, {}).items():
        fulmini = " ⚡" if d.get("fulmini") else ""
        allerta_bg = d.get("colore_allerta", "transparent")
        nome_dpc = d.get("allerta_dpc_nome", "VERDE")
        instab = d.get("instabilita", {})

        badge_allerta = ""
        if allerta_bg != "transparent" or nome_dpc in [
            "ROSSO",
            "ARANCIONE",
            "GIALLO",
        ]:
            badge_allerta = " <span title='Allerta Ufficiale Protezione Civile' style='display:inline-block; font-size:12px;'>⚠️</span>"
        elif instab.get("allerta") == "rosso":
            badge_allerta = " <span title='Rischio Temporali Forti' style='display:inline-block; font-size:12px;'>⚠️⚡</span>"
        elif instab.get("allerta") == "giallo":
            badge_allerta = " <span title='Possibili Temporali' style='display:inline-block; font-size:12px;'>⚠️</span>"

        bg_color = d["pioggia"]["bg"]
        cielo_str = f"{d['cielo']['icona']}<br>{d['cielo']['testo']}"
        allerta_style = (
            f"background-color: {allerta_bg};"
            if allerta_bg != "transparent"
            else ""
        )

        html += (
            f"<tr style='border-bottom:1px solid #eee; height:36px; {allerta_style}'>"
            f"<td style='padding:2px 4px; text-align:left; white-space:nowrap; font-size:11px;'><b>{p_nome}</b>{fulmini}{badge_allerta}</td>"
            f"<td style='font-size:10px; padding:2px;'>{cielo_str}</td>"
            f"<td style='padding:2px;'>{d['pioggia']['gfs']}</td>"
            f"<td style='padding:2px;'>{d['pioggia']['icon']}</td>"
            f"<td style='padding:2px;'>{d['pioggia']['ecmwf']}</td>"
            f"<td style='background-color:{bg_color}; font-weight:bold; color:#1f77b4; padding:2px;'>{d['pioggia']['media']}</td>"
            "</tr>"
        )
    return html + "</table></div>"


def tabella_regionale_temperatura(regione_nome, dati_tabelle_regionali):
    html = (
        f"<div class='scheda-meteo s-temp' style='display:none;'>"
        f"<h3 style='margin:0 0 10px 0; color:#d62728; border-bottom:2px solid #d62728; "
        f"padding-bottom:5px; font-size:14px; text-align:center;'>{regione_nome}: Temperature e Dew Point</h3>"
        "<table style='width:100%; border-collapse:collapse; text-align:center; font-size:11px; "
        "border:1px solid #ddd; margin-top: 6px;'>"
        "<tr style='background-color:#f8f9fa; font-weight:bold; height:32px;'>"
        "<th style='padding: 4px 0; font-weight:bold;'>Provincia</th>"
        "<th style='color:blue; padding: 4px 0; font-weight:bold;'>07:00</th>"
        "<th style='color:red; padding: 4px 0; font-weight:bold;'>14:00</th>"
        "<th style='color:darkblue; padding: 4px 0; font-weight:bold;'>22:00</th></tr>"
    )
    for p_nome, d in dati_tabelle_regionali.get(regione_nome, {}).items():
        fulmini = " ⚡" if d["fulmini"] else ""
        bg_color_t14 = d["t14"]["bg"]
        t7_html = f"<b>{d['t7']['media']}°C</b><br><span style='font-size:9px; color:#555;'>DP: {d['t7'].get('dp', 'N/D')}°C</span>"
        t14_html = f"<b>{d['t14']['media']}</b><br><span style='font-size:9px; color:#555;'>DP: {d['t14'].get('dp', 'N/D')}°C</span>"
        t22_html = f"<b>{d['t22']['media']}°C</b><br><span style='font-size:9px; color:#555;'>DP: {d['t22'].get('dp', 'N/D')}°C</span>"

        html += (
            "<tr style='border-bottom:1px solid #eee; height:38px;'>"
            f"<td><b>{p_nome}{fulmini}</b></td>"
            f"<td style='color:blue; padding:2px 0;'>{t7_html}</td>"
            f"<td style='color:red; background-color:{bg_color_t14}; padding:2px 0;'>{t14_html}</td>"
            f"<td style='color:darkblue; padding:2px 0;'>{t22_html}</td>"
            "</tr>"
        )
    return html + "</table></div>"


def tabella_regionale_vento(regione_nome, dati_tabelle_regionali):
    html = (
        f"<div class='scheda-meteo s-vento' style='display:none;'>"
        f"<h3 style='margin:0 0 10px 0; color:#ff7f0e; border-bottom:2px solid #ff7f0e; "
        f"padding-bottom:5px; font-size:14px; text-align:center;'>{regione_nome}: Venti e Raffiche</h3>"
        "<table style='width:100%; border-collapse:collapse; text-align:center; font-size:11px; "
        "border:1px solid #ddd; margin-top: 6px;'>"
        "<tr style='background-color:#f8f9fa; font-weight:bold; height:32px;'> "
        "<th style='padding: 4px 0; font-weight:bold;'>Provincia</th>"
        "<th style='padding: 4px 0; font-weight:bold;'>GFS</th>"
        "<th style='padding: 4px 0; font-weight:bold;'>ICON</th>"
        "<th style='padding: 4px 0; font-weight:bold;'>ECMWF</th>"
        "<th style='background-color:#e6f2ff; padding: 4px 0; font-weight:bold;'>MEDIA</th>"
        "</tr>"
    )
    for p_nome, d in dati_tabelle_regionali.get(regione_nome, {}).items():
        fulmini = " ⚡" if d["fulmini"] else ""
        bg_color = d["vento"]["bg"]
        html += (
            "<tr style='border-bottom:1px solid #eee; height:34px;'>"
            f"<td><b>{p_nome}{fulmini}</b></td>"
            f"<td>{d['vento']['gfs']}</td>"
            f"<td>{d['vento']['icon']}</td>"
            f"<td>{d['vento']['ecmwf']}</td>"
            f"<td style='background-color:{bg_color}; font-weight:bold; color:#ff7f0e;'>{d['vento']['media']} km/h</td>"
            "</tr>"
        )
    return html + "</table></div>"


def tabella_regionale_smog(regione_nome, dati_tabelle_regionali):
    html = (
        f"<div class='scheda-meteo s-smog' style='display:none;'>"
        f"<h3 style='margin:0 0 10px 0; color:#9467bd; border-bottom:2px solid #9467bd; "
        f"padding-bottom:5px; font-size:14px; text-align:center;'>{regione_nome}: Qualità dell'Aria</h3>"
        "<table style='width:100%; border-collapse:collapse; text-align:center; font-size:11px; "
        "border:1px solid #ddd; margin-top: 6px;'>"
        "<tr style='background-color:#f8f9fa; font-weight:bold; height:32px;'> "
        "<th style='width:50%; padding: 4px 0; font-weight:bold;'>Provincia</th>"
        "<th style='width:50%; padding: 4px 0; font-weight:bold;'>Qualità</th>"
        "</tr>"
    )
    for p_nome, d in dati_tabelle_regionali.get(regione_nome, {}).items():
        fulmini = " ⚡" if d["fulmini"] else ""
        html += (
            "<tr style='border-bottom:1px solid #eee; height:34px;'>"
            f"<td><b>{p_nome}{fulmini}</b></td>"
            f"<td>{d['smog']['valore']} µg/m³</td>"
            f"<td style='background-color:#f3e6ff; font-weight:bold;'>{d['smog']['giudizio']}</td>"
            "</tr>"
        )
    return html + "</table></div>"


def tabella_regionale_uv(regione_nome, dati_tabelle_regionali):
    html = (
        f"<div class='scheda-meteo s-uv' style='display:none;'>"
        f"<h3 style='margin:0 0 10px 0; color:#e67e22; border-bottom:2px solid #e67e22; "
        f"padding-bottom:5px; font-size:14px; text-align:center;'>{regione_nome}: Indice UV</h3>"
        "<table style='width:100%; border-collapse:collapse; text-align:center; font-size:11px; "
        "border:1px solid #ddd; margin-top: 6px;'>"
        "<tr style='background-color:#f8f9fa; font-weight:bold; height:32px;'> "
        "<th style='width:40%; padding: 4px 0; font-weight:bold;'>Provincia</th>"
        "<th colspan='2' style='width:60%; padding: 4px 0; font-weight:bold;'>Indice UV</th>"
        "</tr>"
    )
    for p_nome, d in dati_tabelle_regionali.get(regione_nome, {}).items():
        fulmini = " ⚡" if d["fulmini"] else ""
        html += (
            "<tr style='border-bottom:1px solid #eee; height:34px;'>"
            f"<td><b>{p_nome}{fulmini}</b></td>"
            f"<td>{d['uv']['valore']}</td>"
            f"<td style='background-color:#ffe6ff; font-weight:bold;'>{d['uv']['giudizio']}</td>"
            "</tr>"
        )
    return html + "</table></div>"


# ==========================================
# FUNZIONE PRINCIPALE: MAPPA COMPLETA
# ==========================================
def genera_mappa_completa(day_index: int, nome_file: str):
    print(f"\n=== GENERAZIONE MAPPA PER GIORNO {day_index} → {nome_file} ===")

    dt_target = ora_italiana + timedelta(days=day_index)
    data_validita = dt_target.strftime("%d/%m/%Y")
    data_target_str = dt_target.strftime("%Y-%m-%d")

    dati_render_mappa = []
    dati_tabelle_regionali = {}

    for regione, elenco in PROVINCE_BY_REGIONE.items():
        dati_tabelle_regionali[regione] = {}

        for p in elenco:
            time.sleep(0.15)
            nome_provincia = p["nome"]
            lat_float = float(p["lat"])
            lon_float = float(p["lon"])

            base_t7 = base_t14 = base_t22 = 0.0
            base_pm10 = 15.0
            base_uv = 0.0
            dir_testo = "N/D"
            ha_fulmini = False
            percentuale_nuvole = 0

            prec_gfs = prec_icon = prec_ecmwf = prec_media = None
            snow_gfs = snow_icon = snow_ecmwf = snow_media = None
            wind_gfs = wind_icon = wind_ecmwf = wind_media = None
            gust_gfs = gust_icon = gust_ecmwf = gust_media = None

            colore_allerta, nome_allerta_dpc = ottieni_allerta_dpc_spaziale(
                lat_float, lon_float, data_target_str
            )
            cape_max = 0.0
            li_min = 0.0
            ora_picco_instabile = "N/D"
            livello_allerta_instabilita = "nessuna"

            try:
                url = (
                    "http://api.weatherapi.com/v1/forecast.json?"
                    f"key={API_KEY}&q={lat_float},{lon_float}&days=3&aqi=yes&alerts=yes"
                )
                res = session.get(url, timeout=10).json()

                if colore_allerta == "transparent" and day_index <= 1:
                    colore_allerta = estrai_colore_allerta_weatherapi(
                        res, nome_provincia=nome_provincia
                    )

                giorni = res.get("forecast", {}).get("forecastday", [])
                if day_index < len(giorni):
                    giorno = giorni[day_index]
                    ore = giorno["hour"]
                    base_t7 = float(ore[7]["temp_c"])
                    base_t14 = float(ore[14]["temp_c"])
                    base_t22 = float(ore[22]["temp_c"])
                    dir_testo = str(ore[14]["wind_dir"])
                    base_uv = float(giorno["day"]["uv"])
                    base_pm10 = float(
                        res.get("current", {})
                        .get("air_quality", {})
                        .get("pm10", 15)
                    )
                    percentuale_nuvole = int(
                        sum(o.get("cloud", 0) for o in ore) / len(ore)
                    )
                    ha_fulmini = any(
                        int(ora["condition"]["code"])
                        in [1087, 1273, 1276, 1279, 1282]
                        for ora in ore
                    )

                url_models = (
                    f"https://api.open-meteo.com/v1/forecast?"
                    f"latitude={lat_float}&longitude={lon_float}"
                    f"&daily=precipitation_sum,snowfall_sum,wind_speed_10m_max,wind_gusts_10m_max"
                    f"&hourly=temperature_2m,dew_point_2m,cape,lifted_index"
                    f"&models=gfs_seamless,icon_seamless,ecmwf_ifs025"
                    f"&timezone=Europe/Rome"
                )
                res_m = session.get(url_models, timeout=10).json()
                daily_m = res_m.get("daily", {})
                hourly_m = res_m.get("hourly", {})

                def safe_get(arr, idx, default=0.0):
                    if arr and idx < len(arr) and arr[idx] is not None:
                        return float(arr[idx])
                    return default

                dp7_m = dp14_m = dp22_m = 0.0
                if hourly_m:
                    idx_7 = (day_index * 24) + 7
                    idx_14 = (day_index * 24) + 14
                    idx_22 = (day_index * 24) + 22
                    for idx, key in [
                        (idx_7, "dp7"),
                        (idx_14, "dp14"),
                        (idx_22, "dp22"),
                    ]:
                        dp_gfs = safe_get(
                            hourly_m.get("dew_point_2m_gfs_seamless"), idx, 0.0
                        )
                        dp_icon = safe_get(
                            hourly_m.get("dew_point_2m_icon_seamless"),
                            idx,
                            0.0,
                        )
                        dp_ecmwf = safe_get(
                            hourly_m.get("dew_point_2m_ecmwf_ifs025"), idx, 0.0
                        )
                        val_dp = round((dp_gfs + dp_icon + dp_ecmwf) / 3.0, 1)
                        if key == "dp7":
                            dp7_m = val_dp
                        elif key == "dp14":
                            dp14_m = val_dp
                        elif key == "dp22":
                            dp22_m = val_dp

                    cape_list = hourly_m.get("cape", [])
                    li_list = hourly_m.get("lifted_index", [])
                    start_h = day_index * 24
                    end_h = start_h + 24
                    if cape_list and len(cape_list) >= end_h:
                        cape_giorno = [
                            c if c is not None else 0.0
                            for c in cape_list[start_h:end_h]
                        ]
                        li_giorno = (
                            [
                                l if l is not None else 0.0
                                for l in li_list[start_h:end_h]
                            ]
                            if li_list
                            else [0.0] * 24
                        )
                        cape_max = round(max(cape_giorno), 0)
                        li_min = round(min(li_giorno), 1)
                        idx_max_cape = cape_giorno.index(max(cape_giorno))
                        ora_picco_instabile = f"{idx_max_cape:02d}:00-{(idx_max_cape+2)%24:02d}:00"
                        if cape_max >= 1200 or li_min <= -3.5:
                            livello_allerta_instabilita = "rosso"
                        elif cape_max >= 300 or li_min <= -1.0 or ha_fulmini:
                            livello_allerta_instabilita = "giallo"

                if daily_m:
                    prec_gfs = safe_get(
                        daily_m.get("precipitation_sum_gfs_seamless"),
                        day_index,
                        0.0,
                    )
                    prec_icon = safe_get(
                        daily_m.get("precipitation_sum_icon_seamless"),
                        day_index,
                        0.0,
                    )
                    prec_ecmwf = safe_get(
                        daily_m.get("precipitation_sum_ecmwf_ifs025"),
                        day_index,
                        0.0,
                    )
                    prec_media = round(
                        (prec_gfs + prec_icon + prec_ecmwf) / 3.0, 1
                    )
                    snow_gfs = safe_get(
                        daily_m.get("snowfall_sum_gfs_seamless"),
                        day_index,
                        0.0,
                    )
                    snow_icon = safe_get(
                        daily_m.get("snowfall_sum_icon_seamless"),
                        day_index,
                        0.0,
                    )
                    snow_ecmwf = safe_get(
                        daily_m.get("snowfall_sum_ecmwf_ifs025"),
                        day_index,
                        0.0,
                    )
                    wind_gfs = safe_get(
                        daily_m.get("wind_speed_10m_max_gfs_seamless"),
                        day_index,
                        10.0,
                    )
                    wind_icon = safe_get(
                        daily_m.get("wind_speed_10m_max_icon_seamless"),
                        day_index,
                        10.0,
                    )
                    wind_ecmwf = safe_get(
                        daily_m.get("wind_speed_10m_max_ecmwf_ifs025"),
                        day_index,
                        10.0,
                    )
                    wind_media = round(
                        (wind_gfs + wind_icon + wind_ecmwf) / 3.0, 1
                    )
                    gust_gfs = safe_get(
                        daily_m.get("wind_gusts_10m_max_gfs_seamless"),
                        day_index,
                        10.0,
                    )
                    gust_icon = safe_get(
                        daily_m.get("wind_gusts_10m_max_icon_seamless"),
                        day_index,
                        10.0,
                    )
                    gust_ecmwf = safe_get(
                        daily_m.get("wind_gusts_10m_max_ecmwf_ifs025"),
                        day_index,
                        10.0,
                    )
                    gust_media = round(
                        (gust_gfs + gust_icon + gust_ecmwf) / 3.0, 1
                    )
            except Exception as e:
                print(f"⚠️ Errore API per {nome_provincia}: {e}")

            if percentuale_nuvole <= 20:
                icona_cielo, testo_cielo = "☀️", "Sereno"
            elif percentuale_nuvole <= 50:
                icona_cielo, testo_cielo = "⛅", "Poco Nuv."
            elif percentuale_nuvole <= 80:
                icona_cielo, testo_cielo = "☁️", "Nuvoloso"
            else:
                icona_cielo, testo_cielo = "☁️☁️", "Coperto"

            giudizio_smog = (
                "Buona"
                if base_pm10 < 20
                else (
                    "Discreta"
                    if base_pm10 < 40
                    else ("Mediocre" if base_pm10 < 60 else "Scadente")
                )
            )
            giudizio_uv = (
                "Basso"
                if base_uv < 3
                else (
                    "Moderato"
                    if base_uv < 6
                    else ("Alto" if base_uv < 8 else "Molto alto")
                )
            )

            if prec_gfs is None:
                (
                    p_bg,
                    prec_media_str,
                    val_pioggia_mappa,
                    modelli_con_neve,
                ) = ("#e0e0e0", "N/D", -1.0, 0)
            else:
                modelli_con_neve = sum(
                    [
                        1
                        for s in [snow_gfs, snow_icon, snow_ecmwf]
                        if s is not None and s >= 1.0
                    ]
                )
                snow_media_val = round(
                    (snow_gfs + snow_icon + snow_ecmwf) / 3.0, 1
                )
                if modelli_con_neve >= 2:
                    (
                        p_bg,
                        prec_media_str,
                        val_pioggia_mappa,
                    ) = ("#e0f7fa", f"{snow_media_val} cm ❄️", snow_media_val)
                elif modelli_con_neve == 1:
                    (
                        p_bg,
                        prec_media_str,
                        val_pioggia_mappa,
                    ) = ("#fff3cd", f"{snow_media_val} cm 🌨️?", snow_media_val)
                else:
                    prec_m = round(prec_media, 1)
                    val_pioggia_mappa = prec_m
                    p_ic = (
                        " 💧⚠️"
                        if prec_m >= 60.0
                        else (" 💧" if prec_m >= 15.0 else "")
                    )
                    p_bg = (
                        "#f8d7da"
                        if prec_m >= 60.0
                        else (
                            "#ffe8cc"
                            if prec_m >= 30.0
                            else ("#fff3cd" if prec_m >= 15.0 else "#e6f2ff")
                        )
                    )
                    prec_media_str = f"{prec_m} mm{p_ic}"

            t14_m = round(base_t14, 1)
            t_ic = " ☀️⚠️" if t14_m >= 38.0 else (" ☀️" if t14_m >= 32.0 else "")
            t_bg = (
                "#f8d7da"
                if t14_m >= 38.0
                else (
                    "#ffe8cc"
                    if t14_m >= 35.0
                    else ("#fff3cd" if t14_m >= 32.0 else "#ffe6e6")
                )
            )

            if wind_media is None:
                (
                    w_bg,
                    w_ic,
                    wind_media_str,
                    val_vento_mappa,
                ) = ("#e0e0e0", "", "N/D", -1.0)
            else:
                wind_m, gust_m = round(wind_media, 1), round(gust_media, 1)
                wind_media_str = f"{wind_m} ({gust_m}) {dir_testo}"
                val_vento_mappa = gust_m
                w_ic = (
                    " 💨⚠️"
                    if gust_m >= 85.0
                    else (" 💨" if gust_m >= 45.0 else "")
                )
                w_bg = (
                    "#f8d7da"
                    if gust_m >= 85.0
                    else (
                        "#ffe8cc"
                        if gust_m >= 65.0
                        else ("#fff3cd" if gust_m >= 45.0 else "#ffe6cc")
                    )
                )

            info = {
                "nome": nome_provincia,
                "tipo": "capoluogo",
                "regione": regione,
                "lat": lat_float,
                "lon": lon_float,
                "fulmini": ha_fulmini,
                "colore_allerta": colore_allerta,
                "allerta_dpc_nome": nome_allerta_dpc,
                "instabilita": {
                    "cape_max": cape_max,
                    "lifted_index": li_min,
                    "ora_picco": ora_picco_instabile,
                    "allerta": livello_allerta_instabilita,
                },
                "cielo": {
                    "copertura": percentuale_nuvole,
                    "icona": icona_cielo,
                    "testo": testo_cielo,
                },
                "pioggia": {
                    "gfs": (
                        f"{round(snow_gfs, 1)} cm"
                        if (prec_gfs is not None and modelli_con_neve >= 1)
                        else (
                            round(prec_gfs, 1)
                            if prec_gfs is not None
                            else "N/D"
                        )
                    ),
                    "icon": (
                        f"{round(snow_icon, 1)} cm"
                        if (prec_icon is not None and modelli_con_neve >= 1)
                        else (
                            round(prec_icon, 1)
                            if prec_icon is not None
                            else "N/D"
                        )
                    ),
                    "ecmwf": (
                        f"{round(snow_ecmwf, 1)} cm"
                        if (prec_ecmwf is not None and modelli_con_neve >= 1)
                        else (
                            round(prec_ecmwf, 1)
                            if prec_ecmwf is not None
                            else "N/D"
                        )
                    ),
                    "val_media": val_pioggia_mappa,
                    "media": prec_media_str,
                    "bg": p_bg,
                },
                "t7": {"media": round(base_t7, 1), "dp": dp7_m},
                "t14": {
                    "val_media": t14_m,
                    "media": f"{t14_m} °C{t_ic}",
                    "bg": t_bg,
                    "dp": dp14_m,
                },
                "t22": {"media": round(base_t22, 1), "dp": dp22_m},
                "vento": {
                    "gfs": (
                        f"{round(wind_gfs, 1)} ({round(gust_gfs, 1)})"
                        if wind_gfs is not None
                        else "N/D"
                    ),
                    "icon": (
                        f"{round(wind_icon, 1)} ({round(gust_icon, 1)})"
                        if wind_icon is not None
                        else "N/D"
                    ),
                    "ecmwf": (
                        f"{round(wind_ecmwf, 1)} ({round(gust_ecmwf, 1)})"
                        if wind_ecmwf is not None
                        else "N/D"
                    ),
                    "val_media": val_vento_mappa,
                    "media": f"{wind_media_str}{w_ic}",
                    "bg": w_bg,
                    "dir": dir_testo if wind_media is not None else "N/D",
                },
                "smog": {
                    "valore": round(base_pm10, 1),
                    "giudizio": giudizio_smog,
                },
                "uv": {"valore": round(base_uv, 1), "giudizio": giudizio_uv},
            }

            dati_render_mappa.append(info)
            dati_tabelle_regionali[regione][nome_provincia] = info

    print("🗺️ Disegno della mappa interattiva in corso...")
    map_italia = folium.Map(
        location=[41.9, 12.5],
        zoom_start=5,
        tiles=None,
        zoom_control=False,
    )

    map_italia.fit_bounds([[36.0, 6.0], [47.5, 18.5]])

    folium.TileLayer(
        tiles=f"https://basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}.png?key={CARTO_API_KEY}",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        name="CARTO Voyager",
        max_zoom=19,
    ).add_to(map_italia)

    for d in dati_render_mappa:
        raggio_mappa = 28000
        hex_p = (
            "001d58"
            if d["pioggia"]["val_media"] >= 15
            else (
                "225ea8"
                if d["pioggia"]["val_media"] >= 5
                else "41b6c4" if d["pioggia"]["val_media"] >= 1 else "a1dab4"
            )
        )
        folium.Circle(
            location=[d["lat"], d["lon"]],
            radius=raggio_mappa,
            color="transparent",
            weight=0,
            fill=True,
            fill_opacity=0.7,
            className=f"v-filtro v-pioggia sfumatura-{hex_p}",
        ).add_to(map_italia)

        t_val = d["t14"]["val_media"]
        hex_t = (
            "d73027"
            if t_val >= 28
            else (
                "f46d43"
                if t_val >= 22
                else "fee08b" if t_val >= 15 else "1a9850"
            )
        )
        folium.Circle(
            location=[d["lat"], d["lon"]],
            radius=raggio_mappa,
            color="transparent",
            weight=0,
            fill=True,
            fill_opacity=0.7,
            className=f"v-filtro v-temp sfumatura-{hex_t}",
        ).add_to(map_italia)

        hex_w = (
            "d73027"
            if d["vento"]["val_media"] >= 25
            else "fee090" if d["vento"]["val_media"] >= 10 else "e0f3f8"
        )
        folium.Circle(
            location=[d["lat"], d["lon"]],
            radius=raggio_mappa,
            color="transparent",
            weight=0,
            fill=True,
            fill_opacity=0.7,
            className=f"v-filtro v-vento sfumatura-{hex_w}",
        ).add_to(map_italia)

        hex_s = (
            "f46d43"
            if d["smog"]["valore"] >= 40
            else "fee08b" if d["smog"]["valore"] >= 20 else "66bd63"
        )
        folium.Circle(
            location=[d["lat"], d["lon"]],
            radius=raggio_mappa,
            color="transparent",
            weight=0,
            fill=True,
            fill_opacity=0.7,
            className=f"v-filtro v-smog sfumatura-{hex_s}",
        ).add_to(map_italia)

        hex_uv = (
            "66bd63"
            if d["uv"]["valore"] < 3
            else (
                "fee08b"
                if d["uv"]["valore"] < 6
                else "f46d43" if d["uv"]["valore"] < 8 else "d73027"
            )
        )
        folium.Circle(
            location=[d["lat"], d["lon"]],
            radius=raggio_mappa,
            color="transparent",
            weight=0,
            fill=True,
            fill_opacity=0.7,
            className=f"v-filtro v-uv sfumatura-{hex_uv}",
        ).add_to(map_italia)

    for r_nome, coord in REGIONI_COORDINATE.items():
        id_pulito = r_nome.replace(" ", "-").replace("'", "-")
        html_indicatore_nativo = f"""
        <div class="regione-marker-item" data-regione="{id_pulito}" title="{r_nome}"
             style="width: 36px; height: 36px; background-color: white; border: 3px solid #2c3e50;
                    border-radius: 50%; cursor: pointer; box-shadow: 0px 2px 6px rgba(0,0,0,0.3);
                    transform: translate(-18px, -18px); z-index: 99999; pointer-events: auto !important;"></div>
        """
        folium.Marker(
            location=coord,
            icon=folium.DivIcon(
                html=html_indicatore_nativo, icon_size=(36, 36)
            ),
        ).add_to(map_italia)

    interfaccia_mappa_html = """
    <style>
        .leaflet-container { touch-action: manipulation !important; }
        .regione-marker-item { touch-action: manipulation !important; cursor: pointer !important; }
        .v-filtro { opacity: 0 !important; pointer-events: none !important; transition: opacity 0.2s ease; }
        .v-attivo { opacity: 0.7 !important; pointer-events: none !important; }
        .sfumatura-a1dab4 { fill: url(#grad-a1dab4) !important; } .sfumatura-41b6c4 { fill: url(#grad-41b6c4) !important; }
        .sfumatura-225ea8 { fill: url(#grad-225ea8) !important; } .sfumatura-001d58 { fill: url(#grad-001d58) !important; }
        .sfumatura-1a9850 { fill: url(#grad-1a9850) !important; } .sfumatura-fee08b { fill: url(#grad-fee08b) !important; }
        .sfumatura-f46d43 { fill: url(#grad-f46d43) !important; } .sfumatura-d73027 { fill: url(#grad-d73027) !important; }
        .sfumatura-e0f3f8 { fill: url(#grad-e0f3f8) !important; } .sfumatura-fee090 { fill: url(#grad-fee090) !important; }
        .sfumatura-66bd63 { fill: url(#grad-66bd63) !important; } .sfumatura-4575b4 { fill: url(#grad-4575b4) !important; }
    </style>
    <svg width="0" height="0"><defs>
        <radialGradient id="grad-a1dab4"><stop offset="0%" stop-color="#a1dab4" stop-opacity="0.8"/><stop offset="100%" stop-color="#a1dab4" stop-opacity="0"/></radialGradient>
        <radialGradient id="grad-41b6c4"><stop offset="0%" stop-color="#41b6c4" stop-opacity="0.85"/><stop offset="100%" stop-color="#41b6c4" stop-opacity="0"/></radialGradient>
        <radialGradient id="grad-225ea8"><stop offset="0%" stop-color="#225ea8" stop-opacity="0.9"/><stop offset="100%" stop-color="#225ea8" stop-opacity="0"/></radialGradient>
        <radialGradient id="grad-001d58"><stop offset="0%" stop-color="#001d58" stop-opacity="0.95"/><stop offset="100%" stop-color="#001d58" stop-opacity="0"/></radialGradient>
        <radialGradient id="grad-1a9850"><stop offset="0%" stop-color="#1a9850" stop-opacity="0.8"/><stop offset="100%" stop-color="#1a9850" stop-opacity="0"/></radialGradient>
        <radialGradient id="grad-fee08b"><stop offset="0%" stop-color="#fee08b" stop-opacity="0.8"/><stop offset="100%" stop-color="#fee08b" stop-opacity="0"/></radialGradient>
        <radialGradient id="grad-f46d43"><stop offset="0%" stop-color="#f46d43" stop-opacity="0.85"/><stop offset="100%" stop-color="#f46d43" stop-opacity="0"/></radialGradient>
        <radialGradient id="grad-d73027"><stop offset="0%" stop-color="#d73027" stop-opacity="0.95"/><stop offset="100%" stop-color="#d73027" stop-opacity="0"/></radialGradient>
        <radialGradient id="grad-e0f3f8"><stop offset="0%" stop-color="#e0f3f8" stop-opacity="0.8"/><stop offset="100%" stop-color="#e0f3f8" stop-opacity="0"/></radialGradient>
        <radialGradient id="grad-fee090"><stop offset="0%" stop-color="#fee090" stop-opacity="0.85"/><stop offset="100%" stop-color="#fee090" stop-opacity="0"/></radialGradient>
        <radialGradient id="grad-66bd63"><stop offset="0%" stop-color="#66bd63" stop-opacity="0.8"/><stop offset="100%" stop-color="#66bd63" stop-opacity="0"/></radialGradient>
        <radialGradient id="grad-4575b4"><stop offset="0%" stop-color="#4575b4" stop-opacity="0.85"/><stop offset="100%" stop-color="#4575b4" stop-opacity="0"/></radialGradient>
    </defs></svg>
    """
    map_italia.get_root().html.add_child(folium.Element(interfaccia_mappa_html))

    branding_html = f"""
    <div style="position: fixed; bottom: 10px; left: 50%; transform: translateX(-50%); z-index: 999; display: flex; flex-direction: column; align-items: center; gap: 6px; font-family: Arial, sans-serif; pointer-events: none;">
        <div style="background-color: rgba(200, 0, 0, 0.95); color: white; padding: 5px 12px; border-radius: 12px; font-size: 11px; font-weight: bold; border: 2px solid white; box-shadow: 0px 3px 8px rgba(0,0,0,0.3); white-space: nowrap; text-align: center;">
            Previsione valida per il: {data_validita}
        </div>
        <div style="background-color: rgba(255,255,255,0.9); padding: 3px 8px; border-radius: 4px; font-size: 9px; color: #333; border: 1px solid #ccc; box-shadow: 0px 2px 5px rgba(0,0,0,0.1); white-space: nowrap; text-align: center;">
            <b>{COPYRIGHT}</b> | <span style="color:#666;">{FONTE_DATI}</span>
        </div>
    </div>
    <div style="position: fixed; top: 12px; left: 15px; background-color: rgba(255,255,255,0.9); padding: 5px 10px; border-radius: 4px; z-index: 999; font-family: Arial, sans-serif; font-size: 11px; color: #005580; font-weight: bold; border: 1px solid #ccc; box-shadow: 0px 2px 5px rgba(0,0,0,0.1); white-space: nowrap;">
      {STRINGA_AGGIORNAMENTO}
    </div>
    """
    map_italia.get_root().html.add_child(folium.Element(branding_html))

    map_italia.save(nome_file)
    print(f"✅ Mappa salvata con successo in: {nome_file}")


# ==========================================
# GENERAZIONE FILE INDEX COMPLETO
# ==========================================
def genera_index_html():
    d0 = ora_italiana.strftime("%d/%m/%Y")
    d1 = (ora_italiana + timedelta(days=1)).strftime("%d/%m/%Y")
    d2 = (ora_italiana + timedelta(days=2)).strftime("%d/%m/%Y")

    bottoni_regioni_mobile_html = ""
    for r_nome in sorted(REGIONI_COORDINATE.keys()):
        id_pulito = r_nome.replace(" ", "-").replace("'", "-")
        bottoni_regioni_mobile_html += (
            f'<button onclick="selezionaRegioneDaMobile(\'{id_pulito}\')" '
            'style="background:#f1f5f9; border:1px solid #cbd5e1; padding:10px 8px; border-radius:6px; font-size:12px; font-weight:bold; color:#2c3e50; cursor:pointer; text-align:center; pointer-events:auto !important; touch-action:manipulation !important;">'
            f"{r_nome}</button>"
        )

    html_content = """<!DOCTYPE html>
<html>
<head>
    <title>Previsioni Meteo McSpark</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        html, body { 
            font-family: Arial, sans-serif; 
            text-align: center; 
            margin: 0; 
            padding: 0; 
            background-color: #f8f9fa; 
            height: 100dvh;
            overflow: hidden;
        }
        .header-bar {
            background-color: #2c3e50;
            background-image: radial-gradient(rgba(255, 255, 255, 0.15) 1px, transparent 1px);
            background-size: 4px 4px;
            padding: 8px 0 10px 0;
            box-shadow: 0 4px 15px rgba(0,0,0,0.25);
            position: relative;
            z-index: 1000;
        }
        h2 { 
            margin: 0 0 6px 0; 
            color: #ffffff; 
            font-size: 18px; 
            letter-spacing: 0.5px;
        }
        .btn-bar button {
            display: inline-block;
            text-decoration: none;
            margin: 0 4px;
            padding: 6px 14px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            border-radius: 6px;
            border: 1px solid #4a5d71;
            background-color: #34495e;
            color: #cbd5e1;
            transition: all 0.2s ease;
            text-align: center;
        }
        .btn-bar button.active {
            background-color: #ffffff !important;
            color: #2c3e50 !important;
            border-color: #ffffff !important;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
        }
        iframe { 
            width: 100%; 
            height: calc(100dvh - 65px); 
            border: none; 
            display: block; 
            position: absolute;
            top: 65px;
            left: 0;
            z-index: 1;
        }

        .mobile-nav-bar { display: none; }
        .btn-chiudi-sheet { display: none; }
        #pannello-regioni-mobile, #legenda-mappa-mobile { display: none; }

        @media (max-width: 768px) {
            .mobile-nav-bar {
                display: flex !important;
                position: fixed !important;
                bottom: 12px !important;
                left: 10px !important;
                right: 10px !important;
                height: 56px !important;
                background: #2c3e50 !important;
                border-radius: 14px !important;
                z-index: 2147483647 !important;
                box-shadow: 0 4px 20px rgba(0,0,0,0.5) !important;
                pointer-events: auto !important;
                touch-action: manipulation !important;
                border: 1px solid rgba(255,255,255,0.3);
            }
            .mobile-nav-btn {
                flex: 1 !important;
                display: flex !important;
                flex-direction: column !important;
                align-items: center !important;
                justify-content: center !important;
                color: #cbd5e1 !important;
                font-size: 10px !important;
                font-weight: bold !important;
                background: none !important;
                border: none !important;
                padding: 4px 0 !important;
                cursor: pointer !important;
                pointer-events: auto !important;
                touch-action: manipulation !important;
            }
            .mobile-nav-btn span { font-size: 18px !important; margin-bottom: 2px !important; pointer-events: none !important; }

            #pannello-regioni-mobile, #legenda-mappa-mobile {
                position: fixed !important;
                top: auto !important;
                left: 0 !important;
                right: 0 !important;
                bottom: -100% !important;
                display: none !important;
                width: 100% !important;
                max-width: 100% !important;
                height: auto !important;
                max-height: 55dvh !important;
                border-radius: 18px 18px 0 0 !important;
                border: none !important;
                border-top: 3px solid #2c3e50 !important;
                transition: bottom 0.3s ease !important;
                z-index: 2147483646 !important;
                box-shadow: 0 -5px 25px rgba(0,0,0,0.4) !important;
                background: #ffffff !important;
                padding: 12px 14px !important;
                padding-bottom: calc(75px + env(safe-area-inset-bottom, 0px)) !important;
                box-sizing: border-box !important;
                overflow-y: auto !important;
                pointer-events: auto !important;
                touch-action: pan-y !important;
            }
            .sheet-aperto { display: block !important; bottom: 0 !important; }
            .btn-chiudi-sheet {
                display: block !important;
                position: absolute !important;
                top: 10px !important;
                right: 15px !important;
                background: #e2e8f0 !important;
                border: none !important;
                border-radius: 50% !important;
                width: 32px !important;
                height: 32px !important;
                font-weight: bold !important;
                color: #334155 !important;
                font-size: 16px !important;
                line-height: 32px !important;
                text-align: center !important;
                cursor: pointer !important;
                pointer-events: auto !important;
                touch-action: manipulation !important;
            }
            .drag-handle { width: 40px; height: 5px; background: #cbd5e1; border-radius: 3px; margin: 0 auto 10px auto; }
            .griglia-regioni-mobile { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 10px; }
            h4 { margin: 0 0 10px 0; font-size: 13px; color: #2c3e50; border-bottom: 2px solid #2c3e50; padding-bottom: 5px; text-align: center; font-weight: bold; }
        }
    </style>
</head>
<body>
    <div class="header-bar">
        <h2>Previsioni Meteo McSpark</h2>
        <div class="btn-bar">
            <button onclick="carica('day1.html', this)" class="active">D0_VAL</button>
            <button onclick="carica('day2.html', this)">D1_VAL</button>
            <button onclick="carica('day3.html', this)">D2_VAL</button>
        </div>
    </div>
    
    <iframe id="frame" src="day1.html?v=1"></iframe>

    <div class="mobile-nav-bar">
        <button class="mobile-nav-btn" onclick="apriSheetMobile('pannello-regioni-mobile')">
            <span>📍</span>Regioni
        </button>
        <button class="mobile-nav-btn" onclick="apriSheetMobile('legenda-mappa-mobile')">
            <span>⚠️</span>Legenda
        </button>
    </div>

    <div id="pannello-regioni-mobile">
        <div class="drag-handle"></div>
        <button class="btn-chiudi-sheet" onclick="chiudiTuttiSheets()">✕</button>
        <h4>📍 SCEGLI REGIONE</h4>
        <div class="griglia-regioni-mobile">
            REGIONI_GRID_HTML
        </div>
    </div>

    <div id="legenda-mappa-mobile">
        <div class="drag-handle"></div>
        <button class="btn-chiudi-sheet" onclick="chiudiTuttiSheets()">✕</button>
        <h4>🎨 Legenda & Allerte</h4>
        <div style="text-align:left; font-size:12px; line-height:1.8; padding:5px 10px;">
            🔴 <b>Allerta Rossa</b><br>
            🟠 <b>Allerta Arancione</b><br>
            🟡 <b>Allerta Gialla</b><br>
            ⚠️⚡ <b>Rischio Temporali</b><br>
            ❄️ <b>Neve Prevista</b>
        </div>
    </div>

<script>
function carica(file, elemento) {
    document.getElementById('frame').src = file + '?v=' + new Date().getTime();
    var bottoni = document.querySelectorAll('.header-bar button');
    bottoni.forEach(function(btn) { btn.classList.remove('active'); });
    elemento.classList.add('active');
}

function chiudiTuttiSheets() {
    var regMob = document.getElementById('pannello-regioni-mobile');
    var legMob = document.getElementById('legenda-mappa-mobile');
    if (regMob) regMob.classList.remove('sheet-aperto');
    if (legMob) legMob.classList.remove('sheet-aperto');
}

function apriSheetMobile(idSheet) {
    if (window.innerWidth <= 768) {
        chiudiTuttiSheets();
        var target = document.getElementById(idSheet);
        if (target) target.classList.add('sheet-aperto');
    }
}

function selezionaRegioneDaMobile(idReg) {
    chiudiTuttiSheets();
}
</script>
</body>
</html>"""

    html_content = (
        html_content.replace("D0_VAL", d0)
        .replace("D1_VAL", d1)
        .replace("D2_VAL", d2)
        .replace("REGIONI_GRID_HTML", bottoni_regioni_mobile_html)
    )

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)


if __name__ == "__main__":
    genera_mappa_completa(0, "day1.html")
    genera_mappa_completa(1, "day2.html")
    genera_mappa_completa(2, "day3.html")
    genera_index_html()
