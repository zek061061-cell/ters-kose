import csv
import io
import json
import os
import time
from datetime import datetime, timezone
import requests
from app import MAIN_HISTORY_LEAGUES, _date

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36",
    "Accept": "text/csv,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.football-data.co.uk/",
    "Connection": "close",
}
content = None
last_error = None
for host in ("www.football-data.co.uk", "football-data.co.uk"):
    url = f"https://{host}/matches/resources/fixtures.csv"
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=30, headers=headers, allow_redirects=True)
            if r.ok and r.content:
                content = r.content
                break
            last_error = RuntimeError(f"{r.status_code} from {host}")
        except Exception as e:
            last_error = e
        time.sleep(1.2 * (attempt + 1))
    if content:
        break

if not content:
    # Do not overwrite a previously good snapshot with an empty one.
    if os.path.exists("data/current_fixtures.json"):
        with open("data/current_fixtures.json", "r", encoding="utf-8") as h:
            old = json.load(h)
        if int(old.get("count") or 0) > 0:
            print("fixture source unavailable; preserving previous snapshot:", old.get("count"))
            raise SystemExit(0)
    raise RuntimeError(f"fixture source unavailable: {last_error}")

text = content.decode("utf-8-sig", errors="replace")
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
    if x["event_id"] in seen:
        continue
    seen.add(x["event_id"])
    clean.append(x)
clean.sort(key=lambda x: (x["date"], x.get("kickoff") or "", x["league"], x["home"]))

if not clean:
    if os.path.exists("data/current_fixtures.json"):
        with open("data/current_fixtures.json", "r", encoding="utf-8") as h:
            old = json.load(h)
        if int(old.get("count") or 0) > 0:
            print("new snapshot empty; preserving previous snapshot:", old.get("count"))
            raise SystemExit(0)

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
