"""Automatic provider registry for Ters Köşe v7.

Only providers with known/public identifiers are auto-configured here.
Secrets remain optional overrides in ingest_v7.py.
"""

FOOTBALL_DATA_CODES = {
    "ingiltere.premier-league": "E0",
    "ingiltere.championship": "E1",
    "ingiltere.league-one": "E2",
    "ingiltere.league-two": "E3",
    "ingiltere.national-league": "EC",
    "iskocya.premiership": "SC0",
    "iskocya.championship": "SC1",
    "iskocya.league-one": "SC2",
    "iskocya.league-two": "SC3",
    "almanya.bundesliga": "D1",
    "almanya.2-bundesliga": "D2",
    "italya.serie-a": "I1",
    "italya.serie-b": "I2",
    "ispanya.la-liga": "SP1",
    "ispanya.laliga-2": "SP2",
    "fransa.ligue-1": "F1",
    "fransa.ligue-2": "F2",
    "hollanda.eredivisie": "N1",
    "belcika.pro-league": "B1",
    "portekiz.primeira-liga": "P1",
    "turkiye.super-lig": "T1",
    "yunanistan.super-league": "G1",
}

def football_data_auto_config():
    return {league_id: f"AUTO:{code}" for league_id, code in FOOTBALL_DATA_CODES.items()}
