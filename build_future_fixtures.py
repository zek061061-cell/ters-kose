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
 
 "İngiltere Premier League":"https://www.sahadan.com/lig/premier-lig/2kwbbcootiqqgmrzs6o5inle5/fikstur",
 "İtalya Serie A":"https://www.sahadan.com/lig/serie-a/1r097lpxe0xn03ihb7wi98kao/fikstur",
 "Almanya Bundesliga":"https://www.sahadan.com/lig/bundesliga/6by3h89i2eykc341oz7lv1ddd/fikstur",
 "Fransa Ligue 1":"https://www.sahadan.com/lig/ligue-1/dm5ka0os1e3dxcp3vh05kmp33/fikstur",
 "Hollanda Eredivisie":"https://www.sahadan.com/lig/eredivisie/akmkihra9ruad09ljapsm84b3/fikstur",
 "ABD MLS":"https://www.sahadan.com/lig/mls/287tckirbfj9nb8ar2k9r60vn/fikstur",
 "İskoçya Premiership":"https://www.sahadan.com/lig/premiership/e21cf135btr8t3upw0vl6n6x0/fikstur",
 "İngiltere EFL Championship":"https://www.sahadan.com/lig/championship/7ntvbsyq31jnzoqoa8850b9b8/fikstur",
 "İngiltere EFL League One":"https://www.sahadan.com/lig/1-lig/3frp1zxrqulrlrnk503n6l4l/fikstur",
 "İtalya Serie B":"https://www.sahadan.com/lig/serie-b/8ey0ww2zsosdmwr8ehsorh6t7/fikstur",
 "İspanya La Liga":"https://www.sahadan.com/lig/laliga/34pl8szyvrbwcmfkuocjm3r6t/fikstur",
 "İspanya LaLiga 2":"https://www.sahadan.com/lig/laliga-2/3is4bkgf3loxv9qfg3hm8zfqb/fikstur",
 "Norveç Eliteserien":"https://www.sahadan.com/lig/eliteserien/9ynnnx1qmkizq1o3qr3v0nsuk/fikstur",
 "İsveç Allsvenskan":"https://www.sahadan.com/lig/allsvenskan/b60nisd3qn427jm0hrg9kvmab/fikstur",
}
TR_MONTHS={"Ocak":1,"Şubat":2,"Mart":3,"Nisan":4,"Mayıs":5,"Haziran":6,"Temmuz":7,"Ağustos":8,"Eylül":9,"Ekim":10,"Kasım":11,"Aralık":12}
now=datetime.now(ZoneInfo("Europe/Istanbul"))

def slugify(v):
    import unicodedata
    v=str(v or "").strip().casefold()
    v=v.replace("ı","i").replace("ş","s").replace("ğ","g").replace("ü","u").replace("ö","o").replace("ç","c")
    v=unicodedata.normalize("NFKD",v)
    v="".join(ch for ch in v if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+","-",v).strip("-")

TEAM_LOOKUP={}
try:
    with open("data/history_10y.json","r",encoding="utf-8") as hf:
        hist=json.load(hf)
    for r in hist:
        for t in (r.get("home"),r.get("away")):
            t=str(t or "").strip()
            if t: TEAM_LOOKUP[slugify(t)]=t
except Exception:
    pass

def resolve_slug_team(slug):
    if slug in TEAM_LOOKUP:return TEAM_LOOKUP[slug]
    simple=re.sub(r"-(fc|fk|sk|cf|ac|if)$","",slug)
    for k,v in TEAM_LOOKUP.items():
        ks=re.sub(r"-(fc|fk|sk|cf|ac|if)$","",k)
        if ks==simple:return v
    return slug.replace("-"," ").title()

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
            mt=re.search(r"(?<!\d)(\d{1,2}:\d{2})\s+(.+?)\s+-\s+(.+?)(?:\s*$)",t)
            if not mt:continue
            hm,home,away=mt.groups()
            # Some Sahadan fixture pages expose match rows as non-anchor containers.
            # Use an embedded match link when present; otherwise keep the parsed row.
            link=el if el.name=="a" else el.find("a",href=True)
            href=urljoin(BASE,(link.get("href") if link else "") or "")
            try:
                match_slug=href.split("/mac/",1)[1].split("/",1)[0]
                if "-v-" in match_slug:
                    hs,as_=match_slug.split("-v-",1)
                    home,away=resolve_slug_team(hs),resolve_slug_team(as_)
                elif "-vs-" in match_slug:
                    hs,as_=match_slug.split("-vs-",1)
                    home,away=resolve_slug_team(hs),resolve_slug_team(as_)
            except Exception:
                home=re.sub(r"^\d+\s+Ligde\s+\d+\.sırada\s+","",home).strip()
                away=re.sub(r"\s+\d+\s+Ligde\s+\d+\.sırada\s*-?$","",away).strip()
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
            found.append({
              "event_id":href or "|".join([current_date,league,home,away]),
              "date":current_date,"kickoff":kickoff,"league":league,"league_code":"SAHADAN",
              "home":home.strip(),"away":away.strip(),"home_logo":"","away_logo":"","status":"Planlandı",
              "completed":False,"state":"pre","referee":"","source":"Sahadan lig fikstürü","source_url":href or url
            })
        # Fallback: some Sahadan league pages render fixtures as plain text
        # rather than match anchors. Parse date sections and HH:MM Team - Team rows.
        if not found:
            flat="\n".join(soup.stripped_strings)
            date_pat=r"(\d{1,2})\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\s+(20\d{2})"
            parts=list(re.finditer(date_pat,flat))
            for idx,mdate in enumerate(parts):
                start=mdate.end(); endpos=parts[idx+1].start() if idx+1<len(parts) else len(flat)
                section=flat[start:endpos]
                dd,mon,yy=mdate.groups()
                d=f"{int(yy):04d}-{TR_MONTHS[mon]:02d}-{int(dd):02d}"
                for mm in re.finditer(r"(?<!\d)([0-2]?\d:[0-5]\d)\s+([^\n]+?)\s+-\s+([^\n]+?)(?=(?:\d{1,2}:\d{2})|MS|$)",section):
                    hm,home,away=mm.groups()
                    # remove ranking/stat fragments that sometimes trail team names
                    home=re.sub(r"^\d+\s+Ligde\s+\d+\.sırada\s+","",home).strip()
                    away=re.sub(r"\s+\d+\s+Ligde\s+\d+\.sırada.*$","",away).strip()
                    home=resolve_slug_team(slugify(home))
                    away=resolve_slug_team(slugify(away))
                    kickoff=d+"T"+hm+":00+03:00"
                    try:
                        if datetime.fromisoformat(kickoff)<now: continue
                    except Exception: pass
                    found.append({
                      "event_id":"text|"+"|".join([d,league,home,away]),
                      "date":d,"kickoff":kickoff,"league":league,"league_code":"SAHADAN",
                      "home":home,"away":away,"home_logo":"","away_logo":"","status":"Planlandı",
                      "completed":False,"state":"pre","referee":"","source":"Sahadan lig fikstürü","source_url":url
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
