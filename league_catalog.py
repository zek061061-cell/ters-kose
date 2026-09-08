"""Master league catalogue loading and validation.

The catalogue is data, not an application limit.  Adapters may discover new
competitions and the generated JSON can grow without changing this module.
"""

from __future__ import annotations

import json
from pathlib import Path


CATALOG_PATH = Path(__file__).with_name("data") / "league_catalog.json"
REQUIRED_FIELDS = {
    "league_id", "canonical_name", "country", "tier", "season_format",
    "aliases", "source_support", "active", "men_professional",
}
SEASON_FORMATS = {"cross_year", "calendar_year", "split_year"}


def load_league_catalog(path: Path | str = CATALOG_PATH) -> list[dict]:
    with Path(path).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    leagues = payload.get("leagues") if isinstance(payload, dict) else payload
    if not isinstance(leagues, list):
        raise ValueError("league catalog must contain a leagues array")
    validate_league_catalog(leagues)
    return leagues


def validate_league_catalog(leagues: list[dict]) -> None:
    ids: set[str] = set()
    names: set[tuple[str, str]] = set()
    for position, league in enumerate(leagues):
        missing = REQUIRED_FIELDS - set(league)
        if missing:
            raise ValueError(f"league #{position} missing fields: {sorted(missing)}")
        league_id = str(league["league_id"]).strip()
        if not league_id or league_id in ids:
            raise ValueError(f"duplicate/empty league_id: {league_id!r}")
        ids.add(league_id)
        name_key = (str(league["country"]), str(league["canonical_name"]))
        if name_key in names:
            raise ValueError(f"duplicate canonical league: {name_key}")
        names.add(name_key)
        if not isinstance(league["tier"], int) or league["tier"] < 1:
            raise ValueError(f"invalid tier for {league_id}")
        if league["season_format"] not in SEASON_FORMATS:
            raise ValueError(f"invalid season_format for {league_id}")
        if not isinstance(league["aliases"], list) or not league["aliases"]:
            raise ValueError(f"aliases must be a non-empty array for {league_id}")
        if not isinstance(league["source_support"], list):
            raise ValueError(f"source_support must be an array for {league_id}")
        if not isinstance(league["active"], bool) or not isinstance(league["men_professional"], bool):
            raise ValueError(f"status flags must be booleans for {league_id}")


def catalog_summary(leagues: list[dict] | None = None) -> dict[str, int]:
    leagues = leagues if leagues is not None else load_league_catalog()
    active = [item for item in leagues if item["active"] and item["men_professional"]]
    return {
        "countries": len({item["country"] for item in active}),
        "leagues": len(active),
        "configured_sources": sum(
            any(source.get("status") == "configured" for source in item["source_support"])
            for item in active
        ),
    }
