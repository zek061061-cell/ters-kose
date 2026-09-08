"""Small on-demand coverage projection; never loads history in the browser."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from league_catalog import CATALOG_PATH, load_league_catalog


DATA_DIR = CATALOG_PATH.parent
LEGACY_NAMES = {
    "İngiltere Championship": "İngiltere EFL Championship",
    "İngiltere League One": "İngiltere EFL League One",
    "İngiltere League Two": "İngiltere EFL League Two",
    "ABD/Kanada Major League Soccer": "ABD MLS",
    "Çin Chinese Super League": "Çin Süper Ligi",
    "Romanya SuperLiga": "Romanya Liga I",
}


def build_coverage(data_dir: Path | str = DATA_DIR) -> dict:
    root = Path(data_dir)
    catalog = load_league_catalog(root / "league_catalog.json")
    history_meta = _read(root / "history_meta.json")
    future = _read(root / "future_fixtures.json")
    historical = history_meta.get("league_counts", {})
    upcoming: dict[str, int] = defaultdict(int)
    teams: dict[str, set[str]] = defaultdict(set)
    future_teams: dict[str, set[str]] = defaultdict(set)
    quality: dict[str, dict[str, int]] = defaultdict(lambda: {"played": 0, "ht": 0, "ft": 0, "week": 0})
    first_dates: dict[str, str] = {}
    last_dates: dict[str, str] = {}
    history_file = root / "history_10y.json"
    if history_file.exists():
        try:
            with history_file.open(encoding="utf-8") as handle:
                history_rows = json.load(handle)
            for match in history_rows if isinstance(history_rows, list) else history_rows.get("matches", []):
                name = str(match.get("league") or "")
                match_date = str(match.get("date") or "")[:10]
                if not name:
                    continue
                for field in ("home", "away"):
                    if match.get(field):
                        teams[name].add(str(match[field]))
                completed = match.get("ft_home") not in (None, "") and match.get("ft_away") not in (None, "")
                if completed:
                    quality[name]["played"] += 1
                    quality[name]["ft"] += 1
                    quality[name]["ht"] += int(match.get("ht_home") not in (None, "") and match.get("ht_away") not in (None, ""))
                    quality[name]["week"] += int(bool(match.get("week")))
                if match_date:
                    first_dates[name] = min(first_dates.get(name, match_date), match_date)
                    last_dates[name] = max(last_dates.get(name, match_date), match_date)
        except (OSError, json.JSONDecodeError):
            pass
    for match in future.get("matches", []):
        name = str(match.get("league") or "")
        if name:
            upcoming[name] += int(not match.get("completed"))
            for field in ("home", "away"):
                if match.get(field):
                    teams[name].add(str(match[field]))
                    future_teams[name].add(str(match[field]))
            match_date = str(match.get("date") or "")[:10]
            if match_date:
                first_dates[name] = min(first_dates.get(name, match_date), match_date)
                last_dates[name] = max(last_dates.get(name, match_date), match_date)
    rows = []
    for league in catalog:
        legacy_name = f"{league['country']} {league['canonical_name']}"
        source_name = LEGACY_NAMES.get(legacy_name, legacy_name)
        history_count = int(historical.get(source_name, 0))
        future_count = int(upcoming.get(source_name, 0))
        played = quality[source_name]["played"]
        ht_coverage = quality[source_name]["ht"] / played if played else 0
        ft_coverage = quality[source_name]["ft"] / played if played else 0
        week_coverage = quality[source_name]["week"] / played if played else 0
        reasons = []
        if len(teams[source_name]) < 8: reasons.append("teams_missing")
        if history_count < 80: reasons.append("history_missing_or_thin")
        if not future_count: reasons.append("future_fixtures_missing")
        if played and ht_coverage < .9: reasons.append("ht_coverage_low")
        if played and ft_coverage < 1: reasons.append("ft_coverage_low")
        if played and week_coverage < .75: reasons.append("week_coverage_low")
        if future_count and len(future_teams[source_name]) < min(8, len(teams[source_name])): reasons.append("future_team_coverage_thin")
        if not reasons:
            status = "OK"
        else:
            status = "Eksik"
        rows.append({
            "league_id": league["league_id"], "country": league["country"],
            "league": league["canonical_name"], "team_count": len(teams[source_name]),
            "future_team_count": len(future_teams[source_name]),
            "historical_matches": history_count, "future_matches": future_count,
            "ht_coverage": round(ht_coverage, 4), "ft_coverage": round(ft_coverage, 4),
            "week_coverage": round(week_coverage, 4), "missing_reasons": reasons,
            "first_date": first_dates.get(source_name), "last_date": last_dates.get(source_name),
            "sources": [item["source"] for item in league["source_support"] if item["status"] == "configured"],
            "status": status,
        })
    return {
        "summary": {
            "countries": len({row["country"] for row in rows}), "leagues": len(rows),
            "teams": _persistent_team_count(root, teams),
            "historical_matches": sum(map(int, historical.values())),
            "future_matches": sum(upcoming.values()),
            "ok_leagues": sum(row["status"] == "OK" for row in rows),
        },
        "leagues": rows,
    }


def load_coverage_report(data_dir: Path | str = DATA_DIR) -> dict:
    """Read the precomputed report; rebuild only in development/fallback mode."""
    root = Path(data_dir)
    saved = _read(root / "coverage_report.json")
    if saved.get("summary") and isinstance(saved.get("leagues"), list):
        return {key: value for key, value in saved.items() if key != "ok"}
    return build_coverage(root)


def _read(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
            return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _persistent_team_count(root: Path, fallback: dict[str, set[str]]) -> int:
    catalog = _read(root / "team_catalog.json")
    return int(catalog.get("team_count") or len({(league, team) for league, values in fallback.items() for team in values}))
