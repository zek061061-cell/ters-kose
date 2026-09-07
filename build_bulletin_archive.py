import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HISTORY="data/history_10y.json"
CURRENT="data/current_fixtures.json"
ARCHIVE="data/bulletin_1y.json"

today=datetime.now(ZoneInfo("Europe/Istanbul")).date()
cutoff=today-timedelta(days=365)

with open(HISTORY,"r",encoding="utf-8") as f:
    history=json.load(f)

rows=[]
for r in history:
    d=str(r.get("date") or "")
    try:
        dd=datetime.strptime(d,"%Y-%m-%d").date()
    except Exception:
        continue
    if cutoff <= dd <= today:
        rows.append({
            "event_id":"hist|"+"|".join([d,str(r.get("league") or ""),str(r.get("home") or ""),str(r.get("away") or "")]),
            "date":d,
            "kickoff":d,
            "league":r.get("league") or "",
            "league_code":"HISTORY",
            "home":r.get("home") or "",
            "away":r.get("away") or "",
            "home_logo":"",
            "away_logo":"",
            "status":"Tamamlandı",
            "completed":True,
            "state":"post",
            "referee":"",
            "source":"Ters Köşe doğrulanmış tarihsel depo",
            "ft_home":r.get("ft_home"),
            "ft_away":r.get("ft_away"),
            "ht_home":r.get("ht_home"),
            "ht_away":r.get("ht_away"),
            "week":r.get("week"),
            "season":r.get("season"),
        })

# Preserve previously accumulated Sahadan/current snapshots.
if os.path.exists(ARCHIVE):
    try:
        with open(ARCHIVE,"r",encoding="utf-8") as f:
            old=json.load(f)
        for x in old.get("matches",[]):
            d=str(x.get("date") or "")
            try:
                dd=datetime.strptime(d,"%Y-%m-%d").date()
            except Exception:
                continue
            if dd >= cutoff and str(x.get("source") or "").lower().startswith("sahadan"):
                rows.append(x)
    except Exception:
        pass

# Add the latest Sahadan snapshot.
if os.path.exists(CURRENT):
    try:
        with open(CURRENT,"r",encoding="utf-8") as f:
            cur=json.load(f)
        for x in cur.get("matches",[]):
            y=dict(x)
            y["source"]=cur.get("source") or y.get("source") or "Sahadan"
            rows.append(y)
    except Exception:
        pass

# Dedupe: prefer Sahadan/current rows over generic history for the same fixture.
m={}
def richness(x):
    score=0
    if str(x.get("source") or "").lower().startswith("sahadan"): score+=20
    if x.get("kickoff") and "T" in str(x.get("kickoff")): score+=3
    if x.get("ht_home") is not None: score+=2
    if x.get("ft_home") is not None: score+=2
    return score

for x in rows:
    key="|".join([str(x.get("date") or ""),str(x.get("league") or ""),str(x.get("home") or ""),str(x.get("away") or "")])
    old=m.get(key)
    if old is None or richness(x)>richness(old):
        m[key]=x

clean=list(m.values())
clean.sort(key=lambda x:(str(x.get("date") or ""),str(x.get("kickoff") or ""),str(x.get("league") or ""),str(x.get("home") or "")))

payload={
    "ok":True,
    "generated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
    "from":cutoff.isoformat(),
    "to":today.isoformat(),
    "matches":clean,
    "count":len(clean),
    "sahadan_count":sum(1 for x in clean if str(x.get("source") or "").lower().startswith("sahadan")),
}
with open(ARCHIVE,"w",encoding="utf-8") as f:
    json.dump(payload,f,ensure_ascii=False,separators=(",",":"))
print("bulletin archive:",payload["count"],"sahadan:",payload["sahadan_count"])
