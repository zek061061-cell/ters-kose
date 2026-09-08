"""Fetch priority leagues through v7 adapters without destroying good snapshots."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path

from network_adapters import EspnAdapter, FootballDataCsvAdapter, SahadanAdapter, TffAdapter
from shard_store import ShardStore
from source_adapters import AdapterRegistry


ESPN_PRIORITY = {
    "almanya.3-liga": "ger.3", "isvec.superettan": "swe.2", "japonya.j1-league": "jpn.1",
    "japonya.j2-league": "jpn.2", "japonya.j3-league": "jpn.3",
    "guney-kore.k-league-1": "kor.1", "guney-kore.k-league-2": "kor.2",
    "cin.chinese-super-league": "chn.1", "cin.china-league-one": "chn.2",
    "hollanda.eerste-divisie": "ned.2", "portekiz.liga-portugal-2": "por.2",
    "fransa.national": "fra.3",
}


def _json_env(name: str) -> dict:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="date_from", default=(date.today() - timedelta(days=365)).isoformat())
    parser.add_argument("--to", dest="date_to", default=(date.today() + timedelta(days=370)).isoformat())
    parser.add_argument("--output", default="data/v7_ingested_fixtures.json")
    parser.add_argument("--mode", choices=("current", "future", "history"), default="current")
    args = parser.parse_args()
    configured = {
        "tff": _json_env("V7_TFF_PAGES"),
        "sahadan": _json_env("V7_SAHADAN_URLS"),
        "football-data": _json_env("V7_FOOTBALL_DATA_URLS"),
    }
    matches, audit = [], []
    for league_id in ESPN_PRIORITY:
        adapters = []
        if league_id in configured["tff"]: adapters.append(TffAdapter(configured["tff"]))
        if league_id in configured["sahadan"]: adapters.append(SahadanAdapter(configured["sahadan"]))
        if league_id in configured["football-data"]: adapters.append(FootballDataCsvAdapter(configured["football-data"]))
        if league_id in ESPN_PRIORITY: adapters.append(EspnAdapter(ESPN_PRIORITY))
        registry = AdapterRegistry(adapters)
        rows = registry.fixtures(league_id, args.date_from, args.date_to)
        matches.extend(rows)
        audit.append({
            "league_id": league_id, "rows": len(rows),
            "status": "ok" if rows else "source_error" if any(item.health.error_count for item in adapters) else "empty",
            "attempts": registry.health(),
        })
    output = Path(args.output)
    # An unavailable provider must not erase a previous usable snapshot.
    if matches:
        output.write_text(json.dumps({"matches": matches}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        shard_result = ShardStore().save(matches, args.mode)
    else:
        shard_result = {"shards": 0, "matches": 0, "retained": 0}
    Path("data/source_audit.json").write_text(json.dumps({"mode": args.mode, "leagues": audit, "shards": shard_result}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"matches": len(matches), "successful_leagues": sum(item["status"] == "ok" for item in audit)}, ensure_ascii=False))
    # No-data/provider outages are recorded in source_audit.json and must not
    # turn the whole scheduled workflow red. Validation/test failures still fail later steps.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
