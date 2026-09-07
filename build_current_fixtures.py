import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE = "https://www.sahadan.com"
PROGRAM = BASE + "/Iddaa-Programi"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.7,en;q=0.6",
    "Referer": BASE + "/",
    "Connection": "close",
}
TR_MONTHS = {
    "Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6,
    "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12,
}
LEAGUE_MAP = {
    "Trendyol Süper Lig": "Türkiye Süper Lig",
    "Türkiye Trendyol Süper Lig": "Türkiye Süper Lig",
    "Premier League": "İngiltere Premier League",
    "Championship": "İngiltere EFL Championship",
    "Bundesliga": "Almanya Bundesliga",
    "2. Bundesliga": "Almanya 2. Bundesliga",
    "LaLiga": "İspanya La Liga",
    "LaLiga 2": "İspanya LaLiga 2",
    "Serie A": "İtalya Serie A",
    "Serie B": "İtalya Serie B",
    "Ligue 1": "Fransa Ligue 1",
    "Ligue 2": "Fransa Ligue 2",
    "Eredivisie": "Hollanda Eredivisie",
    "Pro League": "Belçika Pro League",
    "Premier Lig": "Portekiz Primeira Liga",
    "Süper Lig": "Yunanistan Super League",
    "Superliga": "Danimarka Superliga",
    "Eliteserien": "Norveç Eliteserien",
    "Allsvenskan": "İsveç Allsvenskan",
    "Superettan": "İsveç Superettan",
    "Premier Division": "İrlanda Premier Division",
    "Ekstraklasa": "Polonya Ekstraklasa",
    "Premier League -": "Rusya Premier League",
    "J1 League": "Japonya J1 League",
    "Serie A": "İtalya Serie A",
    "MLS": "ABD MLS",
    "Liga MX": "Meksika Liga MX",
}
TARGET_LEAGUES = {
    "Türkiye Süper Lig","İngiltere Premier League","İngiltere EFL Championship","İngiltere EFL League One","İngiltere EFL League Two",
    "İskoçya Premiership","İskoçya Championship","Almanya Bundesliga","Almanya 2. Bundesliga","İspanya La Liga","İspanya LaLiga 2",
    "İtalya Serie A","İtalya Serie B","Fransa Ligue 1","Fransa Ligue 2","Hollanda Eredivisie","Belçika Pro League",
    "Portekiz Primeira Liga","Yunanistan Super League","Avusturya Bundesliga","İsviçre Super League","Danimarka Superliga",
    "Norveç Eliteserien","İsveç Allsvenskan","İsveç Superettan","İrlanda Premier Division","Polonya Ekstraklasa",
    "Romanya Liga I","Rusya Premier League","Japonya J1 League","Çin Süper Ligi","Brezilya Série A","Arjantin Primera División",
    "ABD MLS","Meksika Liga MX",
}

def fetch(url, tries=4):
    last = None
    for attempt in range(tries):
        try:
            r = requests.get(url, timeout=25, headers=HEADERS, allow_redirects=True)
            if r.ok and r.text:
                return r
            last = RuntimeError(f"HTTP {r.status_code} {url}")
        except Exception as e:
            last = e
        time.sleep(1.0 * (attempt + 1))
    raise last or RuntimeError("fetch failed")

def parse_date_time(text):
    m = re.search(r"(\d{1,2})\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\s+(20\d{2})\s*-\s*(\d{1,2}:\d{2})", text)
    if not m:
        return "", ""
    day, month_name, year, hm = m.groups()
    month = TR_MONTHS[month_name]
    date = f"{int(year):04d}-{month:02d}-{int(day):02d}"
    return date, hm

def normalize_league(raw):
    raw = re.sub(r"\s+-\s+.*Sezonu.*$", "", raw).strip()
    # exact/contains rules for common Sahadan naming
    rules = [
        ("Trendyol Süper Lig", "Türkiye Süper Lig"),
        ("Premier League", "İngiltere Premier League"),
        ("Championship", "İngiltere EFL Championship"),
        ("2. Bundesliga", "Almanya 2. Bundesliga"),
        ("Bundesliga", "Almanya Bundesliga"),
        ("LaLiga 2", "İspanya LaLiga 2"),
        ("LaLiga", "İspanya La Liga"),
        ("Serie B", "İtalya Serie B"),
        ("Serie A", "İtalya Serie A"),
        ("Ligue 2", "Fransa Ligue 2"),
        ("Ligue 1", "Fransa Ligue 1"),
        ("Eredivisie", "Hollanda Eredivisie"),
        ("Danimarka", "Danimarka Superliga"),
        ("Eliteserien", "Norveç Eliteserien"),
        ("Allsvenskan", "İsveç Allsvenskan"),
        ("Superettan", "İsveç Superettan"),
        ("Ekstraklasa", "Polonya Ekstraklasa"),
        ("MLS", "ABD MLS"),
        ("Liga MX", "Meksika Liga MX"),
    ]
    for needle, name in rules:
        if needle.lower() in raw.lower():
            return name
    return raw

def parse_match(url):
    try:
        html = fetch(url).text
        soup = BeautifulSoup(html, "html.parser")
        title = (soup.title.get_text(" ", strip=True) if soup.title else "")
        # Title format: Home - Away Maç Oranları ...
        m = re.match(r"\s*(.+?)\s+-\s+(.+?)\s+Maç", title)
        if not m:
            return None
        home, away = m.group(1).strip(), m.group(2).strip()
        text = soup.get_text("\n", strip=True)
        date, hm = parse_date_time(text)
        if not date:
            return None

        league = ""
        for a in soup.find_all("a"):
            t = a.get_text(" ", strip=True)
            if not t:
                continue
            if "Sezonu" in t or any(k in t for k in ("Süper Lig","Premier League","Bundesliga","LaLiga","Serie A","Serie B","Ligue 1","Ligue 2","Eredivisie","Eliteserien","Allsvenskan","Superettan","Ekstraklasa","MLS","Liga MX")):
                league = normalize_league(t)
                if league:
                    break
        if not league:
            return None

        # Keep only future/unplayed games. Use Istanbul time.
        try:
            local_dt = datetime.strptime(date + " " + hm, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Europe/Istanbul"))
            if local_dt < datetime.now(ZoneInfo("Europe/Istanbul")):
                return None
        except Exception:
            pass

        return {
            "event_id": url.rstrip("/").split("/")[-2] if "/iddaa" in url else url,
            "date": date,
            "kickoff": date + "T" + hm + ":00+03:00",
            "league": league,
            "league_code": "SAHADAN",
            "home": home,
            "away": away,
            "home_logo": "",
            "away_logo": "",
            "status": "Planlandı",
            "completed": False,
            "state": "pre",
            "referee": "",
            "source": "Sahadan",
            "source_url": url,
        }
    except Exception as e:
        print("detail error", url, repr(e))
        return None

program = fetch(PROGRAM).text
soup = BeautifulSoup(program, "html.parser")
links = []
for a in soup.find_all("a", href=True):
    href = a["href"]
    if "/mac/" in href and href.rstrip("/").endswith("/iddaa"):
        full = urljoin(BASE, href)
        if full not in links:
            links.append(full)

print("sahadan match links:", len(links))
if not links:
    # Print a small diagnostic sample for future maintenance.
    for a in soup.find_all("a", href=True)[:80]:
        print("anchor", a.get("href"), a.get_text(" ", strip=True)[:80])
    raise RuntimeError("Sahadan programında maç linki bulunamadı")

rows = []
with ThreadPoolExecutor(max_workers=12) as pool:
    futs = [pool.submit(parse_match, u) for u in links]
    for fut in as_completed(futs):
        item = fut.result()
        if item:
            rows.append(item)

# Prefer our known analysis leagues but do not throw away other valid bulletin games.
seen = set()
clean = []
for x in rows:
    key = "|".join([x["date"], x["league"], x["home"], x["away"]])
    if key in seen:
        continue
    seen.add(key)
    clean.append(x)

clean.sort(key=lambda x: (x["date"], x["kickoff"], x["league"], x["home"]))
known = [x for x in clean if x["league"] in TARGET_LEAGUES]
unknown = [x for x in clean if x["league"] not in TARGET_LEAGUES]
print("parsed:", len(clean), "known-analysis-leagues:", len(known), "other:", len(unknown))
print("sample:", json.dumps(clean[:5], ensure_ascii=False))

if not clean:
    if os.path.exists("data/current_fixtures.json"):
        with open("data/current_fixtures.json", "r", encoding="utf-8") as h:
            old = json.load(h)
        if int(old.get("count") or 0) > 0:
            print("Sahadan parse empty; preserving previous good snapshot", old.get("count"))
            raise SystemExit(0)
    raise RuntimeError("Sahadan bülteni parse edilemedi")

payload = {
    "ok": True,
    "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "source": "Sahadan İddaa Programı",
    "source_url": PROGRAM,
    "matches": clean,
    "count": len(clean),
    "known_analysis_league_count": len(known),
}
with open("data/current_fixtures.json", "w", encoding="utf-8") as h:
    json.dump(payload, h, ensure_ascii=False, separators=(",", ":"))
print("fixtures written:", len(clean))
