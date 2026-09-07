import json
import requests
from datetime import datetime, timedelta, timezone
from app import ESPN_LEAGUES

out = []
headers = {"User-Agent": "Mozilla/5.0"}
today = datetime.now(timezone.utc).date()

for offset in range(0, 8):
    d = today + timedelta(days=offset)
    ds = d.strftime("%Y%m%d")
    for code, league_name in ESPN_LEAGUES.items():
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/scoreboard?dates={ds}&limit=100"
        try:
            r = requests.get(url, timeout=12, headers=headers)
            if not r.ok:
                continue
            data = r.json()
            for event in data.get("events", []):
                comps = event.get("competitions") or []
                if not comps:
                    continue
                comp = comps[0]
                competitors = comp.get("competitors") or []
                home = next((x for x in competitors if x.get("homeAway") == "home"), None)
                away = next((x for x in competitors if x.get("homeAway") == "away"), None)
                if not home or not away:
                    continue
                ht = home.get("team", {})
                at = away.get("team", {})
                status = event.get("status", {}).get("type", {})
                out.append({
                    "event_id": event.get("id", ""),
                    "date": (event.get("date") or "")[:10],
                    "kickoff": event.get("date", ""),
                    "league": league_name,
                    "league_code": code,
                    "home": ht.get("displayName") or ht.get("name") or "",
                    "away": at.get("displayName") or at.get("name") or "",
                    "home_logo": ht.get("logo") or "",
                    "away_logo": at.get("logo") or "",
                    "status": status.get("description") or status.get("detail") or "",
                    "completed": bool(status.get("completed")),
                    "state": status.get("state") or "",
                    "referee": "",
                })
        except Exception:
            pass

out.sort(key=lambda x: (x.get("date") or "", x.get("kickoff") or "", x.get("league") or ""))
payload = {
    "ok": True,
    "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
    "matches": out,
    "count": len(out),
}
with open("data/current_fixtures.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
print("fixtures:", len(out))
