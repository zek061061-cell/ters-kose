"""Central fixture store used by Bulletin, Radar, and coverage reporting."""

from __future__ import annotations

import gzip
import json
import lzma
from datetime import date
from pathlib import Path
from threading import Lock

from league_catalog import load_league_catalog
from riskbudur_data_import import convert
from source_adapters import AdapterRegistry, SourceAdapter, canonical_key, fixture_identity, normalize_fixture
from team_catalog import Team, TeamCatalog


DATA_DIR = Path(__file__).with_name("data")
PRIVATE_FIXTURE_PATH = __import__("os").environ.get("TERS_KOSE_PRIVATE_FIXTURE_PATH", "").strip()


class JsonFixtureAdapter(SourceAdapter):
    """Adapter for a repository-owned fixture snapshot, cached by file mtime."""

    def __init__(self, source_id: str, path: Path, priority: int) -> None:
        self.source_id, self.path, self.priority = source_id, path, priority
        self._cached_mtime: int | None = None
        self._cached_rows: list[dict] = []
        self._cache_lock = Lock()
        super().__init__()

    def fetch_fixtures(self, league_id: str, date_from: str, date_to: str) -> list[dict]:
        rows = self._load()
        return [row for row in rows if date_from <= str(row.get("date") or "") <= date_to]

    def _load(self) -> list[dict]:
        mtime = self.path.stat().st_mtime_ns
        with self._cache_lock:
            if self._cached_mtime != mtime:
                with self.path.open(encoding="utf-8") as handle:
                    payload = json.load(handle)
                self._cached_rows = payload.get("matches", [])
                self._cached_mtime = mtime
                self.health.covered_leagues = len({
                    str(row.get("league") or "").strip() for row in self._cached_rows
                    if str(row.get("league") or "").strip()
                })
            return self._cached_rows


class GzipJsonFixtureAdapter(JsonFixtureAdapter):
    def _load(self) -> list[dict]:
        mtime = self.path.stat().st_mtime_ns
        with self._cache_lock:
            if self._cached_mtime != mtime:
                with gzip.open(self.path, "rt", encoding="utf-8") as handle:
                    payload = json.load(handle)
                self._cached_rows = payload.get("matches", [])
                self._cached_mtime = mtime
            return self._cached_rows


class RiskbudurSourceAdapter(JsonFixtureAdapter):
    """Read the compact xz-compressed 21-column Riskbudur DATA export."""

    def _load(self) -> list[dict]:
        mtime = self.path.stat().st_mtime_ns
        with self._cache_lock:
            if self._cached_mtime != mtime:
                with lzma.open(self.path, "rt", encoding="utf-8") as handle:
                    source_rows = json.load(handle)
                payload = convert(source_rows)
                self._cached_rows = payload.get("matches", [])
                self._cached_mtime = mtime
                self.health.covered_leagues = int(payload.get("mapped_leagues") or 0)
            return self._cached_rows


class FixtureStore:
    def __init__(self, data_dir: Path | str = DATA_DIR) -> None:
        root = Path(data_dir)
        self.catalog = load_league_catalog(root / "league_catalog.json")
        self._league_by_name = self._league_index(self.catalog)
        self._league_by_id = {row["league_id"]: row for row in self.catalog}
        adapters = []

        private_path = Path(PRIVATE_FIXTURE_PATH).expanduser() if PRIVATE_FIXTURE_PATH else None
        if private_path and private_path.exists():
            if private_path.suffix == ".xz":
                adapters.append(RiskbudurSourceAdapter("private-runtime-source", private_path, 4))
            elif private_path.suffix == ".gz":
                adapters.append(GzipJsonFixtureAdapter("private-runtime-master", private_path, 4))
            else:
                adapters.append(JsonFixtureAdapter("private-runtime-json", private_path, 4))
        elif (root / "riskbudur_57_source.json.xz").exists():
            adapters.append(RiskbudurSourceAdapter("riskbudur-57-source", root / "riskbudur_57_source.json.xz", 34))
        elif (root / "riskbudur_57_master.json.gz").exists():
            adapters.append(GzipJsonFixtureAdapter("riskbudur-57-master", root / "riskbudur_57_master.json.gz", 35))
        elif (root / "riskbudur_57_history.json").exists():
            adapters.append(JsonFixtureAdapter("riskbudur-57-history", root / "riskbudur_57_history.json", 40))
        self.registry = AdapterRegistry(adapters)

    @staticmethod
    def _league_index(catalog: list[dict]) -> dict[str, dict]:
        index = {}
        for league in catalog:
            country = league["country"]
            values = [league["canonical_name"], *league["aliases"]]
            for value in values:
                index[canonical_key(f"{country} {value}")] = league
        # Existing warehouse names retained as source aliases during migration.
        aliases = {
            "İngiltere EFL Championship": "İngiltere Championship",
            "İngiltere EFL League One": "İngiltere League One",
            "İngiltere EFL League Two": "İngiltere League Two",
            "ABD MLS": "ABD/Kanada Major League Soccer",
            "Çin Süper Ligi": "Çin Chinese Super League",
            "Romanya Liga I": "Romanya SuperLiga",
        }
        for source, target in aliases.items():
            if canonical_key(target) in index:
                index[canonical_key(source)] = index[canonical_key(target)]
        return index

    def query(self, date_from: str, date_to: str | None = None, league_id: str = "", country: str = "") -> list[dict]:
        date_to = date_to or date_from
        merged: dict[str, dict] = {}
        for adapter in self.registry.adapters:
            for source_row in adapter.fetch("", date_from, date_to):
                league = self._league_by_name.get(canonical_key(source_row.get("league")))
                if not league:
                    source_country = str(source_row.get("source_country") or source_row.get("country") or "").strip()
                    source_league = str(source_row.get("source_league") or "").strip()
                    league = self._league_by_name.get(canonical_key(f"{source_country} {source_league}"))
                if not league or (league_id and league["league_id"] != league_id):
                    continue
                if country and canonical_key(league["country"]) != canonical_key(country):
                    continue
                fixture = normalize_fixture(source_row, league["league_id"], adapter.source_id)
                if not fixture:
                    continue
                fixture["league"] = f"{league['country']} {league['canonical_name']}"
                identity = fixture_identity(fixture)
                if identity not in merged:
                    merged[identity] = fixture
                else:
                    for field, value in fixture.items():
                        if merged[identity].get(field) in (None, "", [], {}) and value not in (None, "", [], {}):
                            merged[identity][field] = value
                    merged[identity]["sources"] = sorted(set(merged[identity]["sources"] + fixture["sources"]))
        return sorted(merged.values(), key=lambda row: (row["date"], row.get("kickoff", ""), row["league_id"], row["home"]))

    def teams_for(self, fixtures: list[dict]) -> list[dict]:
        teams = TeamCatalog()
        for fixture in fixtures:
            league = self._league_by_id[fixture["league_id"]]
            for side in ("home", "away"):
                name = str(fixture.get(side) or "").strip()
                if not name:
                    continue
                team_id = f"{canonical_key(league['country'])}.{canonical_key(name)}"
                existing = teams.resolve(name, league["country"])
                if existing:
                    existing.league_ids.add(league["league_id"])
                else:
                    teams.add(Team(team_id, name, league["country"], {league["league_id"]}, {name}, str(fixture.get(f"{side}_logo") or "")))
        return teams.rows()

    def health(self) -> list[dict]:
        return self.registry.health()


STORE = FixtureStore()
