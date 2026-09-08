"""Build a persistent canonical team catalogue from owned match snapshots."""

from __future__ import annotations

import json
from pathlib import Path

from fixture_store import DATA_DIR, FixtureStore
from source_adapters import canonical_key
from team_catalog import canonical_team_key


INPUTS = ("history_10y.json", "riskbudur_57_history.json", "future_fixtures.json", "current_fixtures.json", "bulletin_1y.json")


def build_team_catalog(data_dir: Path | str = DATA_DIR) -> dict:
    root = Path(data_dir)
    store = FixtureStore(root)
    groups: dict[tuple[str, str], dict] = {}
    for filename in INPUTS:
        path = root / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        rows = payload if isinstance(payload, list) else payload.get("matches", [])
        for match in rows:
            league = store._league_by_name.get(canonical_key(match.get("league")))
            if not league:
                continue
            for side in ("home", "away"):
                raw = str(match.get(side) or "").strip()
                if not raw:
                    continue
                key = (league["country"], canonical_team_key(raw))
                item = groups.setdefault(key, {
                    "team_id": f"{canonical_key(league['country'])}.{canonical_team_key(raw)}",
                    "canonical_name": raw, "aliases": set(), "country": league["country"],
                    "league_ids": set(), "logo": "",
                })
                item["aliases"].add(raw)
                item["league_ids"].add(league["league_id"])
                logo = str(match.get(f"{side}_logo") or "")
                if logo and not item["logo"]:
                    item["logo"] = logo
    teams = []
    for item in groups.values():
        item["aliases"] = sorted(item["aliases"])
        item["league_ids"] = sorted(item["league_ids"])
        teams.append(item)
    teams.sort(key=lambda item: item["team_id"])
    return {"schema_version": 1, "team_count": len(teams), "teams": teams}


if __name__ == "__main__":
    output = DATA_DIR / "team_catalog.json"
    result = build_team_catalog()
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"teams": result["team_count"]}, ensure_ascii=False))
