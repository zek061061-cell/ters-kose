import csv
import io
import json
from datetime import datetime, timezone
import requests
from app import MAIN_HISTORY_LEAGUES, _date

url = "https://www.football-data.co.uk/matches/resources/fixtures.csv"
headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/csv,text/plain,*/*",
    "Referer": "https://www.football-data.co.uk/",
}
r = requests.get(url, timeout=30, headers=headers)
r.raise_for_status()
text = r.content.decode("utf-8-sig", errors="replace")
reader = csv.DictReader(io.StringIO(text))
out = []

for row in reader:
    code = str(row.get("Div") or row.get("div") or "").strip()
    league = MAIN_HISTORY_LEAGUES.get(code)
    if not league:
        continue
    home = str(row.get("HomeTeam") or row.get("Home") or "").strip()
    away = str(row.get("AwayTeam") or row.get("Away") or "").strip()
    if not home or not away:
        continue
    date = _date(row.get("Date"))
    if not date:
        continue
    tm = str(row.get("Time") or "").strip()
    kickoff = date + (("T" + tm + ":00") if tm and ":" in tm else "")
    out.append({
        "event_id": "|".join([date, code, home, away]),
        "date": date,
        "kickoff": kickoff,
        "league": league,
        "league_code": code,
        "home": home,
        "away": away,
        "home_logo": "",
        "away_logo": "",
        "status": "Planlandı",
        "completed": False,
        "state": "pre",
        "referee": str(row.get("Referee") or "").strip(),
    })

seen = set()
clean = []
for x in out:
    k = x["event_id"]
    if k in seen:
        continue
    seen.add(k)
    clean.append(x)

clean.sort(key=lambda x: (x["date"], x.get("kickoff") or "", x["league"], x["home"]))
payload = {
    "ok": True,
    "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
    "source": "football-data fixtures.csv",
    "matches": clean,
    "count": len(clean),
}
with open("data/current_fixtures.json", "w", encoding="utf-8") as h:
    json.dump(payload, h, ensure_ascii=False, separators=(",", ":"))
print("fixtures:", len(clean))
