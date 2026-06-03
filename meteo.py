import os
import requests
import folium
import time
from datetime import datetime
import zoneinfo
from province_italia import PROVINCE_BY_REGIONE, REGIONI_COORDINATE

# ==========================================
# CONFIGURAZIONE, TIMESTAMP E BRANDING
# ==========================================
NOME_SITO = "McSpark Meteo"
COPYRIGHT = f"© 2026 {NOME_SITO} - Tutti i diritti riservati"
FONTE_DATI = "Dati REALI: Multi-Modello Deterministico (ECMWF IFS / GFS / ICON)"
FILE_LOGO_LOCAL = "unnamed.jpg" 

# Calcolo automatico del fuso orario italiano per i server GitHub
ora_italiana = datetime.now(zoneinfo.ZoneInfo("Europe/Rome"))
STRINGA_AGGIORNAMENTO = ora_italiana.strftime("Aggiornato il: %d/%m/%Y alle %H:%M")

print(f"🌊✨ {NOME_SITO}: Avvio motore multi-modello ultra-rapido ({STRINGA_AGGIORNAMENTO})...")

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
    "Basso Adriatico": {"lat": 41.30, "lon": 17.50},
    "Mar Ionio": {"lat": 39.00, "lon": 17.80},
    "Mare di Sicilia": {"lat": 36.80, "lon": 13.50}
}

def gradi_a_punti_cardinali(deg):
    if deg is None: return "N"
    deg = deg % 360
    punti = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return punti[int((deg + 11.25) / 22.5) % 16]

# ==========================================
# 1. SCARICAMENTO DI MASSA (BULK) - TUTTE LE PROVINCE IN 1 SOLA CHIAMATA
# ==========================================
elenco_province_piatto = []
lats = []
lons = []

for regione, elenco in PROVINCE_BY_REGIONE.items():
    for p in elenco:
        elenco_province_piatto.append({"nome": p["nome"], "regione": regione, "lat": float(p["lat"]), "lon": float(p["lon"])})
        lats.append(str(p["lat"]))
        lons.append(str(p["lon"]))

stringa_lats = ",".join(lats)
stringa_lons = ",".join(lons)

print("📦 Download in blocco dei dati meteorologici (1 sola richiesta per 110 province)...")
url_bulk = (
    f"https://api.open-meteo.com/v1/forecast?latitude={stringa_lats}&longitude={stringa_lons}"
    "&hourly=temperature_2m,precipitation,wind_speed_10m,wind_direction_10m,weather_code"
    "&models=gfs_seamless,icon_seamless,ecmwf_ifs04&forecast_days=1&timezone=Europe/Rome"
)

url_aqi_bulk = (
    f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={stringa_lats}&longitude={stringa_lons}"
    "&hourly=pm10&forecast_days=1&timezone=Europe/Rome"
)

try:
    res_meteo = requests.get(url_bulk, timeout=30).json()
    res_aqi = requests.get(url_aqi_bulk, timeout=30).json()
except Exception as e:
    print(f"❌ Errore fatale nel download dei dati di massa: {e}")
    res_meteo = []
    res_aqi = []

# Normalizzazione output se arriva un dizionario singolo invece di una lista
if isinstance(res_meteo, dict) and "hourly" in res_meteo: res_meteo = [res_meteo]
if isinstance(res_aqi, dict) and "hourly" in res_aqi: res_aqi = [res_aqi]

# ==========================================
# 2. ELABORAZIONE E STRUTTURAZIONE DATI
# ==========================================
dati_render_mappa = []
dati_tabelle_regionali = {r: {} for r in PROVINCE_BY_REGIONE.keys()}

for idx, prov in enumerate(elenco_province_piatto):
    p_data = {
        "pioggia_gfs": 0.0, "pioggia_icon": 0.0, "pioggia_ecmwf": 0.0, "pioggia_media": 0.0,
        "t7": 14.0, "t14": 22.0, "t22": 17.0,
        "vento_gfs": 10.0, "vento_icon": 10.0, "vento_ecmwf": 10.0, "vento_media": 10.0,
        "dir_testo": "N", "fulmini": False, "pm10": 15.0
    }
    
    if idx < len(res_meteo) and isinstance(res_meteo, list) and "hourly" in res_meteo[idx]:
        h = res_meteo[idx]["hourly"]
        p_data["pioggia_gfs"] = round(sum(h.get("precipitation_gfs_seamless", [0]*24)[:24]), 1)
        p_data["pioggia_icon"] = round(sum(h.get("precipitation_icon_seamless", [0]*24)[:24]), 1)
        p_data["pioggia_ecmwf"] = round(sum(h.get("precipitation_ecmwf_ifs04", [0]*24)[:24]), 1)
        p_data["pioggia_media"] = round((p_data["pioggia_gfs"] + p_data["pioggia_icon"] + p_data["pioggia_ecmwf"]) / 3, 1)
        
        p_data["t7"] = round((h.get("temperature_2m_gfs_seamless", [14]*24)[7] + h.get("temperature_2m_icon_seamless", [14]*24)[7] + h.get("temperature_2m_ecmwf_ifs04", [14]*24)[7]) / 3, 1)
        p_data["t14"] = round((h.get("temperature_2m_gfs_seamless", [22]*24)[14] + h.get("temperature_2m_icon_seamless", [22]*24)[14] + h.get("temperature_2m_ecmwf_ifs04", [22]*24)[14]) / 3, 1)
        p_data["t22"] = round((h.get("temperature_2m_gfs_seamless", [17]*24)[22] + h.get("temperature_2m_icon_seamless", [17]*24)[22] + h.get("temperature_2m_ecmwf_ifs04", [17]*24)[22]) / 3, 1)
        
        p_data["vento_gfs"] = round(h.get("wind_speed_10m_gfs_seamless", [10]*24)[14], 1)
        p_data["vento_icon"] = round(h.get("wind_speed_10m_icon_seamless", [10]*24)[14], 1)
        p_data["vento_ecmwf"] = round(h.get("wind_speed_10m_ecmwf_ifs04", [10]*24)[14], 1)
        p_data["vento_media"] = round((p_data["vento_gfs"] + p_data["vento_icon"] + p_data["vento_ecmwf"]) / 3, 1)
        p_data["dir_testo"] = gradi_a_punti_cardinali(h.get("wind_direction_10m_ecmwf_ifs04", [0]*24)[14])
        
        for o_idx in range(12, 23):
            if h.get("weather_code_icon_seamless", [0]*24)[o_idx] in [95, 96, 99] or h.get("weather_code_ecmwf_ifs04", [0]*24)[o_idx] in [95, 96, 99]:
                p_data["fulmini"] = True
                break

    if idx < len(res_aqi) and isinstance(res_aqi, list) and "hourly" in res_aqi[idx]:
        p_data["pm10"] = round(res_aqi[idx]["hourly"].get("pm10", [15]*24)[14], 1)

    info_capoluogo = {
        "nome": prov["nome"], "tipo": "capoluogo", "regione": prov["regione"], "lat": prov["lat"], "lon": prov["lon"], "fulmini": p_data["fulmini"],
        "pioggia": {"gfs": p_data["pioggia_gfs"], "icon": p_data["pioggia_icon"], "ecmwf": p_data["pioggia_ecmwf"], "media": p_data["pioggia_media"]},
        "t7": {"media": p_data["t7"]}, "t14": {"media": p_data["t14"]}, "t22": {"media": p_data["t22"]},
        "vento": {"gfs": p_data["vento_gfs"], "icon": p_data["vento_icon"], "ecmwf": p_data["vento_ecmwf"], "media": p_data["vento_media"], "dir": p_data["dir_testo"]},
        "smog": {"valore": p_data["pm10"], "giudizio": "Ottima" if p_data["pm10"] < 20 else "Discreta" if p_data["pm10"] < 35 else "Scadente" if p_data["pm10"] < 50 else "Pessima"}
    }
    
    dati_render_mappa.append(info_capoluogo)
    dati_tabelle_regionali[prov["regione"]][prov["nome"]] = info_capoluogo

# ==========================================
# 3. RECUPERO DATI METEO MARINI
# ==========================================
print("⚓ Elaborazione bollettino mari...")
dati_mari_render = []
mar_lats = [str(m["lat"]) for m in DIZIONARIO_MARI.values()]
mar_lons = [str(m["lon"]) for m in DIZIONARIO_MARI.values()]
try:
    url_marine = f"https://marine-api.open-meteo.com/v1/marine?latitude={','.join(mar_lats)}&longitude={','.join(mar_lons)}&hourly=wave_height,sea_surface_temperature&forecast_days=1&timezone=Europe/Rome"
    res_marine = requests.get(url_marine, timeout=15).json()
except Exception:
    res_marine = {}

for i, (nome_mare, coord) in enumerate(DIZIONARIO_MARI.items()):
    pt_marine = res_marine[i] if isinstance(res_marine, list) else res_marine
    altezza_onda = pt_marine["hourly"]["wave_height"][14] if (isinstance(pt_marine, dict) and "hourly" in pt_marine) else 0.4
    temp_mare = pt_marine["hourly"]["sea_surface_temperature"][14] if (isinstance(pt_marine, dict) and "hourly" in pt_marine) else 18.5
    if altezza_onda < 0.5: icona_mare, stato_testo = "🌊", f"Calmo ({round(altezza_onda,2)}m)"
    elif altezza_onda <= 1.25: icona_mare, stato_testo = "🌊🌊", f"Mosso ({round(altezza_onda,2)}m)"
    else: icona_mare, stato_testo = "🌊🌊🌊", f"Agitato ({round(altezza_onda,2)}m)"
    hex_m = "d73027" if temp_mare >= 24 else "fee090" if temp_mare >= 19 else "e0f3f8" if temp_mare >= 14 else "4575b4"
    dati_mari_render.append({"nome": nome_mare, "lat": coord["lat"], "lon": coord["lon"], "icona": icona_mare, "temp": round(temp_mare, 1), "testo": stato_testo, "colore_classe": hex_m})

# ==========================================
# 4. GENERAZIONE TABELLE HTML REGIONALI
# ==========================================
def tabella_regionale_pioggia(regione_nome):
    html = f"<div class='scheda-meteo s-pioggia'><h3 style='margin:0 0 10px 0; color:#1f77b4; border-bottom:2px solid #1f77b4; padding-bottom:5px; font-size:14px; text-align:center;'>{regione_nome}: Precipitazioni 24h</h3>"
    html += "<table style='width:100%; border-collapse:collapse; text-align:center; font-size:11px; border:1px solid #ddd;'><tr style='background-color:#f8f9fa; font-weight:bold; height:26px;'><td>Provincia</td><td>GFS</td><td>ICON</td><td>ECMWF</td><td style='background-color:#e6f2ff;'>MEDIA</td></tr>"
    for p_nome, d in dati_tabelle_regionali.get(regione_nome, {}).items():
        ico = " ⛈️" if d["fulmini"] else ""
        html += f"<tr style='border-bottom:1px solid #eee; height:26px;'><td><b>{p_nome}{ico}</b></td><td>{d['pioggia']['gfs']}</td><td>{d['pioggia']['icon']}</td><td>{d['pioggia']['ecmwf']}</td><td style='background-color:#e6f2ff; font-weight:bold; color:#1f77b4;'>{d['pioggia']['media']} mm</td></tr>"
    return html + "</table></div>"

def tabella_regionale_temperatura(regione_nome):
    html = f"<div class='scheda-meteo s-temp' style='display:none;'><h3 style='margin:0 0 10px 0; color:#d62728; border-bottom:2px solid #d62728; padding-bottom:5px; font-size:14px; text-align:center;'>{regione_nome}: Temperature Medie</h3>"
    html += "<table style='width:100%; border-collapse:collapse; text-align:center; font-size:11px; border:1px solid #ddd;'><tr style='background-color:#f8f9fa; font-weight:bold; height:26px;'><td>Provincia</td><td style='color:blue;'>07:00</td><td style='color:red;'>14:00</td><td style='color:darkblue;'>22:00</td></tr>"
    for p_nome, d in dati_tabelle_regionali.get(regione_nome, {}).items():
        ico = " ⚡" if d["fulmini"] else ""
        html += f"<tr style='border-bottom:1px solid #eee; height:26px;'><td><b>{p_nome}{ico}</b></td><td style='color:blue;'>{d['t7']['media']} °C</td><td style='color:red; font-weight:bold; background-color:#ffe6e6;'>{d['t14']['media']} °C</td><td style='color:darkblue;'>{d['t22']['media']} °C</td></tr>"
    return html + "</table></div>"

def tabella_regionale_vento(regione_nome):
    html = f"<div class='scheda-meteo s-vento' style='display:none;'><h3 style='margin:0 0 10px 0; color:#ff7f0e; border-bottom:2px solid #ff7f0e; padding-bottom:5px; font-size:14px; text-align:center;'>{regione_nome}: Venti e Raffiche</h3>"
    html += "<table style='width:100%; border-collapse:collapse; text-align:center; font-size:11px; border:1px solid #ddd;'><tr style='background-color:#f8f9fa; font-weight:bold; height:26px;'><td>Provincia</td><td>GFS</td><td>ICON</td><td>ECMWF</td><td style='background-color:#ffe6cc;'>MEDIA</td></tr>"
    for p_nome, d in dati_tabelle_regionali.get(regione_nome, {}).items():
        ico = " ⚡" if d["fulmini"] else ""
        html += f"<tr style='border-bottom:1px solid #eee; height:26px;'><td><b>{p_nome}{ico}</b></td><td>{d['vento']['gfs']}</td><td>{d['vento']['icon']}</td><td>{d['vento']['ecmwf']}</td><td style='background-color:#ffe6cc; font-weight:bold; color:#ff7f0e;'>{d['vento']['media']} km/h ({d['vento']['dir']})</td></tr>"
    return html + "</table></div>"

def tabella_regionale_smog(regione_nome):
    html = f"<div class='scheda-meteo s-smog' style='display:none;'><h3 style='margin:0 0 10px 0; color:#9467bd; border-bottom:2px solid #9467bd; padding-bottom:5px; font-size:14px; text-align:center;'>{regione_nome}: Qualità dell'Aria</h3>"
    html += "<table style='width:100%; border-collapse:collapse; text-align:center; font-size:11px; border:1px solid #ddd;'><tr style='background-color:#f8f9fa; font-weight:bold; height:26px;'><td>Provincia</td><td>PM10</td><td style='background-color:#f3e6ff;'>Stato Aria</td></tr>"
    for p_nome, d in dati_tabelle_regionali.get(regione_nome, {}).items():
        ico = " ⚡" if d["fulmini"] else ""
        html += f"<tr style='border-bottom:1px solid #eee; height:26px;'><td><b>{p_nome}{ico}</b></td><td>{d['smog']['valore']} ug/m3</td><td style='background-color:#f3e6ff; font-weight:bold;'>{d['smog']['giudizio']}</td></tr>"
    return html + "</table></div>"

# ==========================================
# 5. CREAZIONE MAPPA FOLLIUM
# ==========================================
print("🗺️ Disegno della mappa interattiva...")
map_italia = folium.Map(location=[42.0, 12.5], zoom_start=6, tiles="cartodbpositron")

for d in dati_render_mappa:
    raggio_mappa = 45000
    
    cl_p = "001d58" if d["pioggia"]["media"] >= 15 else "225ea8" if d["pioggia"]["media"] >= 5 else "41b6c4" if d["pioggia"]["media"] >= 1 else "a1dab4"
    folium.Circle(location=[d["lat"], d["lon"]], radius=raggio_mappa, color="transparent", weight=0, fill=True, fill_opacity=0.7, className=f"v-filtro v-pioggia sfumatura-{cl_p}").add_to(map_italia)
    
    t_val = d["t14"]["media"]
    cl_t = "d73027" if t_val >= 28 else "f46d43" if t_val >= 22 else "fee08b" if t_val >= 15 else "1a9850"
    folium.Circle(location=[d["lat"], d["lon"]], radius=raggio_mappa, color="transparent", weight=0, fill=True, fill_opacity=0.7, className=f"v-filtro v-temp sfumatura-{cl_t}").add_to(map_italia)
    
    cl_w = "d73027" if d["vento"]["media"] >= 25 else "fee090" if d["vento"]["media"] >= 10 else "e0f3f8"
    folium.Circle(location=[d["lat"], d["lon"]], radius=raggio_mappa, color="transparent", weight=0, fill=True, fill_opacity=0.7, className=f"v-filtro v-vento sfumatura-{cl_w}").add_to(map_italia)
    
    cl_s = "f46d43" if d["smog"]["valore"] >= 40 else "fee08b" if d["smog"]["valore"] >= 20 else "66bd63"
    folium.Circle(location=[d["lat"], d["lon"]], radius=raggio_mappa, color="transparent", weight=0, fill=True, fill_opacity=0.7, className=f"v-filtro v-smog sfumatura-{cl_s}").add_to(map_italia)

blocchi_html_tabelle = ""
for r_nome in REGIONI_COORDINATE.keys():
    id_div_regione = r_nome.replace(" ", "-").replace("'", "-")
    blocchi_html_tabelle += f'<div id="box-regione-{id_div_regione}" class="gruppo-regione-tabella" style="display:none;">{tabella_regionale_pioggia(r_nome)}{tabella_regionale_temperatura(r_nome)}{tabella_regionale_vento(r_nome)}{tabella_regionale_smog(r_nome)}</div>'

for r_nome, coord in REGIONI_COORDINATE.items():
    id_pulito = r_nome.replace(" ", "-").replace("'", "-")
    html_indicatore_nativo = f'<div onclick="mostraRegioneLaterale(\'{id_pulito}\')" title="{r_nome}" style="width: 24px; height: 24px; background-color: white; border: 3px solid #2c3e50; border-radius: 50%; cursor: pointer; box-shadow: 0px 2px 6px rgba(0,0,0,0.3); transform: translate(-12px, -12px); z-index: 99999;"></div>'
    folium.Marker(location=coord, icon=folium.DivIcon(html=html_indicatore_nativo, icon_size=(24, 24))).add_to(map_italia)

for mare in dati_mari_render:
    folium.Circle(location=[mare["lat"], mare["lon"]], radius=110000, color="transparent", weight=0, fill=True, fill_opacity=0.55, className=f"sfumatura-{mare['colore_classe']}").add_to(map_italia)
    popup_html = f"<div style='font-family: Arial, sans-serif; font-size:11px; width:180px;'><h4 style='margin:0 0 5px 0; color:#005580; border-bottom:1px solid #ccc; padding-bottom:3px;'>{mare['nome']}</h4><b>Moto Ondoso:</b> {mare['testo']}<br><b>Temp. Acqua:</b> <b>{mare['temp']} °C</b></div>"
    folium.Marker(location=[mare["lat"], mare["lon"]], icon=folium.DivIcon(html=f"<div style='font-family: Arial, sans-serif; font-size: 11px; text-align: center; font-weight: bold; color: #003366; text-shadow: 1px 1px 2px white;'><span style='font-size:16px;'>{mare['icona']}</span><br>🌡️ {mare['temp']}°C</div>"), popup=folium.Popup(popup_html, max_width=220)).add_to(map_italia)

# ==========================================
# 6. STRUTTURA INTERFACCIA E JAVASCRIPT
# ==========================================
interfaccia_custom_html = """
<style>
    .v-filtro { opacity: 0 !important; pointer-events: none !important; transition: opacity 0.2s ease; }
    .v-attivo { opacity: 0.7 !important; pointer-events: auto !important; }
    .sfumatura-a1dab4 { fill: url(#grad-a1dab4) !important; } .sfumatura-41b6c4 { fill: url(#grad-41b6c4) !important; }
    .sfumatura-225ea8 { fill: url(#grad-225ea8) !important; } .sfumatura-001d58 { fill: url(#grad-001d58) !important; }
    .sfumatura-1a9850 { fill: url(#grad-1a9850) !important; } .sfumatura-fee08b { fill: url(#grad-fee08b) !important; }
    .sfumatura-f46d43 { fill: url(#grad-f46d43) !important; } .sfumatura-d73027 { fill: url(#grad-d73027) !important; }
    .sfumatura-e0f3f8 { fill: url(#grad-e0f3f8) !important; } .sfumatura-fee090 { fill: url(#grad-fee090) !important; }
    .sfumatura-66bd63 { fill: url(#grad-66bd63) !important; } .sfumatura-4575b4 { fill: url(#grad-4575b4) !important; }
    
    #sidebar-tabelle-mcspark { position: fixed !important; bottom: 20px !important; left: 20px !important; width: 320px !important; height: 300px !important; background: rgba(255, 255, 255, 0.95) !important; border: 2px solid #2c3e50 !important; border-radius: 8px !important; z-index: 9999 !important; font-family: Arial, sans-serif !important; box-shadow: 4px 4px 15px rgba(0,0,0,0.2) !important; padding: 12px !important; overflow-y: auto !important; display: block !important; box-sizing: border-box !important; }
    .messaggio-benvenuto-sidebar { font-size: 11px !important; color: #555 !important; text-align: center !important; margin-top: 15px !important; line-height: 1.4 !important; }
    #pannello-meteo-pulsanti { position: fixed; top: 20px; right: 20px; background: white; padding: 12px; border: 2px solid #2c3e50; border-radius: 8px; z-index: 9999; font-family: Arial, sans-serif; box-shadow: 4px 4px 15px rgba(0,0,0,0.2); width: 320px; box-sizing: border-box; }
    #pannello-meteo-pulsanti h4 { margin: 0 0 10px 0; font-size: 13px; color: #2c3e50; border-bottom: 2px solid #2c3e50; padding-bottom: 5px; text-align: center; font-weight: bold; }
    .opzione-radio { display: block; margin-bottom: 8px; cursor: pointer; font-size: 12px; font-weight: bold; color: #333; }
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

<div id="sidebar-tabelle-mcspark">
    <div id="contenitore-vuoto-sidebar">
        <h2 style='text-align:center; color:#2c3e50; font-size:15px; margin-top:5px;'>📊 Report Dettagliato</h2>
        <div class="messaggio-benvenuto-sidebar"><span style="font-size: 24px;">🗺️</span><br><br><b>Clicca direttamente sul cerchietto vicino alla regione</b> per vederne istantaneamente i dati provinciali completi qui a sinistra.</div>
    </div>
    <div id="contenitore-tabelle-attive-sidebar" style="display:none;">""" + blocchi_html_tabelle + """</div>
</div>

<div id="pannello-meteo-pulsanti">
    <h4>📊 SELEZIONA VISUALIZZAZIONE</h4>
    <label class="opzione-radio"><input type="radio" name="filtro-global" value="pioggia" checked>🌧️ Pioggia Prevista 24h</label>
    <label class="opzione-radio"><input type="radio" name="filtro-global" value="temp">🌡️ Temperature (07-14-22)</label>
    <label class="opzione-radio"><input type="radio" name="filtro-global" value="vento">💨 Vento e Raffiche</label>
    <label class="opzione-radio"><input type="radio" name="filtro-global" value="smog">😷 Qualità dell'Aria (Smog)</label>
</div>

<script>
var filtroAttuale = 'pioggia'; var ultimaRegioneAperta = null;
function mostraRegioneLaterale(idRegione) {
    ultimaRegioneAperta = idRegione; document.getElementById('contenitore-vuoto-sidebar').style.display = 'none'; document.getElementById('contenitore-tabelle-attive-sidebar').style.display = 'block';
    var tuttiIBox = document.getElementsByClassName('gruppo-regione-tabella'); for (var i = 0; i < tuttiIBox.length; i++) { tuttiIBox[i].style.display = 'none'; }
    var boxAttivo = document.getElementById('box-regione-' + idRegione);
    if(boxAttivo) { boxAttivo.style.display = 'block'; var tutteLeSchede = boxAttivo.getElementsByClassName('scheda-meteo'); for (var j = 0; j < tutteLeSchede.length; j++) { tutteLeSchede[j].style.display = 'none'; } var schedeDaMostrare = boxAttivo.getElementsByClassName('s-' + filtroAttuale); for (var k = 0; k < schedeDaMostrare.length; k++) { schedeDaMostrare[k].style.display = 'block'; } }
}
function aggiornaMappaEInvolucri(valoreFiltro) {
    filtroAttuale = valoreFiltro; var tuttiIFiltri = document.getElementsByClassName('v-filtro'); for (var i = 0; i < tuttiIFiltri.length; i++) { tuttiIFiltri[i].classList.remove('v-attivo'); }
    var filtriDaAttivare = document.getElementsByClassName('v-' + valoreFiltro); for (var j = 0; j < filtriDaAttivare.length; j++) { filtriDaAttivare[j].classList.add('v-attivo'); }
    if(ultimaRegioneAperta) { mostraRegioneLaterale(ultimaRegioneAperta); }
}
var radioButtons = document.getElementsByName('filtro-global'); for (var i = 0; i < radioButtons.length; i++) { radioButtons[i].addEventListener('change', function(e) { aggiornaMappaEInvolucri(e.target.value); }); }
setTimeout(function() { aggiornaMappaEInvolucri('pioggia'); }, 300);
</script>
"""
map_italia.get_root().html.add_child(folium.Element(interfaccia_custom_html))

branding_html = (
    f'<div style="position: fixed; bottom: 35px; right: 20px; width: 60px; height: auto; z-index: 9999; border: 1px solid #2c3e50; border-radius: 4px; overflow: hidden; box-shadow: 0 2px 5px rgba(0,0,0,0.2);"><img src="{FILE_LOGO_LOCAL}" style="width:100%; display:block;"></div>'
    f'<div style="position: fixed; bottom: 10px; left: 50%; transform: translateX(-50%); background-color: rgba(255,255,255,0.9); padding: 4px 10px; border-radius: 4px; z-index: 9999; font-family: Arial, sans-serif; font-size: 10px; color: #333; border: 1px solid #ccc; box-shadow: 0px 2px 5px rgba(0,0,0,0.1); text-align: center; white-space: nowrap;"><b>{COPYRIGHT}</b> | <span style="color:#666;">{FONTE_DATI}</span> | <span style="color:#005580; font-weight:bold;">{STRINGA_AGGIORNAMENTO}</span></div>'
)
map_italia.get_root().html.add_child(folium.Element(branding_html))

# FORZATURA STRUTTURA SMARTPHONE RESPONSIVE (CON GRAFFA CORRECT)
stile_smartphone = """
<style>
@media (max-width: 600px) {
    #sidebar-tabelle-mcspark { width: 100% !important; height: 230px !important; left: 0 !important; bottom: 0 !important; border-radius: 12px 12px 0 0 !important; border-width: 2px 0 0 0 !important; z-index: 99999 !important; }
    #pannello-meteo-pulsanti { top: 10px !important; right: 10px !important; width: 160px !important; padding: 5px !important; z-index: 99999 !important; }
    .opzione-radio { display: block; margin-bottom: 8px; cursor: pointer; font-size: 12px; font-weight: bold; color: #333; }
}
</style>
"""
map_italia.get_root().html.add_child(folium.Element(stile_smartphone))

map_italia.fit_bounds([[36.0, 6.0], [47.5, 18.5]])
map_italia.save("index.html")

print(f"✅ Interfaccia completata in blocco con successo: {STRINGA_AGGIORNAMENTO}")
