"""Import the 21-column Riskbudur browser DATA export into the focused 57-league core.

Input is the JSON array exported from window.DATA. The source layout is:
0 league, 1 season, 2 week, 3 day, 4 home, 5 away, 6 FT score,
7 HT score, 8 HT/FT label, 9 six-plus, 10 over/under 2.5,
11 over/under 3.5, 12 BTTS, 13 HT 0.5, 14 HT 1.5,
15 date, 16 year, 17 time, 18 country, 19 referee, 20 row order.

Only country/league pairs that belong to the focused core are retained. No
score is invented: a row is completed only when column 6 contains a score.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).with_name("data")
DEFAULT_OUTPUT = DATA_DIR / "riskbudur_57_master.json.gz"

SOURCE_TO_CANONICAL = {
    ("ABD", "MLS"): "abd-kanada.major-league-soccer",
    ("Almanya", "Bundesliga"): "almanya.bundesliga",
    ("Almanya", "2. Bundesliga"): "almanya.2-bundesliga",
    ("Almanya", "3. Lig"): "almanya.3-liga",
    ("Avusturya", "Bundesliga"): "avusturya.bundesliga",
    ("Avusturya", "2. Lig"): "avusturya.2-liga",
    ("Belçika", "Pro Lig"): "belcika.pro-league",
    ("Brezilya", "Serie A"): "brezilya.serie-a",
    ("Danimarka", "Süper Lig"): "danimarka.superliga",
    ("Finlandiya", "Veikkausliiga"): "finlandiya.veikkausliiga",
    ("Fransa", "Ligue 1"): "fransa.ligue-1",
    ("Fransa", "Ligue 2"): "fransa.ligue-2",
    ("Fransa", "Ligue 3"): "fransa.national",
    ("Güney Kore", "K-Lig"): "guney-kore.k-league-1",
    ("Hollanda", "Eredivisie"): "hollanda.eredivisie",
    ("Hollanda", "Eerste Divisie"): "hollanda.eerste-divisie",
    ("Japonya", "J1 Lig"): "japonya.j1-league",
    ("Norveç", "Eliteserien"): "norvec.eliteserien",
    ("Norveç", "1. Lig"): "norvec.1-division",
    ("Portekiz", "Premier Lig"): "portekiz.primeira-liga",
    ("Türkiye", "Trendyol Süper Lig"): "turkiye.super-lig",
    ("Türkiye", "Trendyol 1. Lig"): "turkiye.1-lig",
    ("Yunanistan", "Süper Lig"): "yunanistan.super-league",
    ("Çin", "Süper Lig"): "cin.chinese-super-league",
    ("İngiltere", "Premier Lig"): "ingiltere.premier-league",
    ("İngiltere", "Championship"): "ingiltere.championship",
    ("İngiltere", "1. Lig"): "ingiltere.league-one",
    ("İngiltere", "2. Lig"): "ingiltere.league-two",
    ("İngiltere", "Ulusal Lig"): "ingiltere.national-league",
    ("İrlanda Cumhuriyeti", "Premier Lig"): "irlanda.premier-division",
    ("İskoçya", "Premiership"): "iskocya.premiership",
    ("İskoçya", "Championship"): "iskocya.championship",
    ("İspanya", "LaLiga"): "ispanya.la-liga",
    ("İspanya", "LaLiga 2"): "ispanya.laliga-2",
    ("İsveç", "Allsvenskan"): "isvec.allsvenskan",
    ("İsveç", "Superettan"): "isvec.superettan",
    ("İsviçre", "Süper Lig"): "isvicre.super-league",
    ("İtalya", "Serie A"): "italya.serie-a",
    ("İtalya", "Serie B"): "italya.serie-b",
}

CANONICAL_META = {
    "abd-kanada.major-league-soccer": ("ABD/Kanada", "Major League Soccer"),
    "almanya.bundesliga": ("Almanya", "Bundesliga"),
    "almanya.2-bundesliga": ("Almanya", "2. Bundesliga"),
    "almanya.3-liga": ("Almanya", "3. Liga"),
    "avusturya.bundesliga": ("Avusturya", "Bundesliga"),
    "avusturya.2-liga": ("Avusturya", "2. Liga"),
    "belcika.pro-league": ("Belçika", "Pro League"),
    "brezilya.serie-a": ("Brezilya", "Série A"),
    "danimarka.superliga": ("Danimarka", "Superliga"),
    "finlandiya.veikkausliiga": ("Finlandiya", "Veikkausliiga"),
    "fransa.ligue-1": ("Fransa", "Ligue 1"),
    "fransa.ligue-2": ("Fransa", "Ligue 2"),
    "fransa.national": ("Fransa", "National"),
    "guney-kore.k-league-1": ("Güney Kore", "K League 1"),
    "hollanda.eredivisie": ("Hollanda", "Eredivisie"),
    "hollanda.eerste-divisie": ("Hollanda", "Eerste Divisie"),
    "japonya.j1-league": ("Japonya", "J1 League"),
    "norvec.eliteserien": ("Norveç", "Eliteserien"),
    "norvec.1-division": ("Norveç", "1. Division"),
    "portekiz.primeira-liga": ("Portekiz", "Primeira Liga"),
    "turkiye.super-lig": ("Türkiye", "Süper Lig"),
    "turkiye.1-lig": ("Türkiye", "1. Lig"),
    "yunanistan.super-league": ("Yunanistan", "Super League"),
    "cin.chinese-super-league": ("Çin", "Chinese Super League"),
    "ingiltere.premier-league": ("İngiltere", "Premier League"),
    "ingiltere.championship": ("İngiltere", "Championship"),
    "ingiltere.league-one": ("İngiltere", "League One"),
    "ingiltere.league-two": ("İngiltere", "League Two"),
    "ingiltere.national-league": ("İngiltere", "National League"),
    "irlanda.premier-division": ("İrlanda", "Premier Division"),
    "iskocya.premiership": ("İskoçya", "Premiership"),
    "iskocya.championship": ("İskoçya", "Championship"),
    "ispanya.la-liga": ("İspanya", "La Liga"),
    "ispanya.laliga-2": ("İspanya", "LaLiga 2"),
    "isvec.allsvenskan": ("İsveç", "Allsvenskan"),
    "isvec.superettan": ("İsveç", "Superettan"),
    "isvicre.super-league": ("İsviçre", "Super League"),
    "italya.serie-a": ("İtalya", "Serie A"),
    "italya.serie-b": ("İtalya", "Serie B"),
}


def _score(value):
    match = re.fullmatch(r"\s*(\d+)\s*[-:]\s*(\d+)\s*", str(value or ""))
    return (int(match.group(1)), int(match.group(2))) if match else (None, None)


def _result(home, away):
    if home is None or away is None:
        return ""
    return "1" if home > away else "2" if away > home else "X"


def convert(rows: list[list]) -> dict:
    output, seen = [], set()
    rejected = {"outside_core57": 0, "short_row": 0, "missing_date_or_team": 0, "duplicate": 0}

    for raw in rows:
        if not isinstance(raw, list) or len(raw) < 21:
            rejected["short_row"] += 1
            continue
        source_key = (str(raw[18] or "").strip(), str(raw[0] or "").strip())
        league_id = SOURCE_TO_CANONICAL.get(source_key)
        if not league_id:
            rejected["outside_core57"] += 1
            continue

        match_date = str(raw[15] or "").strip()[:10]
        home, away = str(raw[4] or "").strip(), str(raw[5] or "").strip()
        if not match_date or not home or not away:
            rejected["missing_date_or_team"] += 1
            continue

        identity = (league_id, match_date, home.casefold(), away.casefold())
        if identity in seen:
            rejected["duplicate"] += 1
            continue
        seen.add(identity)

        ft_home, ft_away = _score(raw[6])
        ht_home, ht_away = _score(raw[7])
        completed = ft_home is not None and ft_away is not None
        total = ft_home + ft_away if completed else None
        country, league_name = CANONICAL_META[league_id]
        kickoff_time = str(raw[17] or "").strip()
        kickoff = f"{match_date}T{kickoff_time}:00" if re.fullmatch(r"\d{1,2}:\d{2}", kickoff_time) else match_date

        output.append({
            "event_id": f"RB|{league_id}|{match_date}|{home}|{away}",
            "date": match_date,
            "kickoff": kickoff,
            "league_id": league_id,
            "league": f"{country} {league_name}",
            "country": country,
            "season": str(raw[1] or "").strip(),
            "week": str(raw[2] or "").strip() or None,
            "day": str(raw[3] or "").strip(),
            "home": home,
            "away": away,
            "completed": completed,
            "ft_home": ft_home,
            "ft_away": ft_away,
            "ht_home": ht_home,
            "ht_away": ht_away,
            "ht_ft": f"{_result(ht_home, ht_away)}/{_result(ft_home, ft_away)}" if ht_home is not None and completed else "",
            "six_plus": (total >= 6) if total is not None else None,
            "over25": (total >= 3) if total is not None else None,
            "over35": (total >= 4) if total is not None else None,
            "btts": (ft_home > 0 and ft_away > 0) if total is not None else None,
            "referee": str(raw[19] or "").strip(),
            "source": "Riskbudur DATA export",
        })

    output.sort(key=lambda row: (row["date"], row["league_id"], row["home"], row["away"]))
    return {
        "schema_version": 1,
        "profile": "riskbudur-57",
        "source_rows": len(rows),
        "mapped_leagues": len({row["league_id"] for row in output}),
        "match_count": len(output),
        "history_count": sum(bool(row["completed"]) for row in output),
        "future_count": sum(not row["completed"] for row in output),
        "rejected": rejected,
        "matches": output,
    }


def load_input(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def write_output(payload: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    payload = convert(load_input(Path(args.input)))
    write_output(payload, Path(args.output))
    print(json.dumps({key: payload[key] for key in ("source_rows", "mapped_leagues", "match_count", "history_count", "future_count", "rejected")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
