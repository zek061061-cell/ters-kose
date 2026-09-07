import json, os, time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from app import ESPN_LEAGUES

OUT="data/future_fixtures.json"
today=datetime.now(timezone.utc).date()
end=today+timedelta(days=300)
headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}

def fetch_league(item):
    code,league=item
    url=f"https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/scoreboard?dates={today.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}&limit=1000"
    try:
        r=requests.get(url,headers=headers,timeout=25)
        if not r.ok:return []
        data=r.json(); out=[]
        for ev in data.get("events",[]):
            comp=(ev.get("competitions") or [{}])[0]
            cs=comp.get("competitors") or []
            home=next((x for x in cs if x.get("homeAway")=="home"),None)
            away=next((x for x in cs if x.get("homeAway")=="away"),None)
            if not home or not away:continue
            st=(ev.get("status") or {}).get("type") or {}
            if st.get("completed"):continue
            ht=home.get("team") or {}; at=away.get("team") or {}
            date=(ev.get("date") or "")[:10]
            if not date:continue
            out.append({"event_id":ev.get("id",""),"date":date,"kickoff":ev.get("date",""),"league":league,"league_code":code,
              "home":ht.get("displayName") or ht.get("name") or "","away":at.get("displayName") or at.get("name") or "",
              "home_logo":ht.get("logo") or "","away_logo":at.get("logo") or "","status":st.get("description") or "Planlandı",
              "completed":False,"state":"pre","referee":"","source":"ESPN sezon fikstürü"})
        return out
    except Exception:return []

rows=[]
with ThreadPoolExecutor(max_workers=12) as ex:
    fs=[ex.submit(fetch_league,x) for x in ESPN_LEAGUES.items()]
    for f in as_completed(fs): rows.extend(f.result())

seen=set(); clean=[]
for x in rows:
    k=x.get("event_id") or "|".join([x["date"],x["league"],x["home"],x["away"]])
    if k in seen:continue
    seen.add(k); clean.append(x)
clean.sort(key=lambda x:(x["date"],x["league"],x["home"]))
payload={"ok":True,"generated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"from":today.isoformat(),"to":end.isoformat(),"count":len(clean),"matches":clean}
with open(OUT,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False,separators=(",",":"))
print("future fixtures:",len(clean),"leagues:",len(set(x["league"] for x in clean)))
