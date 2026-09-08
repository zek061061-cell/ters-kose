"""Canonical team identities shared by ingestion adapters and the UI API."""

from __future__ import annotations

from dataclasses import dataclass, field

from source_adapters import canonical_key


TEAM_ALIAS_KEYS = {
    "manutd": "manchesterunited", "manchesteru": "manchesterunited",
    "manchesterutd": "manchesterunited", "psg": "parissaintgermain",
    "intermilan": "inter", "spurs": "tottenhamhotspur",
}


def canonical_team_key(value: object) -> str:
    key = canonical_key(value)
    return TEAM_ALIAS_KEYS.get(key, key)


@dataclass
class Team:
    team_id: str
    canonical_name: str
    country: str
    league_ids: set[str] = field(default_factory=set)
    aliases: set[str] = field(default_factory=set)
    logo: str = ""

    def as_dict(self) -> dict:
        return {
            "team_id": self.team_id,
            "canonical_name": self.canonical_name,
            "aliases": sorted(self.aliases),
            "country": self.country,
            "league_ids": sorted(self.league_ids),
            "logo": self.logo,
        }


class TeamCatalog:
    def __init__(self) -> None:
        self._teams: dict[str, Team] = {}
        self._aliases: dict[tuple[str, str], str] = {}

    def add(self, team: Team) -> None:
        if not team.team_id or not team.canonical_name or not team.country:
            raise ValueError("team_id, canonical_name and country are required")
        existing = self._teams.get(team.team_id)
        if existing and existing.canonical_name != team.canonical_name:
            raise ValueError(f"team_id collision: {team.team_id}")
        team.aliases.add(team.canonical_name)
        for alias in team.aliases:
            key = (canonical_key(team.country), canonical_team_key(alias))
            owner = self._aliases.get(key)
            if owner and owner != team.team_id:
                raise ValueError(f"team alias collision: {team.country}/{alias}")
            self._aliases[key] = team.team_id
        self._teams[team.team_id] = team

    def resolve(self, name: object, country: object) -> Team | None:
        team_id = self._aliases.get((canonical_key(country), canonical_team_key(name)))
        return self._teams.get(team_id) if team_id else None

    def rows(self) -> list[dict]:
        return [team.as_dict() for team in sorted(self._teams.values(), key=lambda item: item.team_id)]
