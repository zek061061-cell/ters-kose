"""Source adapter contracts, health tracking, fallback, and fixture merging."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Iterable
import re
import unicodedata


def canonical_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char)).casefold()
    return re.sub(r"[^a-z0-9]+", "", text)


@dataclass
class SourceHealth:
    source_id: str
    healthy: bool | None = None
    last_success_at: str | None = None
    error_count: int = 0
    covered_leagues: int = 0
    last_error: str = ""


class SourceAdapter(ABC):
    """Stable boundary for legal, independently replaceable data providers."""

    source_id = "source"
    priority = 100

    def __init__(self) -> None:
        self.health = SourceHealth(self.source_id)
        self._lock = Lock()

    @abstractmethod
    def fetch_fixtures(self, league_id: str, date_from: str, date_to: str) -> list[dict]:
        raise NotImplementedError

    def fetch(self, league_id: str, date_from: str, date_to: str) -> list[dict]:
        try:
            rows = self.fetch_fixtures(league_id, date_from, date_to)
            with self._lock:
                self.health.healthy = True
                self.health.last_success_at = datetime.now(timezone.utc).isoformat()
                self.health.last_error = ""
            return rows
        except Exception as exc:
            with self._lock:
                self.health.healthy = False
                self.health.error_count += 1
                self.health.last_error = str(exc)[:240]
            return []

    def health_dict(self) -> dict:
        row = asdict(self.health)
        row["status"] = "unknown" if self.health.healthy is None else "healthy" if self.health.healthy else "error"
        return row


class AdapterRegistry:
    def __init__(self, adapters: Iterable[SourceAdapter] = ()) -> None:
        self.adapters = sorted(adapters, key=lambda adapter: adapter.priority)

    def fixtures(self, league_id: str, date_from: str, date_to: str) -> list[dict]:
        """Try all providers and merge their useful fields by canonical identity."""
        merged: dict[str, dict] = {}
        for adapter in self.adapters:
            for raw in adapter.fetch(league_id, date_from, date_to):
                fixture = normalize_fixture(raw, league_id, adapter.source_id)
                if fixture is None:
                    continue
                key = fixture_identity(fixture)
                if key not in merged:
                    merged[key] = fixture
                else:
                    for field, value in fixture.items():
                        if merged[key].get(field) in (None, "", [], {}) and value not in (None, "", [], {}):
                            merged[key][field] = value
                    merged[key]["sources"] = sorted(set(merged[key]["sources"] + fixture["sources"]))
        return sorted(merged.values(), key=lambda row: (row["date"], row.get("kickoff", ""), row["home"]))

    def health(self) -> list[dict]:
        return [adapter.health_dict() for adapter in self.adapters]


def fixture_identity(fixture: dict) -> str:
    return "|".join((fixture["date"], fixture["league_id"], canonical_key(fixture["home"]), canonical_key(fixture["away"])))


def normalize_fixture(raw: dict, league_id: str, source_id: str) -> dict | None:
    date = str(raw.get("date") or "").strip()[:10]
    home = str(raw.get("home") or "").strip()
    away = str(raw.get("away") or "").strip()
    if len(date) != 10 or not home or not away or canonical_key(home) == canonical_key(away):
        return None
    completed = bool(raw.get("completed"))
    row = dict(raw)
    row.update({
        "date": date, "league_id": league_id, "home": home, "away": away,
        "completed": completed, "sources": [source_id],
    })
    for field in ("ht_home", "ht_away", "ft_home", "ft_away"):
        value = raw.get(field)
        row[field] = int(value) if completed and value not in (None, "") else None
    return row
