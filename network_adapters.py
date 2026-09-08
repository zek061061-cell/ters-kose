"""Legal public HTTP adapters used by the v7 ingestion job.

These adapters never bypass access controls. HTTP/parse failures are captured
by SourceAdapter health and allow the next configured provider to run.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

import requests
from bs4 import BeautifulSoup
import re

from source_adapters import SourceAdapter


class EspnAdapter(SourceAdapter):
    source_id = "espn"
    priority = 30

    def __init__(self, competition_ids: dict[str, str], timeout: int = 20) -> None:
        super().__init__()
        self.competition_ids = competition_ids
        self.timeout = timeout

    def fetch_fixtures(self, league_id: str, date_from: str, date_to: str) -> list[dict]:
        code = self.competition_ids[league_id]
        dates = date_from.replace("-", "") + "-" + date_to.replace("-", "")
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/scoreboard?dates={dates}&limit=1000"
        response = requests.get(url, timeout=self.timeout, headers={"User-Agent": "TersKose/7.0", "Accept": "application/json"})
        response.raise_for_status()
        rows = []
        for event in response.json().get("events", []):
            competition = next(iter(event.get("competitions") or []), {})
            competitors = competition.get("competitors") or []
            home = next((item for item in competitors if item.get("homeAway") == "home"), None)
            away = next((item for item in competitors if item.get("homeAway") == "away"), None)
            if not home or not away:
                continue
            state = (event.get("status") or {}).get("type") or {}
            completed = bool(state.get("completed") or state.get("state") == "post")
            home_team, away_team = home.get("team") or {}, away.get("team") or {}
            row = {
                "event_id": f"ESPN|{code}|{event.get('id', '')}", "date": str(event.get("date") or "")[:10],
                "kickoff": event.get("date") or "", "league_id": league_id,
                "home": home_team.get("displayName") or home_team.get("name") or "",
                "away": away_team.get("displayName") or away_team.get("name") or "",
                "home_logo": home_team.get("logo") or "", "away_logo": away_team.get("logo") or "",
                "completed": completed, "state": state.get("state") or "pre",
                "week": (event.get("week") or {}).get("number") or competition.get("round") or 0,
                "season": str((event.get("season") or {}).get("year") or ""),
                "ft_home": home.get("score") if completed else None,
                "ft_away": away.get("score") if completed else None,
                "ht_home": _period_score(home, 1), "ht_away": _period_score(away, 1),
                "source": "ESPN public scoreboard", "source_url": url,
            }
            rows.append(row)
        return rows


class FootballDataCsvAdapter(SourceAdapter):
    source_id = "football-data"
    priority = 20

    def __init__(self, csv_urls: dict[str, str], timeout: int = 20) -> None:
        super().__init__()
        self.csv_urls = csv_urls
        self.timeout = timeout

    def fetch_fixtures(self, league_id: str, date_from: str, date_to: str) -> list[dict]:
        url = self.csv_urls[league_id]
        response = requests.get(url, timeout=self.timeout, headers={"User-Agent": "TersKose/7.0", "Accept": "text/csv"})
        response.raise_for_status()
        output = []
        for raw in csv.DictReader(io.StringIO(response.content.decode("utf-8-sig", "replace"))):
            match_date = _date(raw.get("Date"))
            if not match_date or not date_from <= match_date <= date_to:
                continue
            completed = raw.get("FTHG") not in (None, "") and raw.get("FTAG") not in (None, "")
            output.append({
                "event_id": f"FD|{league_id}|{match_date}|{raw.get('HomeTeam')}|{raw.get('AwayTeam')}",
                "date": match_date, "kickoff": f"{match_date}T{raw.get('Time')}:00" if raw.get("Time") else match_date,
                "league_id": league_id, "home": raw.get("HomeTeam") or "", "away": raw.get("AwayTeam") or "",
                "completed": completed, "ft_home": raw.get("FTHG"), "ft_away": raw.get("FTAG"),
                "ht_home": raw.get("HTHG"), "ht_away": raw.get("HTAG"), "week": raw.get("MW") or 0,
                "source": "Football-Data CSV", "source_url": url,
            })
        return output


class TffAdapter(SourceAdapter):
    source_id = "tff"
    priority = 5

    def __init__(self, page_templates: dict[str, str], weeks: range = range(1, 45), timeout: int = 20) -> None:
        super().__init__()
        self.page_templates, self.weeks, self.timeout = page_templates, weeks, timeout

    def fetch_fixtures(self, league_id: str, date_from: str, date_to: str) -> list[dict]:
        template, output = self.page_templates[league_id], []
        for week in self.weeks:
            url = template.format(week=week)
            response = requests.get(url, timeout=self.timeout, headers={"User-Agent": "TersKose/7.0"})
            response.raise_for_status()
            text = "\n".join(BeautifulSoup(response.text, "html.parser").stripped_strings)
            for match in re.finditer(r"(\d{2}\.\d{2}\.20\d{2})(?:\s+(\d{1,2}:\d{2}))?\s+([^\n]+?)\s+-\s+([^\n]+?)(?=\s+Detaylar|\n|$)", text):
                raw_date, kickoff, home, away = match.groups()
                match_date = datetime.strptime(raw_date, "%d.%m.%Y").strftime("%Y-%m-%d")
                if date_from <= match_date <= date_to:
                    output.append({
                        "event_id": f"TFF|{league_id}|{week}|{match_date}|{home}|{away}",
                        "league_id": league_id, "date": match_date,
                        "kickoff": f"{match_date}T{kickoff}:00+03:00" if kickoff else match_date,
                        "home": home.strip(), "away": away.strip(), "week": week,
                        "completed": False, "source": "TFF official", "source_url": url,
                    })
        return output


class SahadanAdapter(SourceAdapter):
    source_id = "sahadan"
    priority = 10

    def __init__(self, fixture_urls: dict[str, str], timeout: int = 20) -> None:
        super().__init__()
        self.fixture_urls, self.timeout = fixture_urls, timeout

    def fetch_fixtures(self, league_id: str, date_from: str, date_to: str) -> list[dict]:
        url = self.fixture_urls[league_id]
        response = requests.get(url, timeout=self.timeout, headers={"User-Agent": "Mozilla/5.0 (compatible; TersKose/7.0)"})
        response.raise_for_status()
        soup, output = BeautifulSoup(response.text, "html.parser"), []
        for node in soup.select("[data-match-id], [data-event-id], .match-row, .fixture"):
            home_node = node.select_one("[data-home-team], .home-team, .team-home")
            away_node = node.select_one("[data-away-team], .away-team, .team-away")
            date_node = node.select_one("time, [data-date], .match-date")
            home = (home_node.get("data-home-team") if home_node else "") or (home_node.get_text(" ", strip=True) if home_node else "")
            away = (away_node.get("data-away-team") if away_node else "") or (away_node.get_text(" ", strip=True) if away_node else "")
            raw_date = ((date_node.get("datetime") or date_node.get("data-date")) if date_node else "") or (date_node.get_text(" ", strip=True) if date_node else "")
            match_date = _date(raw_date[:10])
            if home and away and match_date and date_from <= match_date <= date_to:
                output.append({
                    "event_id": str(node.get("data-match-id") or node.get("data-event-id") or f"{match_date}|{home}|{away}"),
                    "league_id": league_id, "date": match_date, "kickoff": raw_date,
                    "home": home, "away": away, "completed": False,
                    "source": "Sahadan fixture page", "source_url": url,
                })
        return output


def _date(value: object) -> str:
    for pattern in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value or ""), pattern).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return ""


def _period_score(competitor: dict, period: int) -> int | None:
    for line in competitor.get("linescores") or []:
        if int(line.get("period") or 0) == period and str(line.get("value") or "") != "":
            return int(float(line["value"]))
    return None
