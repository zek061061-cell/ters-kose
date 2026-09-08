"""Atomic repository-owned league/season/date shard persistence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from source_adapters import fixture_identity


class ShardStore:
    def __init__(self, root: Path | str = "data/v7_shards") -> None:
        self.root = Path(root)

    def save(self, rows: list[dict], mode: str) -> dict:
        groups: dict[tuple[str, str], list[dict]] = {}
        for row in rows:
            league_id = str(row.get("league_id") or "").strip()
            season = str(row.get("season") or "unknown").replace("/", "-")
            if league_id:
                groups.setdefault((league_id, season), []).append(row)
        written = retained = 0
        for (league_id, season), incoming in groups.items():
            path = self.root / league_id / season / f"{mode}.json"
            existing = self._read(path)
            merged = {fixture_identity(row): row for row in existing if _valid(row)}
            for row in incoming:
                if not _valid(row):
                    continue
                key = fixture_identity(row)
                old = merged.get(key)
                if old:
                    retained += 1
                    merged[key] = _richer(old, row)
                else:
                    merged[key] = row
            # Empty/invalid source responses never replace a valid shard.
            if not merged:
                continue
            payload = {"league_id": league_id, "season": season, "mode": mode, "matches": sorted(merged.values(), key=lambda item: (item["date"], item.get("kickoff", "")))}
            self._atomic_json(path, payload)
            written += len(payload["matches"])
        return {"shards": len(groups), "matches": written, "retained": retained}

    @staticmethod
    def _read(path: Path) -> list[dict]:
        try:
            with path.open(encoding="utf-8") as handle:
                return json.load(handle).get("matches", [])
        except (OSError, json.JSONDecodeError):
            return []

    @staticmethod
    def _atomic_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=path.name, dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def _valid(row: dict) -> bool:
    return bool(row.get("date") and row.get("league_id") and row.get("home") and row.get("away"))


def _richer(first: dict, second: dict) -> dict:
    score = lambda row: sum(row.get(field) not in (None, "", 0) for field in ("week", "ht_home", "ht_away", "ft_home", "ft_away", "kickoff", "home_logo", "away_logo"))
    winner, other = (second, first) if score(second) > score(first) else (first, second)
    result = dict(winner)
    for key, value in other.items():
        if result.get(key) in (None, "", [], {}):
            result[key] = value
    result["sources"] = sorted(set(first.get("sources", []) + second.get("sources", [])))
    return result
