# province_italia.py
# Lista ufficiale delle 107 province italiane suddivise per regione con coordinate geografiche

PROVINCE_BY_REGIONE = {
    "Abruzzo": [
        {"nome": "L'Aquila", "lat": 42.354, "lon": 13.392},
        {"nome": "Chieti", "lat": 42.351, "lon": 14.167},
        {"nome": "Pescara", "lat": 42.464, "lon": 14.214},
        {"nome": "Teramo", "lat": 42.658, "lon": 13.704}
    ],
    "Basilicata": [
        {"nome": "Potenza", "lat": 40.642, "lon": 15.805},
        {"nome": "Matera", "lat": 40.666, "lon": 16.605}
    ],
    "Calabria": [
        {"nome": "Catanzaro", "lat": 38.905, "lon": 16.594},
        {"nome": "Cosenza", "lat": 39.298, "lon": 16.252},
        {"nome": "Crotone", "lat": 39.081, "lon": 17.127},
        {"nome": "Reggio Calabria", "lat": 38.114, "lon": 15.650},
        {"nome": "Vibo Valentia", "lat": 38.675, "lon": 16.101}
    ],
    "Campania": [
        {"nome": "Napoli", "lat": 40.852, "lon": 14.268},
        {"nome": "Avellino", "lat": 40.914, "lon": 14.792},
        {"nome": "Benevento", "lat": 41.130, "lon": 14.777},
        {"nome": "Caserta", "lat": 41.073, "lon": 14.332},
        {"nome": "Salerno", "lat": 40.678, "lon": 14.765}
    ],
    "Emilia-Romagna": [
        {"nome": "Bologna", "lat": 44.494, "lon": 11.343},
        {"nome": "Ferrara", "lat": 44.838, "lon": 11.619},
        {"nome": "Forlì-Cesena", "lat": 44.222, "lon": 12.040},
        {"nome": "Modena", "lat": 44.647, "lon": 10.925},
        {"nome": "Parma", "lat": 44.801, "lon": 10.328},
        {"nome": "Piacenza", "lat": 45.053, "lon": 9.693},
        {"nome": "Ravenna", "lat": 44.418, "lon": 12.204},
        {"nome": "Reggio Emilia", "lat": 44.698, "lon": 10.631},
        {"nome": "Rimini", "lat": 44.059, "lon": 12.568}
    ],
    "Friuli-Venezia Giulia": [
        {"nome": "Trieste", "lat": 45.649, "lon": 13.777},
        {"nome": "Gorizia", "lat": 45.940, "lon": 13.621},
        {"nome": "Pordenone", "lat": 45.956, "lon": 12.660},
        {"nome": "Udine", "lat": 46.062, "lon": 13.244}
    ],
    "Lazio": [
        {"nome": "Roma", "lat": 41.892, "lon": 12.492},
        {"nome": "Frosinone", "lat": 41.639, "lon": 13.341},
        {"nome": "Latina", "lat": 41.467, "lon": 12.903},
        {"nome": "Rieti", "lat": 42.404, "lon": 12.862},
        {"nome": "Viterbo", "lat": 42.417, "lon": 12.107}
    ],
    "Liguria": [
        {"nome": "Genova", "lat": 44.406, "lon": 8.934},
        {"nome": "Imperia", "lat": 43.886, "lon": 8.042},
        {"nome": "La Spezia", "lat": 44.110, "lon": 9.844},
        {"nome": "Savona", "lat": 44.308, "lon": 8.481}
    ],
    "Lombardia": [
        {"nome": "Milano", "lat": 45.464, "lon": 9.190},
        {"nome": "Bergamo", "lat": 45.698, "lon": 9.677},
        {"nome": "Brescia", "lat": 45.541, "lon": 10.211},
        {"nome": "Como", "lat": 45.808, "lon": 9.085},
        {"nome": "Cremona", "lat": 45.133, "lon": 10.022},
        {"nome": "Lecco", "lat": 45.856, "lon": 9.397},
        {"nome": "Lodi", "lat": 45.314, "lon": 9.503},
        {"nome": "Mantova", "lat": 45.156, "lon": 10.791},
        {"nome": "Monza e della Brianza", "lat": 45.584, "lon": 9.274},
        {"nome": "Pavia", "lat": 45.185, "lon": 9.155},
        {"nome": "Sondrio", "lat": 46.169, "lon": 9.869},
        {"nome": "Varese", "lat": 45.817, "lon": 8.826}
    ],
    "Marche": [
        {"nome": "Ancona", "lat": 43.616, "lon": 13.518},
        {"nome": "Ascoli Piceno", "lat": 42.853, "lon": 13.574},
        {"nome": "Fermo", "lat": 43.161, "lon": 13.718},
        {"nome": "Macerata", "lat": 43.300, "lon": 13.453},
        {"nome": "Pesaro e Urbino", "lat": 43.910, "lon": 12.913}
    ],
    "Molise": [
        {"nome": "Campobasso", "lat": 41.560, "lon": 14.659},
        {"nome": "Isernia", "lat": 41.596, "lon": 14.232}
    ],
    "Piemonte": [
        {"nome": "Torino", "lat": 45.070, "lon": 7.686},
        {"nome": "Alessandria", "lat": 44.912, "lon": 8.615},
        {"nome": "Asti", "lat": 44.900, "lon": 8.206},
        {"nome": "Biella", "lat": 45.563, "lon": 8.057},
        {"nome": "Cuneo", "lat": 44.389, "lon": 7.547},
        {"nome": "Novara", "lat": 45.446, "lon": 8.621},
        {"nome": "Verbano-Cusio-Ossola", "lat": 45.937, "lon": 8.541},
        {"nome": "Vercelli", "lat": 45.324, "lon": 8.423}
    ],
    "Puglia": [
        {"nome": "Bari", "lat": 41.117, "lon": 16.871},
        {"nome": "Barletta-Andria-Trani", "lat": 41.318, "lon": 16.279},
        {"nome": "Brindisi", "lat": 40.632, "lon": 17.936},
        {"nome": "Foggia", "lat": 41.462, "lon": 15.544},
        {"nome": "Lecce", "lat": 40.354, "lon": 18.172},
        {"nome": "Taranto", "lat": 40.464, "lon": 17.247}
    ],
    "Sardegna": [
        {"nome": "Cagliari", "lat": 39.223, "lon": 9.121},
        {"nome": "Nuoro", "lat": 40.320, "lon": 9.326},
        {"nome": "Oristano", "lat": 39.905, "lon": 8.591},
        {"nome": "Sassari", "lat": 40.725, "lon": 8.560},
        {"nome": "Sud Sardegna", "lat": 39.151, "lon": 8.522}
    ],
    "Sicilia": [
        {"nome": "Palermo", "lat": 38.115, "lon": 13.361},
        {"nome": "Agrigento", "lat": 37.309, "lon": 13.587},
        {"nome": "Caltanissetta", "lat": 37.490, "lon": 14.062},
        {"nome": "Catania", "lat": 37.502, "lon": 15.087},
        {"nome": "Enna", "lat": 37.567, "lon": 14.275},
        {"nome": "Messina", "lat": 38.193, "lon": 15.555},
        {"nome": "Ragusa", "lat": 36.928, "lon": 14.717},
        {"nome": "Siracusa", "lat": 37.075, "lon": 15.286},
        {"nome": "Trapani", "lat": 38.017, "lon": 12.514}
    ],
    "Toscana": [
        {"nome": "Firenze", "lat": 43.769, "lon": 11.255},
        {"nome": "Arezzo", "lat": 43.463, "lon": 11.878},
        {"nome": "Grosseto", "lat": 42.766, "lon": 11.109},
        {"nome": "Livorno", "lat": 43.548, "lon": 10.316},
        {"nome": "Lucca", "lat": 43.842, "lon": 10.502},
        {"nome": "Massa-Carrara", "lat": 44.036, "lon": 10.138},
        {"nome": "Pisa", "lat": 43.708, "lon": 10.403},
        {"nome": "Pistoia", "lat": 43.931, "lon": 10.917},
        {"nome": "Prato", "lat": 43.877, "lon": 11.102},
        {"nome": "Siena", "lat": 43.318, "lon": 11.332}
    ],
    "Trentino-Alto Adige": [
        {"nome": "Trento", "lat": 46.067, "lon": 11.121},
        {"nome": "Bolzano", "lat": 46.490, "lon": 11.339}
    ],
    "Umbria": [
        {"nome": "Perugia", "lat": 43.112, "lon": 12.388},
        {"nome": "Terni", "lat": 42.563, "lon": 12.641}
    ],
    "Valle d'Aosta": [
        {"nome": "Aosta", "lat": 45.737, "lon": 7.315}
    ],
    "Veneto": [
        {"nome": "Venezia", "lat": 45.434, "lon": 12.338},
        {"nome": "Belluno", "lat": 46.142, "lon": 12.216},
        {"nome": "Padova", "lat": 45.406, "lon": 11.876},
        {"nome": "Rovigo", "lat": 45.070, "lon": 11.790},
        {"nome": "Treviso", "lat": 45.666, "lon": 12.245},
        {"nome": "Verona", "lat": 45.438, "lon": 10.991},
        {"nome": "Vicenza", "lat": 45.547, "lon": 11.549}
    ]
}

# Coordinate centrali approssimative delle 20 regioni per posizionare i cerchi-pulsante
REGIONI_COORDINATE = {
    "Abruzzo": [42.35, 14.0], "Basilicata": [40.5, 16.2], "Calabria": [39.0, 16.5],
    "Campania": [40.8, 15.0], "Emilia-Romagna": [44.5, 11.0], "Friuli-Venezia Giulia": [46.1, 13.1],
    "Lazio": [41.9, 12.7], "Liguria": [44.4, 8.9], "Lombardia": [45.7, 9.8],
    "Marche": [43.3, 13.2], "Molise": [41.7, 14.5], "Piemonte": [45.1, 7.9],
    "Puglia": [41.0, 16.8], "Sardegna": [40.0, 9.0], "Sicilia": [37.5, 14.0],
    "Toscana": [43.4, 11.1], "Trentino-Alto Adige": [46.4, 11.3], "Umbria": [42.9, 12.5],
    "Valle d'Aosta": [45.7, 7.3], "Veneto": [45.6, 11.9]
}