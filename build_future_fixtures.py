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
 "Almanya 2. Bundesliga":"https://www.sahadan.com/lig/2-bundesliga/722fdbecxzcq9788l6jqclzlw/fikstur",
 "Fransa Ligue 2":"https://www.sahadan.com/lig/ligue-2/4w7x0s5gfs5abasphlha5de8k/fikstur",
 "İskoçya Championship":"https://www.sahadan.com/lig/championship/8t2o4huu2e48ij23dxnl9w5qx/fikstur",
 "Polonya Ekstraklasa":"https://www.sahadan.com/lig/ekstraklasa/7hl0svs2hg225i2zud0g3xzp2/fikstur",
 "Avusturya Bundesliga":"https://www.sahadan.com/lig/bundesliga/5c96g1zm7vo5ons9c42uy2w3r/fikstur",
 "Belçika Pro League":"https://www.sahadan.com/lig/pro-lig/4zwgbb66rif2spcoeeol2motx/fikstur",
 "Finlandiya Veikkausliiga":"https://www.sahadan.com/lig/veikkausliiga/dvstmwnvw0mt5p38twn9yttyb/fikstur",
 "Danimarka Superliga":"https://www.sahadan.com/lig/superliga/29actv1ohj8r10kd9hu0jnb0n/fikstur",
 "İsviçre Super League":"https://www.sahadan.com/lig/super-league/e0lck99w8meo9qoalfrxgo33o/fikstur",
 "Brezilya Série A":"https://www.sahadan.com/lig/serie-a/scf9p4y91yjvqvg5jndxzhxj/fikstur",
 "Meksika Liga MX":"https://www.sahadan.com/lig/liga-mx/2hsidwomhjsaaytdy9u5niyi4/fikstur",
 "Çin Süper Ligi":"https://www.sahadan.com/lig/super-lig/82jkgccg7phfjpd0mltdl3pat/fikstur",
 "Rusya Premier League":"https://www.sahadan.com/en/league/premier-league/3ab1uwtoyjopdj1y1fynyy9jg/fixtures",
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
EN_MONTHS={"January":1,"February":2,"March":3,"April":4,"May":5,"June":6,"July":7,"August":8,"September":9,"October":10,"November":11,"December":12}
ALL_MONTHS={**TR_MONTHS,**EN_MONTHS}
now=datetime.now(ZoneInfo("Europe/Istanbul"))

# Exact 35-league catalogue used by the historical warehouse. ESPN is a
# fallback/coverage source; Sahadan/TFF rows still win when both sources have
# the same fixture.
ESPN_35={
 "tur.1":"Türkiye Süper Lig",
 "eng.1":"İngiltere Premier League","eng.2":"İngiltere EFL Championship","eng.3":"İngiltere EFL League One","eng.4":"İngiltere EFL League Two",
 "sco.1":"İskoçya Premiership","sco.2":"İskoçya Championship",
 "ger.1":"Almanya Bundesliga","ger.2":"Almanya 2. Bundesliga",
 "esp.1":"İspanya La Liga","esp.2":"İspanya LaLiga 2",
 "ita.1":"İtalya Serie A","ita.2":"İtalya Serie B",
 "fra.1":"Fransa Ligue 1","fra.2":"Fransa Ligue 2",
 "ned.1":"Hollanda Eredivisie","bel.1":"Belçika Pro League","por.1":"Portekiz Primeira Liga","gre.1":"Yunanistan Super League",
 "arg.1":"Arjantin Primera División","aut.1":"Avusturya Bundesliga","bra.1":"Brezilya Série A","chn.1":"Çin Süper Ligi",
 "den.1":"Danimarka Superliga","fin.1":"Finlandiya Veikkausliiga","irl.1":"İrlanda Premier Division","jpn.1":"Japonya J1 League",
 "mex.1":"Meksika Liga MX","nor.1":"Norveç Eliteserien","pol.1":"Polonya Ekstraklasa","rou.1":"Romanya Liga I",
 "rus.1":"Rusya Premier League","swe.1":"İsveç Allsvenskan","sui.1":"İsviçre Super League","usa.1":"ABD MLS",
}
WAREHOUSE_35=set(ESPN_35.values())

FOOTBALL_DATA_CODES={
 "T1":"Türkiye Süper Lig","E0":"İngiltere Premier League","E1":"İngiltere EFL Championship","E2":"İngiltere EFL League One","E3":"İngiltere EFL League Two",
 "SC0":"İskoçya Premiership","SC1":"İskoçya Championship","D1":"Almanya Bundesliga","D2":"Almanya 2. Bundesliga",
 "SP1":"İspanya La Liga","SP2":"İspanya LaLiga 2","I1":"İtalya Serie A","I2":"İtalya Serie B","F1":"Fransa Ligue 1","F2":"Fransa Ligue 2",
 "N1":"Hollanda Eredivisie","B1":"Belçika Pro League","P1":"Portekiz Primeira Liga","G1":"Yunanistan Super League"
}

def fetch_football_data_fixtures():
    """Current/future domestic fixtures for the 19 Football-Data leagues."""
    import csv, io
    url="https://www.football-data.co.uk/matches/resources/fixtures.csv"
    try:
        r=requests.get(url,headers={"User-Agent":HEADERS["User-Agent"],"Accept":"text/csv,*/*"},timeout=30)
        if not r.ok:return [],{"_error":f"HTTP {r.status_code}"}
        text=r.content.decode("utf-8-sig","replace")
        rows=[];counts={k:0 for k in FOOTBALL_DATA_CODES.values()}
        for rec in csv.DictReader(io.StringIO(text)):
            code=str(rec.get("Div") or "").strip()
            league=FOOTBALL_DATA_CODES.get(code)
            if not league:continue
            ds=str(rec.get("Date") or "").strip()
            try:d=datetime.strptime(ds,"%d/%m/%Y").strftime("%Y-%m-%d")
            except Exception:
                try:d=datetime.strptime(ds,"%d/%m/%y").strftime("%Y-%m-%d")
                except Exception:continue
            if d < now.date().isoformat():continue
            home=str(rec.get("HomeTeam") or "").strip();away=str(rec.get("AwayTeam") or "").strip()
            if not home or not away:continue
            hm=str(rec.get("Time") or "").strip()
            kickoff=d+(("T"+hm+":00+03:00") if re.match(r"^\d{1,2}:\d{2}$",hm) else "")
            rows.append({
              "event_id":"FD|"+code+"|"+"|".join([d,home,away]),"date":d,"kickoff":kickoff,
              "league":league,"league_code":code,"home":resolve_slug_team(slugify(home)),"away":resolve_slug_team(slugify(away)),
              "home_logo":"","away_logo":"","status":"Planlandı","completed":False,"state":"pre","referee":"",
              "source":"Football-Data güncel fikstür","source_url":url
            });counts[league]=counts.get(league,0)+1
        return rows,counts
    except Exception as e:
        return [],{"_error":repr(e)}

def fetch_espn_35():
    """Fetch season/range fixtures for the same 35 leagues as the model warehouse.
    ESPN accepts a date range on scoreboard endpoints for many competitions.
    Leagues that do not expose the full range simply contribute zero rows and
    remain covered by Sahadan/TFF/current-snapshot fallbacks.
    """
    from datetime import timedelta
    start=now.date()
    end=(now+timedelta(days=370)).date()
    date_range=start.strftime("%Y%m%d")+"-"+end.strftime("%Y%m%d")
    out=[]; counts={}; errors={}
    for code,league in ESPN_35.items():
        url=f"https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/scoreboard?dates={date_range}&limit=1000"
        try:
            r=requests.get(url,headers={"User-Agent":HEADERS["User-Agent"],"Accept":"application/json"},timeout=25)
            if not r.ok:
                counts[league]=0;errors[league]=f"HTTP {r.status_code}";continue
            data=r.json()
            found=[]
            for event in data.get("events",[]):
                comps=event.get("competitions") or []
                if not comps: continue
                comp=comps[0]
                cs=comp.get("competitors") or []
                home=next((x for x in cs if x.get("homeAway")=="home"),None)
                away=next((x for x in cs if x.get("homeAway")=="away"),None)
                if not home or not away: continue
                status=(event.get("status") or {}).get("type") or {}
                if status.get("completed") or status.get("state")=="post": continue
                kickoff=str(event.get("date") or "")
                d=kickoff[:10]
                if not d or d < start.isoformat() or d > end.isoformat(): continue
                ht=home.get("team") or {}; at=away.get("team") or {}
                hn=resolve_slug_team(slugify(ht.get("displayName") or ht.get("name") or ""))
                an=resolve_slug_team(slugify(at.get("displayName") or at.get("name") or ""))
                if not hn or not an: continue
                found.append({
                  "event_id":"ESPN|"+code+"|"+str(event.get("id") or ""),
                  "date":d,"kickoff":kickoff,"league":league,"league_code":code,
                  "home":hn,"away":an,"home_logo":ht.get("logo") or "","away_logo":at.get("logo") or "",
                  "status":status.get("description") or status.get("detail") or "Planlandı",
                  "completed":False,"state":status.get("state") or "pre","referee":"",
                  "source":"ESPN lig fikstürü","source_url":url
                })
            counts[league]=len(found);out.extend(found)
        except Exception as e:
            counts[league]=0;errors[league]=repr(e)
    return out,counts,errors

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
    month=ALL_MONTHS[mon]
    # season pages cross New Year: dates Jan-Jun after an Aug-Dec current date are next year.
    if not m.group(3) and month < 7 and now.month >= 7:y=year_hint+1
    return f"{y:04d}-{month:02d}-{int(d):02d}"

def clean_tff_team(v):
    v=str(v or "").strip()
    v=re.sub(r"\s+A\.Ş\.$","",v).strip()
    v=v.replace("TÜMOSAN ","").replace("CORENDON ","").replace("ARCA ","")
    v=v.replace("FUTBOL KULÜBÜ","").replace("SPORTİF FAALİYETLER","").strip()
    # Prefer the canonical historical team name where possible.
    return resolve_slug_team(slugify(v))

def fetch_tff_super_lig():
    out=[]
    base="https://www.tff.org/Default.aspx?pageId=198&hafta={}"
    seen=set()
    for week in range(1,35):
        try:
            html=fetch(base.format(week))
            soup=BeautifulSoup(html,"html.parser")
            txt="\n".join(soup.stripped_strings)
            # TFF week pages expose rows like 14.08.2026 21:30 HOME - AWAY Detaylar
            for m in re.finditer(r"(\d{2}\.\d{2}\.20\d{2})(?:\s+(\d{1,2}:\d{2}))?\s+([^\n]+?)\s+-\s+([^\n]+?)(?=\s+Detaylar|\n|$)",txt):
                ds,hm,home,away=m.groups()
                d=datetime.strptime(ds,"%d.%m.%Y").strftime("%Y-%m-%d")
                home=clean_tff_team(home); away=clean_tff_team(away)
                if not home or not away: continue
                kickoff=d+(("T"+hm+":00+03:00") if hm else "")
                try:
                    if hm and datetime.fromisoformat(kickoff)<now: continue
                except Exception: pass
                k="|".join([d,home,away])
                if k in seen: continue
                seen.add(k)
                out.append({
                  "event_id":"TFF|"+str(week)+"|"+k,
                  "date":d,"kickoff":kickoff,"league":"Türkiye Süper Lig","league_code":"TFF",
                  "home":home,"away":away,"home_logo":"","away_logo":"","status":"Planlandı",
                  "completed":False,"state":"pre","referee":"","source":"TFF resmi fikstür",
                  "source_url":base.format(week),"week":week,"season":"2026/27"
                })
        except Exception as e:
            print("TFF week error",week,repr(e))
    return out

rows=[]
diag={}
fd_rows,fd_counts=fetch_football_data_fixtures()
rows.extend(fd_rows)
espn_rows,espn_counts,espn_errors=fetch_espn_35()
rows.extend(espn_rows)
for _lg in WAREHOUSE_35: diag[_lg]=int(fd_counts.get(_lg,0) or 0)+int(espn_counts.get(_lg,0) or 0)
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
                d=f"{int(yy):04d}-{ALL_MONTHS[mon]:02d}-{int(dd):02d}"
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
        diag[league]=int(diag.get(league,0) or 0)+len(found)
        rows.extend(found)
    except Exception as e:
        diag[league]=diag.get(league,0)

# Official TFF source for Türkiye Süper Lig avoids same-name league collisions.
tff_rows=fetch_tff_super_lig()
rows.extend(tff_rows)
diag["Türkiye Süper Lig"]=int(diag.get("Türkiye Süper Lig",0) or 0)+len(tff_rows)

# Keep the rolling Sahadan İddaa snapshot too; it covers additional leagues.
try:
    with open("data/current_fixtures.json","r",encoding="utf-8") as f:cur=json.load(f)
    rows.extend([x for x in cur.get("matches",[]) if not x.get("completed")])
except Exception:pass

def source_rank(x):
    s=str(x.get("source") or "").lower()
    if "tff" in s:return 40
    if "sahadan lig" in s:return 35
    if s.startswith("sahadan"):return 30
    if "football-data" in s:return 28\n    if "espn" in s:return 20
    return 10

best={}
for x in rows:
    k="|".join([str(x.get("date") or ""),str(x.get("league") or ""),slugify(x.get("home") or ""),slugify(x.get("away") or "")])
    old=best.get(k)
    if old is None or source_rank(x)>source_rank(old):
        best[k]=x
clean=list(best.values())
clean.sort(key=lambda x:(x.get("date") or "",x.get("kickoff") or "",x.get("league") or "",x.get("home") or ""))

payload={"ok":True,"generated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"source":"Sahadan + TFF + ESPN 35 lig fikstürleri + İddaa Programı","count":len(clean),"league_counts":diag,"football_data":fd_counts,"espn_errors":espn_errors,"coverage_leagues":sum(1 for l in WAREHOUSE_35 if int(diag.get(l,0) or 0)>0),"target_leagues":35,"matches":clean}
with open(OUT,"w",encoding="utf-8") as f:json.dump(payload,f,ensure_ascii=False,separators=(",",":"))
print("future fixtures:",len(clean))
print("league counts:",json.dumps(diag,ensure_ascii=False))
print("sample:",json.dumps(clean[:12],ensure_ascii=False))
