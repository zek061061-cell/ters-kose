import json, re, time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

OUT="data/future_fixtures.json"
BASE="https://www.sahadan.com"
HEADERS={
  "User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1",
  "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
  "Accept-Language":"tr-TR,tr;q=0.9,en;q=0.7",
  "Referer":BASE+"/",
}

# Verified Sahadan competition pages.
LEAGUES={
 "Türkiye Süper Lig":"https://www.sahadan.com/lig/trendyol-super-lig/482ofyysbdbeoxauk19yg7tdt/fikstur",
 "İngiltere Premier League":"https://www.sahadan.com/lig/premier-lig/2kwbbcootiqqgmrzs6o5inle5/fikstur",
 "İtalya Serie A":"https://www.sahadan.com/lig/serie-a/1r097lpxe0xn03ihb7wi98kao/fikstur",
 "Almanya Bundesliga":"https://www.sahadan.com/lig/bundesliga/6by3h89i2eykc341oz7lv1ddd/fikstur",
 "Fransa Ligue 1":"https://www.sahadan.com/lig/ligue-1/dm5ka0os1e3dxcp3vh05kmp33/fikstur",
 "Hollanda Eredivisie":"https://www.sahadan.com/lig/eredivisie/akmkihra9ruad09ljapsm84b3/fikstur",
 "ABD MLS":"https://www.sahadan.com/lig/mls/287tckirbfj9nb8ar2k9r60vn/fikstur",
 "İskoçya Premiership":"https://www.sahadan.com/lig/premiership/e21cf135btr8t3upw0vl6n6x0/fikstur",
}
TR_MONTHS={"Ocak":1,"Şubat":2,"Mart":3,"Nisan":4,"Mayıs":5,"Haziran":6,"Temmuz":7,"Ağustos":8,"Eylül":9,"Ekim":10,"Kasım":11,"Aralık":12}
now=datetime.now(ZoneInfo("Europe/Istanbul"))

def fetch(url):
    last=None
    for attempt in range(4):
        try:
            r=requests.get(url,headers=HEADERS,timeout=30)
            if r.ok and r.text:return r.text
            last=RuntimeError(f"HTTP {r.status_code}")
        except Exception as e:last=e
        time.sleep(1.5*(attempt+1))
    raise last or RuntimeError("fetch failed")

def parse_date(text,year_hint):
    m=re.search(r"(\d{1,2})\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)(?:\s+(20\d{2}))?",text)
    if not m:return ""
    d,mon,y=m.groups(); y=int(y or year_hint)
    month=TR_MONTHS[mon]
    # season pages cross New Year: dates Jan-Jun after an Aug-Dec current date are next year.
    if not m.group(3) and month < 7 and now.month >= 7:y=year_hint+1
    return f"{y:04d}-{month:02d}-{int(d):02d}"

rows=[]
diag={}
for league,url in LEAGUES.items():
    try:
        html=fetch(url)
        soup=BeautifulSoup(html,"html.parser")
        text=soup.get_text("\n",strip=True)
        # The page exposes upcoming match anchors. Parse only anchors that contain a
        # time but not a completed score marker.
        current_date=""
        found=[]
        for el in soup.find_all(["div","span","a","li","tr"]):
            t=" ".join(el.get_text(" ",strip=True).split())
            if not t:continue
            d=parse_date(t,now.year)
            if d and len(t)<45:
                current_date=d
            if el.name!="a":continue
            mt=re.search(r"(?<!\d)(\d{1,2}:\d{2})\s+(.+?)\s+-\s+(.+?)(?:\s*$)",t)
            if not mt:continue
            hm,home,away=mt.groups()
            if not current_date:
                # compact preview uses DD/MM at the beginning
                md=re.match(r"(\d{2})/(\d{2})\s+",t)
                if md:
                    dd,mm=map(int,md.groups()); y=now.year+(1 if mm<7 and now.month>=7 else 0)
                    current_date=f"{y:04d}-{mm:02d}-{dd:02d}"
            if not current_date:continue
            kickoff=current_date+"T"+hm+":00+03:00"
            try:
                dt=datetime.fromisoformat(kickoff)
                if dt < now:continue
            except Exception:pass
            href=urljoin(BASE,el.get("href") or "")
            found.append({
              "event_id":href or "|".join([current_date,league,home,away]),
              "date":current_date,"kickoff":kickoff,"league":league,"league_code":"SAHADAN",
              "home":home.strip(),"away":away.strip(),"home_logo":"","away_logo":"","status":"Planlandı",
              "completed":False,"state":"pre","referee":"","source":"Sahadan lig fikstürü","source_url":href or url
            })
        diag[league]=len(found)
        rows.extend(found)
    except Exception as e:
        diag[league]=f"error:{e}"

# Keep the rolling Sahadan İddaa snapshot too; it covers additional leagues.
try:
    with open("data/current_fixtures.json","r",encoding="utf-8") as f:cur=json.load(f)
    rows.extend([x for x in cur.get("matches",[]) if not x.get("completed")])
except Exception:pass

seen=set();clean=[]
for x in rows:
    k="|".join([str(x.get("date") or ""),str(x.get("league") or ""),str(x.get("home") or ""),str(x.get("away") or "")])
    if k in seen:continue
    seen.add(k);clean.append(x)
clean.sort(key=lambda x:(x.get("date") or "",x.get("kickoff") or "",x.get("league") or "",x.get("home") or ""))

payload={"ok":True,"generated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"source":"Sahadan lig fikstürleri + İddaa Programı","count":len(clean),"league_counts":diag,"matches":clean}
with open(OUT,"w",encoding="utf-8") as f:json.dump(payload,f,ensure_ascii=False,separators=(",",":"))
print("future fixtures:",len(clean))
print("league counts:",json.dumps(diag,ensure_ascii=False))
print("sample:",json.dumps(clean[:12],ensure_ascii=False))
