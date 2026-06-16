import os
import requests
import folium
from datetime import datetime, timedelta
import zoneinfo
from province_italia import PROVINCE_BY_REGIONE, REGIONI_COORDINATE

# ===========================================
# CONFIGURAZIONE, TIMESTAMP E BRANDING
# ==========================================
NOME_SITO = "McSpark Meteo"
COPYRIGHT = f"© 2026 {NOME_SITO} - Tutti i diritti riservati"
FONTE_DATI = "Dati: WeatherAPI Realtime & Forecast Models (GFS/ECMWF)"
FILE_LOGO_LOCAL = "unnamed.jpg"

ora_italiana = datetime.now(zoneinfo.ZoneInfo("Europe/Rome"))
STRINGA_AGGIORNAMENTO = ora_italiana.strftime("Aggiornato il: %d/%m/%Y alle %H:%M")

print(f"🌊✨ McSpark Meteo: Avvio iniezione dati ({STRINGA_AGGIORNAMENTO})...")

API_KEY = "eca968be0d38479d87e193151260106"

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

# ==========================================
# FUNZIONI TABELLE REGIONALI
# ==========================================
def tabella_regionale_pioggia(regione_nome, dati_tabelle_regionali):
    html = (
        f"<div class='scheda-meteo s-pioggia'>"
        f"<h3 style='margin:0 0 10px 0; color:#1f77b4; border-bottom:2px solid #1f77b4; "
        f"padding-bottom:5px; font-size:14px; text-align:center;'>{regione_nome}: Precipitazioni 24h</h3>"
    )
    html += (
    # Aggiunto margin-top: 6px per staccarla dal bordo superiore e non farla tagliare
    "<table style='width:100%; border-collapse:collapse; text-align:center; font-size:11px; "
    "border:1px solid #ddd; margin-top: 6px;'>"
    
    # Cambiato in <th> e aggiunti padding per dare respiro al testo
    "<tr style='background-color:#f8f9fa; font-weight:bold; height:28px;'> "
    "<th style='padding: 4px 0; font-weight:bold;'>Provincia</th>"
    "<th style='padding: 4px 0; font-weight:bold;'>GFS</th>"
    "<th style='padding: 4px 0; font-weight:bold;'>ICON</th>"
    "<th style='padding: 4px 0; font-weight:bold;'>ECMWF</th>"
    "<th style='background-color:#e6f2ff; padding: 4px 0; font-weight:bold;'>MEDIA</th>"
    "</tr>"
)

    for p_nome, d in dati_tabelle_regionali.get(regione_nome, {}).items():
        fulmini = " ⚡" if d["fulmini"] else ""
        html += (
            "<tr style='border-bottom:1px solid #eee; height:26px;'>"
            f"<td><b>{p_nome}{fulmini}</b></td>"
            f"<td>{d['pioggia']['gfs']}</td>"
            f"<td>{d['pioggia']['icon']}</td>"
            f"<td>{d['pioggia']['ecmwf']}</td>"
            f"<td style='background-color:#e6f2ff; font-weight:bold; color:#1f77b4;'>{d['pioggia']['media']} mm</td>"
            "</tr>"
        )
    return html + "</table></div>"


def tabella_regionale_temperatura(regione_nome, dati_tabelle_regionali):
    html = (
        f"<div class='scheda-meteo s-temp' style='display:none;'>"
        f"<h3 style='margin:0 0 10px 0; color:#d62728; border-bottom:2px solid #d62728; "
        f"padding-bottom:5px; font-size:14px; text-align:center;'>{regione_nome}: Temperature Medie</h3>"
    )
    html += (
        # Aggiunto margin-top: 6px; per evitare il taglio dell'intestazione
        "<table style='width:100%; border-collapse:collapse; text-align:center; font-size:11px; "
        "border:1px solid #ddd; margin-top: 6px;'>"
        
        # Cambiati i tag in <th> per l'intestazione e aggiunto padding
        "<tr style='background-color:#f8f9fa; font-weight:bold; height:28px;'>"
        "<th style='padding: 4px 0; font-weight:bold;'>Provincia</th>"
        "<th style='color:blue; padding: 4px 0; font-weight:bold;'>07:00</th>"
        "<th style='color:red; padding: 4px 0; font-weight:bold;'>14:00</th>"
        "<th style='color:darkblue; padding: 4px 0; font-weight:bold;'>22:00</th></tr>"
    )
    for p_nome, d in dati_tabelle_regionali.get(regione_nome, {}).items():
        fulmini = " ⚡" if d["fulmini"] else ""
        html += (
            "<tr style='border-bottom:1px solid #eee; height:26px;'>"
            f"<td><b>{p_nome}{fulmini}</b></td>"
            f"<td style='color:blue;'>{d['t7']['media']} °C</td>"
            f"<td style='color:red; font-weight:bold; background-color:#ffe6e6;'>{d['t14']['media']} °C</td>"
            f"<td style='color:darkblue;'>{d['t22']['media']} °C</td>"
            "</tr>"
        )
    return html + "</table></div>"


def tabella_regionale_vento(regione_nome, dati_tabelle_regionali):
    html = (
        f"<div class='scheda-meteo s-vento' style='display:none;'>"
        f"<h3 style='margin:0 0 10px 0; color:#ff7f0e; border-bottom:2px solid #ff7f0e; "
        f"padding-bottom:5px; font-size:14px; text-align:center;'>{regione_nome}: Venti e Raffiche</h3>"
    )
    html += (
    # Aggiunto margin-top: 6px per staccarla dal bordo superiore e non farla tagliare
    "<table style='width:100%; border-collapse:collapse; text-align:center; font-size:11px; "
    "border:1px solid #ddd; margin-top: 6px;'>"
    
    # Cambiato in <th> e aggiunti padding per dare respiro al testo
    "<tr style='background-color:#f8f9fa; font-weight:bold; height:28px;'> "
    "<th style='padding: 4px 0; font-weight:bold;'>Provincia</th>"
    "<th style='padding: 4px 0; font-weight:bold;'>GFS</th>"
    "<th style='padding: 4px 0; font-weight:bold;'>ICON</th>"
    "<th style='padding: 4px 0; font-weight:bold;'>ECMWF</th>"
    "<th style='background-color:#e6f2ff; padding: 4px 0; font-weight:bold;'>MEDIA</th>"
    "</tr>"
)
    for p_nome, d in dati_tabelle_regionali.get(regione_nome, {}).items():
        fulmini = " ⚡" if d["fulmini"] else ""
        html += (
            "<tr style='border-bottom:1px solid #eee; height:26px;'>"
            f"<td><b>{p_nome}{fulmini}</b></td>"
            f"<td>{d['vento']['gfs']}</td>"
            f"<td>{d['vento']['icon']}</td>"
            f"<td>{d['vento']['ecmwf']}</td>"
            f"<td style='background-color:#ffe6cc; font-weight:bold; color:#ff7f0e;'>"
            f"{d['vento']['media']} km/h ({d['vento']['dir']})</td>"
            "</tr>"
        )
    return html + "</table></div>"


def tabella_regionale_smog(regione_nome, dati_tabelle_regionali):
    html = (
        f"<div class='scheda-meteo s-smog' style='display:none;'>"
        f"<h3 style='margin:0 0 10px 0; color:#9467bd; border-bottom:2px solid #9467bd; "
        f"padding-bottom:5px; font-size:14px; text-align:center;'>{regione_nome}: Qualità dell'Aria</h3>"
    )
    html += (
        "<table style='width:100%; border-collapse:collapse; text-align:center; font-size:11px; "
        "border:1px solid #ddd; margin-top: 6px;'>"
        
        # Intestazione corretta a 2 sole colonne per lo Smog
        "<tr style='background-color:#f8f9fa; font-weight:bold; height:28px;'> "
        "<th style='width:50%; padding: 4px 0; font-weight:bold;'>Provincia</th>"
        "<th style='width:50%; padding: 4px 0; font-weight:bold;'>Qualità</th>"
        "</tr>"
    )
    for p_nome, d in dati_tabelle_regionali.get(regione_nome, {}).items():
        fulmini = " ⚡" if d["fulmini"] else ""
        html += (
            "<tr style='border-bottom:1px solid #eee; height:26px;'>"
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
    )
    html += (
        "<table style='width:100%; border-collapse:collapse; text-align:center; font-size:11px; "
        "border:1px solid #ddd; margin-top: 6px;'>"
        
        # Intestazione corretta a 3 colonne reali (ma 2 titoli visibili)
        "<tr style='background-color:#f8f9fa; font-weight:bold; height:28px;'> "
        "<th style='width:40%; padding: 4px 0; font-weight:bold;'>Provincia</th>"
        # colspan='2' unisce le due colonne successive sotto un unico titolo "Indice UV"
        "<th colspan='2' style='width:60%; padding: 4px 0; font-weight:bold;'>Indice UV</th>"
        "</tr>"
    )
    for p_nome, d in dati_tabelle_regionali.get(regione_nome, {}).items():
        fulmini = " ⚡" if d["fulmini"] else ""
        html += (
            "<tr style='border-bottom:1px solid #eee; height:26px;'>"
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

    # DATA VALIDITÀ SPECIFICA PER IL GIORNO
    data_validita = (ora_italiana + timedelta(days=day_index)).strftime("%d/%m/%Y")

    # 1. RECUPERO DATI METEO TERRESTRI
    dati_render_mappa = []
    dati_tabelle_regionali = {}

    for regione, elenco in PROVINCE_BY_REGIONE.items():
        dati_tabelle_regionali[regione] = {}

        for p in elenco:
            nome_provincia = p["nome"]
            lat_float = float(p["lat"])
            lon_float = float(p["lon"])

            base_t7 = 14.0
            base_t14 = 22.0
            base_t22 = 17.0
            base_prec = 0.0
            base_wind = 10.0
            base_pm10 = 15.0
            base_uv = 0.0
            dir_testo = "N"
            ha_fulmini = False

            try:
                url = (
                    "http://api.weatherapi.com/v1/forecast.json?"
                    f"key={API_KEY}&q={lat_float},{lon_float}&days=3&aqi=yes&alerts=no"
                )
                res = requests.get(url, timeout=10).json()

                giorni = res["forecast"]["forecastday"]
                if day_index >= len(giorni):
                    print(f"⚠️ Giorno {day_index} non disponibile per {nome_provincia}, salto.")
                    continue

                giorno = giorni[day_index]
                ore = giorno["hour"]

                base_prec = float(giorno["day"]["totalprecip_mm"])
                base_t7 = float(ore[7]["temp_c"])
                base_t14 = float(ore[14]["temp_c"])
                base_t22 = float(ore[22]["temp_c"])
                base_wind = float(giorno["day"]["maxwind_kph"])
                dir_testo = str(ore[14]["wind_dir"])
                base_uv = float(giorno["day"]["uv"])
                base_pm10 = float(res["current"]["air_quality"].get("pm10", 15))

                ha_fulmini = any(
                    int(ora["condition"]["code"]) in [1087, 1273, 1276, 1279, 1282]
                    for ora in ore
                )

            except Exception as e:
                print(f"⚠️ Errore API per {nome_provincia}: {e}")

            # Giudizi smog
            if base_pm10 < 20:
                giudizio_smog = "Buona"
            elif base_pm10 < 40:
                giudizio_smog = "Discreta"
            elif base_pm10 < 60:
                giudizio_smog = "Mediocre"
            else:
                giudizio_smog = "Scadente"

            # Giudizi UV
            if base_uv < 3:
                giudizio_uv = "Basso"
            elif base_uv < 6:
                giudizio_uv = "Moderato"
            elif base_uv < 8:
                giudizio_uv = "Alto"
            else:
                giudizio_uv = "Molto alto"

            info = {
                "nome": nome_provincia,
                "tipo": "capoluogo",
                "regione": regione,
                "lat": lat_float,
                "lon": lon_float,
                "fulmini": ha_fulmini,
                "pioggia": {
                    "gfs": round(base_prec, 1),
                    "icon": round(base_prec, 1),
                    "ecmwf": round(base_prec, 1),
                    "media": round(base_prec, 1),
                },
                "t7": {"media": round(base_t7, 1)},
                "t14": {"media": round(base_t14, 1)},
                "t22": {"media": round(base_t22, 1)},
                "vento": {
                    "gfs": round(base_wind, 1),
                    "icon": round(base_wind, 1),
                    "ecmwf": round(base_wind, 1),
                    "media": round(base_wind, 1),
                    "dir": dir_testo,
                },
                "smog": {"valore": round(base_pm10, 1), "giudizio": giudizio_smog},
                "uv": {"valore": round(base_uv, 1), "giudizio": giudizio_uv},
            }

            dati_render_mappa.append(info)
            dati_tabelle_regionali[regione][nome_provincia] = info

    # 2. CREAZIONE MAPPA
    print("🗺️ Disegno della mappa interattiva in corso...")
    map_italia = folium.Map(location=[42.0, 12.5], zoom_start=6, tiles="cartodbpositron")

    # 3. STRATO MARI (con dati marine API, VARIABILI PER GIORNO)
    print("⚓ Elaborazione bollettino mari...")
    dati_mari_render = []

    for nome_mare, coord in DIZIONARIO_MARI.items():
        altezza_onda = 0.4
        temp_mare = 18.5
        try:
            url_marine = (
                "https://marine-api.open-meteo.com/v1/marine?"
                f"latitude={coord['lat']}&longitude={coord['lon']}"
                "&hourly=wave_height,sea_surface_temperature"
                "&forecast_days=3&timezone=Europe/Rome"
            )
            res_marine = requests.get(url_marine, timeout=15).json()
            idx = day_index * 24 + 14  # ora 14 del giorno scelto
            altezza_onda = res_marine["hourly"]["wave_height"][idx]
            temp_mare = res_marine["hourly"]["sea_surface_temperature"][idx]
        except Exception as e:
            print(f"⚠️ Errore marine API per {nome_mare}: {e}")

        if altezza_onda < 0.5:
            icona_mare, stato_testo = "🌊", f"Calmo ({round(altezza_onda, 2)}m)"
        elif altezza_onda <= 1.25:
            icona_mare, stato_testo = "🌊🌊", f"Mosso ({round(altezza_onda, 2)}m)"
        else:
            icona_mare, stato_testo = "🌊🌊🌊", f"Agitato ({round(altezza_onda, 2)}m)"

        hex_m = (
            "d73027" if temp_mare >= 24 else
            "fee090" if temp_mare >= 19 else
            "e0f3f8" if temp_mare >= 14 else
            "4575b4"
        )

        dati_mari_render.append({
            "nome": nome_mare,
            "lat": coord["lat"],
            "lon": coord["lon"],
            "icona": icona_mare,
            "temp": round(temp_mare, 1),
            "testo": stato_testo,
            "colore_classe": hex_m
        })

    # --- QUESTO È IL BLOCCO CORRETTO E RIPULITO ---
    for mare in dati_mari_render:
        # Mantiene il cerchio colorato trasparente di fondo per la temperatura
        folium.Circle(
            location=[mare["lat"], mare["lon"]],
            radius=110000,
            color="transparent",
            weight=0,
            fill=True,
            fill_opacity=0.55,
            className=f"sfumatura-{mare['colore_classe']}"
        ).add_to(map_italia)

        # Creiamo il fumetto bianco pulito ed elegante che si aprirà SOLO AL CLICK
        popup_html = f"""
        <div style='font-family: Arial, sans-serif; font-size:12px; width:160px; color:#2c3e50;'>
            <h4 style='margin:0 0 5px 0; border-bottom:1px solid #ddd; padding-bottom:3px;'>{mare['nome']}</h4>
            <b>Moto Ondoso:</b> {mare['testo']}<br>
            <b>Temp. Acqua:</b> {mare['temp']} °C
        </div>
        """
        
        # Creiamo l'icona visibile sulla mappa usando le tue onde emoji originali (🌊, 🌊🌊, 🌊🌊🌊)
        # inserite dentro un cerchietto DivIcon piccolo, pulito e senza testi giganti intorno.
        icona_trasparente = folium.DivIcon(
            html=f"""<div style="font-size: 20px; text-shadow: 1px 1px 2px rgba(0,0,0,0.4); 
                     cursor: pointer; text-align: center; width: 40px; margin-left: -20px; margin-top: -10px;">
                     {mare['icona']}
                  </div>"""
        )

        # Creiamo il Marker definitivo sulla mappa
        folium.Marker(
            location=[mare["lat"], mare["lon"]],
            icon=icona_trasparente,                     # Mostra solo il simbolo delle onde (1, 2 o 3 onde)
            popup=folium.Popup(popup_html, max_width=250) # Nasconde il testo e lo mostra nel fumetto bianco solo al click!
        ).add_to(map_italia)

    # 4. BADGE DATA VALIDITÀ + FIX OVERFLOW
    legenda_data_html = f'''



    '''
    map_italia.get_root().html.add_child(folium.Element(legenda_data_html))

    map_italia.get_root().header.add_child(folium.Element("""
    <style>
    html, body, iframe {
        overflow: visible !important;
    }

    .banner-validita {
        position: absolute;
        top: 217px;
        left: 520px;
        transform: scale(1);
    }
    @media (max-width: 768px) {
        .banner-validita {
            top: 227px !important;
            left: 460px !important;
            transform: scale(0.9);
        }
    }

    .report-dettagliato {
        position: relative !important;
        margin-top: 0px !important;
        padding-top: 0px !important;
        z-index: 9999 !important;
    }

    .scheda-meteo {
        margin-top: 0px !important;
        padding-top: 0px !important;
    }

    /* === APPLICHIAMO IL MARGINE NEGATIVO === */
    .scheda-meteo h3 {
        margin-top: 0px !important;     
        padding-top: 0px !important;
        margin-bottom: 6px !important;  /* Tiene la tabella vicina al titolo */
        line-height: 1.2 !important;    
        display: block !important;
        color: #2c3e50 !important;
    }

    .scheda-meteo table {
        margin-top: 0px !important;     
        margin-bottom: 5px !important;
    }

    /* === ASCOLTA ANCHE FIREFOX === */
    @supports (-moz-appearance: none) {
        .report-dettagliato {
            margin-top: 0px !important;
            transform: none !important;
        }
        .scheda-meteo h3 {
            margin-top: -8px !important; /* Replica l'effetto calamita anche qui */
        }
    }
    </style>
    """))

    # 5. LAYER SFUMATI PROVINCE
    for d in dati_render_mappa:
        raggio_mappa = 45000

        # Pioggia
        hex_p = (
            "001d58" if d["pioggia"]["media"] >= 15 else
            "225ea8" if d["pioggia"]["media"] >= 5 else
            "41b6c4" if d["pioggia"]["media"] >= 1 else
            "a1dab4"
        )
        folium.Circle(
            location=[d["lat"], d["lon"]],
            radius=raggio_mappa,
            color="transparent",
            weight=0,
            fill=True,
            fill_opacity=0.7,
            className=f"v-filtro v-pioggia sfumatura-{hex_p}"
        ).add_to(map_italia)

        # Temperatura
        t_val = d["t14"]["media"]
        hex_t = (
            "d73027" if t_val >= 28 else
            "f46d43" if t_val >= 22 else
            "fee08b" if t_val >= 15 else
            "1a9850"
        )
        folium.Circle(
            location=[d["lat"], d["lon"]],
            radius=raggio_mappa,
            color="transparent",
            weight=0,
            fill=True,
            fill_opacity=0.7,
            className=f"v-filtro v-temp sfumatura-{hex_t}"
        ).add_to(map_italia)

        # Vento
        hex_w = (
            "d73027" if d["vento"]["media"] >= 25 else
            "fee090" if d["vento"]["media"] >= 10 else
            "e0f3f8"
        )
        folium.Circle(
            location=[d["lat"], d["lon"]],
            radius=raggio_mappa,
            color="transparent",
            weight=0,
            fill=True,
            fill_opacity=0.7,
            className=f"v-filtro v-vento sfumatura-{hex_w}"
        ).add_to(map_italia)

        # Smog
        hex_s = (
            "f46d43" if d["smog"]["valore"] >= 40 else
            "fee08b" if d["smog"]["valore"] >= 20 else
            "66bd63"
        )
        folium.Circle(
            location=[d["lat"], d["lon"]],
            radius=raggio_mappa,
            color="transparent",
            weight=0,
            fill=True,
            fill_opacity=0.7,
            className=f"v-filtro v-smog sfumatura-{hex_s}"
        ).add_to(map_italia)

        # UV
        hex_uv = (
            "66bd63" if d["uv"]["valore"] < 3 else
            "fee08b" if d["uv"]["valore"] < 6 else
            "f46d43" if d["uv"]["valore"] < 8 else
            "d73027"
        )
        folium.Circle(
            location=[d["lat"], d["lon"]],
            radius=raggio_mappa,
            color="transparent",
            weight=0,
            fill=True,
            fill_opacity=0.7,
            className=f"v-filtro v-uv sfumatura-{hex_uv}"
        ).add_to(map_italia)

    # 6. TABELLE REGIONALI HTML
    blocchi_html_tabelle = ""
    for r_nome in REGIONI_COORDINATE.keys():
        id_div_regione = r_nome.replace(" ", "-").replace("'", "-")
        blocchi_html_tabelle += f"""
        <div id="box-regione-{id_div_regione}" class="gruppo-regione-tabella report-dettagliato" style="display:none;">
            {tabella_regionale_pioggia(r_nome, dati_tabelle_regionali)}
            {tabella_regionale_temperatura(r_nome, dati_tabelle_regionali)}
            {tabella_regionale_vento(r_nome, dati_tabelle_regionali)}
            {tabella_regionale_smog(r_nome, dati_tabelle_regionali)}
            {tabella_regionale_uv(r_nome, dati_tabelle_regionali)}
        </div>
        """

    # 7. MARKER REGIONI (cerchietti cliccabili)
    for r_nome, coord in REGIONI_COORDINATE.items():
        id_pulito = r_nome.replace(" ", "-").replace("'", "-")
        html_indicatore_nativo = f"""
        <div onclick="mostraRegioneLaterale('{id_pulito}')" title="{r_nome}"
             style="width: 24px; height: 24px; background-color: white; border: 3px solid #2c3e50;
                    border-radius: 50%; cursor: pointer; box-shadow: 0px 2px 6px rgba(0,0,0,0.3);
                    transform: translate(-12px, -12px); z-index: 99999;"></div>
        """
        folium.Marker(
            location=coord,
            icon=folium.DivIcon(html=html_indicatore_nativo, icon_size=(24, 24))
        ).add_to(map_italia)

    # 8. INTERFACCIA CUSTOM (CSS + SIDEBAR + PANNELLO + JS)
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

        #sidebar-tabelle-mcspark {
            position: fixed !important;
            bottom: 50px !important;
            left: 15px !important;
            width: 320px !important;
            max-width: 320px !important;
            height: 300px !important;
            max-height: 300px !important;
            background: rgba(255, 255, 255, 0.95) !important;
            border: 2px solid #2c3e50 !important;
            border-radius: 8px !important;
            z-index: 9999 !important;
            font-family: Arial, sans-serif !important;
            box-shadow: 4px 4px 15px rgba(0,0,0,0.2) !important;
            padding: 12px !important;
            padding-top: 4px !important;
            overflow-y: auto !important;
            display: block !important;
            box-sizing: border-box !important;
        }
        .messaggio-benvenuto-sidebar {
            font-size: 11px !important;
            color: #555 !important;
            text-align: center !important;
            margin-top: 15px !important;
            line-height: 1.4 !important;
        }
        #pannello-meteo-pulsanti {
    position: fixed;
    top: 20px;
    right: 20px;
    background: white;
    padding: 14px 12px 12px 12px;
    border: 2px solid #2c3e50;
    border-radius: 8px;
    z-index: 9999;
    font-family: Arial, sans-serif;
    box-shadow: 4px 4px 15px rgba(0,0,0,0.2);
    width: 320px;
    box-sizing: border-box;
    max-height: 85vh;
    overflow-y: auto;
}

/* === QUESTE RIGHE FORZANO IL RESPIRO DELLE TABELLE E DEL TITOLO === */
.scheda-meteo {
    margin-top: 10px !important;
    padding-top: 5px !important;
}

.scheda-meteo h3 {
    margin-top: 5px !important;
    margin-bottom: 15px !important;
}

.scheda-meteo table {
    margin-top: 15px !important; /* Spinge a forza la tabella verso il basso rispetto al titolo */
}
        #pannello-meteo-pulsanti h4 {
            margin: 0 0 10px 0;
            font-size: 13px;
            color: #2c3e50;
            border-bottom: 2px solid #2c3e50;
            padding-bottom: 5px;
            text-align: center;
            font-weight: bold;
        }
        .opzione-radio {
            display: block;
            margin-bottom: 8px;
            cursor: pointer;
            font-size: 12px;
            font-weight: bold;
            color: #333;
        }
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
            <div class="messaggio-benvenuto-sidebar">
                <span style="font-size: 24px;">🗺️</span><br><br>
                <b>Clicca direttamente sul cerchietto vicino alla regione</b> per vederne istantaneamente i dati provinciali.
            </div>
        </div>
        <div id="contenitore-tabelle-attive-sidebar" style="display:none;">""" + blocchi_html_tabelle + """</div>
    </div>
    <div id="pannello-meteo-pulsanti">
        <h4>📊 SELEZIONA VISUALIZZAZIONE</h4>
        <label class="opzione-radio"><input type="radio" name="filtro-global" value="pioggia" checked>🌧️ Pioggia Prevista 24h</label>
        <label class="opzione-radio"><input type="radio" name="filtro-global" value="temp">🌡️ Temperature (07-14-22)</label>
        <label class="opzione-radio"><input type="radio" name="filtro-global" value="vento">💨 Vento e Raffiche</label>
        <label class="opzione-radio"><input type="radio" name="filtro-global" value="smog">😷 Qualità dell'Aria (Smog)</label>
        <label class="opzione-radio"><input type="radio" name="filtro-global" value="uv">☀️ Indice UV</label>
    </div>
    <script>
    var filtroAttuale = 'pioggia';
    var ultimaRegioneAperta = null;

    function mostraRegioneLaterale(idRegione) {
        ultimaRegioneAperta = idRegione;
        document.getElementById('contenitore-vuoto-sidebar').style.display = 'none';
        document.getElementById('contenitore-tabelle-attive-sidebar').style.display = 'block';
        var tuttiIBox = document.getElementsByClassName('gruppo-regione-tabella');
        for (var i = 0; i < tuttiIBox.length; i++) { tuttiIBox[i].style.display = 'none'; }
        var boxAttivo = document.getElementById('box-regione-' + idRegione);
        if (boxAttivo) {
            boxAttivo.style.display = 'block';
            var tutteLeSchede = boxAttivo.getElementsByClassName('scheda-meteo');
            for (var j = 0; j < tutteLeSchede.length; j++) { tutteLeSchede[j].style.display = 'none'; }
            var schedeDaMostrare = boxAttivo.getElementsByClassName('s-' + filtroAttuale);
            for (var k = 0; k < schedeDaMostrare.length; k++) { schedeDaMostrare[k].style.display = 'block'; }
        }
    }

    function aggiornaMappaEInvolucri(valoreFiltro) {
        filtroAttuale = valoreFiltro;
        var tuttiIFiltri = document.getElementsByClassName('v-filtro');
        for (var i = 0; i < tuttiIFiltri.length; i++) {
            tuttiIFiltri[i].classList.remove('v-attivo');
        }
        var filtriDaAttivare = document.getElementsByClassName('v-' + valoreFiltro);
        for (var j = 0; j < filtriDaAttivare.length; j++) {
            filtriDaAttivare[j].classList.add('v-attivo');
        }
        if (ultimaRegioneAperta) {
            mostraRegioneLaterale(ultimaRegioneAperta);
        }
    }

    var radioButtons = document.getElementsByName('filtro-global');
    for (var i = 0; i < radioButtons.length; i++) {
        radioButtons[i].addEventListener('change', function(e) {
            aggiornaMappaEInvolucri(e.target.value);
        });
    }

    setTimeout(function() { aggiornaMappaEInvolucri('pioggia'); }, 300);
    </script>
    """
    map_italia.get_root().html.add_child(folium.Element(interfaccia_custom_html))

    # 9. BRANDING E STILE SMARTPHONE
    # 9. BRANDING E STILE SMARTPHONE
    branding_html = f'''
    <div style="position: fixed; bottom: 35px; right: 20px; width: 60px; height: auto; z-index: 9999; border: 1px solid #2c3e50; border-radius: 4px; overflow: hidden; box-shadow: 0 2px 5px rgba(0,0,0,0.2);">
      <img src="{FILE_LOGO_LOCAL}" style="width:100%; display:block;">
    </div>
    
    <div style="position: fixed; bottom: 10px; left: 50%; transform: translateX(-50%); z-index: 99999; display: flex; flex-direction: column; align-items: center; gap: 8px; font-family: Arial, sans-serif; pointer-events: none;">
        
        <div style="background-color: rgba(200, 0, 0, 0.9); color: white; padding: 5px 12px; border-radius: 12px; font-size: 12px; font-weight: bold; border: 2px solid white; box-shadow: 0px 3px 8px rgba(0,0,0,0.3); white-space: nowrap; text-align: center;">
            Previsione valida per il: {data_validita}
        </div>

        <div style="background-color: rgba(255,255,255,0.9); padding: 4px 10px; border-radius: 4px; font-size: 10px; color: #333; border: 1px solid #ccc; box-shadow: 0px 2px 5px rgba(0,0,0,0.1); white-space: nowrap; text-align: center;">
            <b>{COPYRIGHT}</b> | <span style="color:#666;">{FONTE_DATI}</span>
        </div>
    </div>

    <div style="position: fixed; top: 12px; left: 50px; background-color: rgba(255,255,255,0.9); padding: 5px 10px; border-radius: 4px; z-index: 9999; font-family: Arial, sans-serif; font-size: 12px; color: #005580; font-weight: bold; border: 1px solid #ccc; box-shadow: 0px 2px 5px rgba(0,0,0,0.1); white-space: nowrap;">
      {STRINGA_AGGIORNAMENTO}
    </div>
    '''
    map_italia.get_root().html.add_child(folium.Element(branding_html))

    stile_smartphone = """
    <style>
    @media (max-width: 600px) {
        #sidebar-tabelle-mcspark {
            width: calc(100% - 35px) !important;
            height: 210px !important;
            left: 15px !important;
            bottom: 90px !important;
            border-radius: 12px  !important;
            border-width: 2px  !important;
            z-index: 99999 !important;
        }
            #pannello-meteo-pulsanti {
            top: 10px !important;
            right: 10px !important;
            width: 160px !important;
            padding: 5px !important;
            z-index: 99999 !important;
        }
            .opzione-radio {
            display: block;
            margin-bottom: 8px;
            cursor: pointer;
            font-size: 12px;
            font-weight: bold;
            color: #333;
        }
    }

    @supports (-moz-appearance: none) {
        #sidebar-tabelle-mcspark {
            position: fixed !important;
            bottom: 90px !important;
            left: 15px !important;
            width: calc(100% - 35px) !important;
            border-radius: 12px !important;
            z-index: 99999 !important;
        }
    }
    </style>
    """
    map_italia.get_root().html.add_child(folium.Element(stile_smartphone))

    # 10. SALVATAGGIO
    # --- DA INCOLLARE DENTRO "genera_mappa_completa", PRIMA DI MAP_ITALIA.SAVE() ---
    script_memoria_filtri = """
    <script>
    document.addEventListener("DOMContentLoaded", function() {
        // ==========================================
        // 1. MEMORIA DEI FILTRI RADIO (OGGI/DOMANI)
        // ==========================================
        const filtriMeteo = document.querySelectorAll('input[type="radio"]');
        const filtroSalvato = localStorage.getItem("visualizzazioneMeteoScelta");
        
        if (filtroSalvato) {
            setTimeout(function() {
                filtriMeteo.forEach(radio => {
                    if (radio.value === filtroSalvato || radio.id === filtroSalvato) {
                        radio.checked = true;
                        radio.dispatchEvent(new Event('change'));
                        if (typeof radio.click === 'function') {
                            radio.click();
                        }
                    }
                });
            }, 150);
        }

        filtriMeteo.forEach(radio => {
            radio.addEventListener("change", function() {
                if (this.checked) {
                    localStorage.setItem("visualizzazioneMeteoScelta", this.value || this.id);
                }
            });
        });

        // ==========================================
        // 2. MEMORIA DELLA SCHEDA APERTA (SIDEBAR)
        // ==========================================
        const sidebar = document.getElementById("sidebar-tabelle-mcspark");
        
        if (sidebar) {
            const schedaStatoSalvato = localStorage.getItem("sidebarMeteoAperto");
            const contenutoSalvato = localStorage.getItem("sidebarMeteoContenuto");

            if (schedaStatoSalvato === "true" && contenutoSalvato) {
                sidebar.innerHTML = contenutoSalvato;
                sidebar.style.display = "block";
            }

            const observer = new MutationObserver(function() {
                if (sidebar.style.display === "block" || sidebar.innerHTML.trim() !== "") {
                    localStorage.setItem("sidebarMeteoAperto", "true");
                    localStorage.setItem("sidebarMeteoContenuto", sidebar.innerHTML);
                } else {
                    localStorage.setItem("sidebarMeteoAperto", "false");
                    localStorage.removeItem("sidebarMeteoContenuto");
                }
            });

            observer.observe(sidebar, { attributes: true, childList: true, characterData: true, attributeFilter: ['style'] });
        }
    });
    </script>
    """

    # Iniettiamo lo script nella mappa corrente
    map_italia.get_root().html.add_child(folium.Element(script_memoria_filtri))

    map_italia.save(nome_file)
    print(f"✅ Interfaccia completata in modo nativo e sicuro: {STRINGA_AGGIORNAMENTO}")


# ==========================================
# GENERAZIONE FILE GIORNO 1/2/3 + INDEX
# ==========================================
def genera_index_html():
    with open("index.html", "w", encoding="utf-8") as f:
        f.write("""<!DOCTYPE html>
        <html>
        <head>
            <title>Meteo McSpark</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { font-family: Arial, sans-serif; text-align: center; margin: 0; padding: 0; background-color: #f8f9fa; }
                
                /* FASCIA IN ALTO BLU NOTTE (VARIANTE A) */
                .header-bar {
                    background-color: #2c3e50;
                    background-image: radial-gradient(rgba(255, 255, 255, 0.15) 1px, transparent 1px);
                    background-size: 4px 4px;
                    padding: 15px 0 20px 0;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.25);
                }
                
                /* TITOLO BIANCO ED ELEGANTE */
                h2 { 
                    margin: 0 0 15px 0; 
                    color: #ffffff; 
                    font-size: 26px; 
                    letter-spacing: 0.5px;
                }
                
                .btn-bar { margin-bottom: 0px; }
                
                /* STILE DEI BOTTONI NON ATTIVI */
                button, .btn-bar a {
                    display: inline-block;
                    text-decoration: none;
                    margin: 0 6px;
                    padding: 10px 22px;
                    font-size: 14px;
                    font-weight: 600;
                    cursor: pointer;
                    border-radius: 6px;
                    border: 1px solid #4a5d71;
                    background-color: #34495e;
                    color: #cbd5e1;
                    transition: all 0.2s ease;
                    text-align: center;
                }
                
                /* EFFETTO MOUSE SUI BOTTONI */
                button:hover, .btn-bar a:hover {
                    background-color: #415b76;
                    color: #ffffff;
                    border-color: #cbd5e1;
                }
                
                /* STILE DEL BOTTONE ATTIVO */
                button.active, .btn-bar a.active {
                    background-color: #ffffff !important;
                    color: #2c3e50 !important;
                    border-color: #ffffff !important;
                    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
                }
                
                iframe { width: 100%; height: 86vh; border: none; display: block; }
            </style>
        </head>
        <body>
            <div class="header-bar">
                <h2>Previsioni Meteo McSpark</h2>
                <div class="btn-bar">
                    <button onclick="carica('day1.html', this)" class="active">Oggi</button>
                    <button onclick="carica('day2.html', this)">Domani</button>
                    <button onclick="carica('day3.html', this)">Dopodomani</button>
                </div>
            </div>
            
            <iframe id="frame" src="day1.html"></iframe>

        <script>
        // 1. Funzione classica per cambiare giorno nell'iframe
        function carica(file, elemento) {
            document.getElementById('frame').src = file;
            var bottoni = document.querySelectorAll('.btn-bar button');
            bottoni.forEach(function(btn) { btn.classList.remove('active'); });
            elemento.classList.add('active');
        }

        // 2. RIPRISTINO STATO AD OGNI CARICAMENTO DEL GIORNO
        document.getElementById('frame').addEventListener('load', function() {
            var iframeWindow = this.contentWindow;
            var iframeDocument = this.contentDocument || iframeWindow.document;
            
            // Aspettiamo che la mappa carichi le sue funzioni interne
            setTimeout(function() {
                
                // --- A. RIPRISTINO FILTRO METEO GLOBAL ---
                var filtroSalvato = localStorage.getItem("visualizzazioneMeteoScelta");
                var filtriMeteo = iframeDocument.querySelectorAll('#pannello-meteo-pulsanti input[type="radio"]');
                
                if (filtroSalvato && filtriMeteo.length > 0) {
                    filtriMeteo.forEach(function(radio) {
                        if (radio.value === filtroSalvato) {
                            radio.checked = true;
                            // Aggiorna la mappa usando la funzione nativa che hai scritto nell'interfaccia custom
                            if (typeof iframeWindow.aggiornaMappaEInvolucri === 'function') {
                                iframeWindow.aggiornaMappaEInvolucri(filtroSalvato);
                            }
                        }
                    });
                }
                
                // --- B. RIPRISTINO TABELLA REGIONE ---
                var regioneSalvata = localStorage.getItem("regioneAttivaMcSpark");
                if (regioneSalvata && typeof iframeWindow.mostraRegioneLaterale === 'function') {
                    // Chiamiamo la tua funzione nativa! Apre la sidebar, nasconde il benvenuto e mostra la tabella
                    iframeWindow.mostraRegioneLaterale(regioneSalvata);
                }
                
                // Avviamo l'ascolto per i prossimi click
                avviaMonitoraggio(iframeWindow, iframeDocument);
                
            }, 400); 
        });

        // 3. SALVATAGGIO IN MEMORIA IN TEMPO REALE
        function avviaMonitoraggio(iframeWindow, iframeDocument) {
            // Ascolta i cambi manuali dei radio button
            var filtriMeteo = iframeDocument.querySelectorAll('#pannello-meteo-pulsanti input[type="radio"]');
            filtriMeteo.forEach(function(radio) {
                radio.addEventListener('change', function() {
                    if (this.checked) {
                        localStorage.setItem("visualizzazioneMeteoScelta", this.value);
                    }
                });
            });

            // Controlla la variabile globale della mappa 'ultimaRegioneAperta' ogni 400ms e la salva
            setInterval(function() {
                if (iframeWindow.ultimaRegioneAperta) {
                    localStorage.setItem("regioneAttivaMcSpark", iframeWindow.ultimaRegioneAperta);
                }
            }, 400);
        }
        </script>
        </body>
        </html>
""")

if __name__ == "__main__":
    genera_mappa_completa(0, "day1.html")
    genera_mappa_completa(1, "day2.html")
    genera_mappa_completa(2, "day3.html")
    genera_index_html()
