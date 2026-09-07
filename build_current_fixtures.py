import json
import os
import re
import time
import unicodedata
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

def slugify(s):
    s = str(s or "").strip().casefold()
    s = s.replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

def fetch(url, tries=4):
    last = None
    for attempt in range(tries):
        try:
            r = requests.get(url, timeout=30, headers=HEADERS, allow_redirects=True)
            if r.ok and r.text:
                return r
            last = RuntimeError(f"HTTP {r.status_code} {url}")
        except Exception as e:
            last = e
        time.sleep(1.5 * (attempt + 1))
    raise last or RuntimeError("fetch failed")

# Build a team-name and current-league dictionary from our verified historical warehouse.
with open("data/history_10y.json", "r", encoding="utf-8") as h:
    history = json.load(h)

team_candidates = {}
team_latest = {}
for row in history:
    league = str(row.get("league") or "").strip()
    date = str(row.get("date") or "")
    for team in (row.get("home"), row.get("away")):
        team = str(team or "").strip()
        if not team:
            continue
        key = slugify(team)
        if not key:
            continue
        team_candidates.setdefault(key, set()).add(team)
        old = team_latest.get(key)
        if not old or date > old[0]:
            team_latest[key] = (date, team, league)

# Add useful Sahadan-style short forms to matching keys.
def resolve_team(slug):
    if slug in team_latest:
        return team_latest[slug][1], team_latest[slug][2]
    # relaxed suffix/prefix comparison for FK/FC/SK and abbreviations
    simple = re.sub(r"-(fk|fc|sk|cf|bk|if|ac)$", "", slug)
    hits = []
    for k, info in team_latest.items():
        ks = re.sub(r"-(fk|fc|sk|cf|bk|if|ac)$", "", k)
        if ks == simple or k.endswith("-" + simple) or simple.endswith("-" + ks):
            hits.append(info)
    if hits:
        hits.sort(key=lambda x: x[0], reverse=True)
        return hits[0][1], hits[0][2]
    return "", ""

html = fetch(PROGRAM).text
soup = BeautifulSoup(html, "html.parser")

# Date comes from Sahadan page title/header, falling back to Istanbul today.
page_text = soup.get_text(" ", strip=True)
mdate = re.search(r"\b(\d{2})\.(\d{2})\.(20\d{2})\b", page_text)
if mdate:
    dd, mm, yyyy = mdate.groups()
    bulletin_date = f"{yyyy}-{mm}-{dd}"
else:
    bulletin_date = datetime.now(ZoneInfo("Europe/Istanbul")).date().isoformat()

links = []
for a in soup.find_all("a", href=True):
    href = str(a.get("href") or "")
    if "/mac/" not in href or not href.rstrip("/").endswith("/iddaa"):
        continue
    full = urljoin(BASE, href)
    if full not in links:
        links.append(full)

print("Sahadan match links:", len(links), "date:", bulletin_date)

rows = []
unmatched = []
for full in links:
    try:
        slug = full.split("/mac/", 1)[1].split("/", 1)[0]
        if "-vs-" not in slug:
            continue
        home_slug, away_slug = slug.split("-vs-", 1)
        home, home_league = resolve_team(home_slug)
        away, away_league = resolve_team(away_slug)

        if not home or not away:
            unmatched.append((home_slug, away_slug))
            continue

        # Only keep games that can be tied to one of our analysis leagues.
        league = home_league if home_league and home_league == away_league else (home_league or away_league)
        if not league:
            unmatched.append((home_slug, away_slug))
            continue

        # Find kickoff in the match card containing this link.
        kickoff_time = ""
        anchor = soup.find("a", href=lambda x: x and full.endswith(str(x)) if str(x).startswith("/") else str(x) == full)
        if anchor:
            node = anchor
            for _ in range(7):
                node = getattr(node, "parent", None)
                if node is None:
                    break
                text = node.get_text(" ", strip=True)
                mt = re.search(r"(?<!\d)([0-2]?\d:[0-5]\d)(?!\d)", text)
                if mt:
                    kickoff_time = mt.group(1)
                    break

        kickoff = bulletin_date + (("T" + kickoff_time + ":00+03:00") if kickoff_time else "")
        event_id = full.rstrip("/").split("/")[-2]

        rows.append({
            "event_id": event_id,
            "date": bulletin_date,
            "kickoff": kickoff,
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
            "source_url": full,
        })
    except Exception as e:
        print("parse error", full, repr(e))

# Remove duplicates and games that already started when a kickoff was recovered.
now_tr = datetime.now(ZoneInfo("Europe/Istanbul"))
seen = set()
clean = []
for x in rows:
    k = "|".join([x["date"], x["league"], x["home"], x["away"]])
    if k in seen:
        continue
    seen.add(k)
    if "T" in x.get("kickoff", ""):
        try:
            dt = datetime.fromisoformat(x["kickoff"])
            if dt < now_tr:
                continue
        except Exception:
            pass
    clean.append(x)

clean.sort(key=lambda x: (x["date"], x.get("kickoff") or "", x["league"], x["home"]))
print("matched analysis fixtures:", len(clean), "unmatched:", len(unmatched))
print("sample:", json.dumps(clean[:8], ensure_ascii=False))
print("unmatched sample:", unmatched[:12])

if not clean:
    if os.path.exists("data/current_fixtures.json"):
        with open("data/current_fixtures.json", "r", encoding="utf-8") as h:
            old = json.load(h)
        if int(old.get("count") or 0) > 0:
            print("Sahadan parse empty; preserving previous good snapshot", old.get("count"))
            raise SystemExit(0)
    raise RuntimeError("Sahadan bülteni tarihsel takım listesiyle eşleşmedi")

payload = {
    "ok": True,
    "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "source": "Sahadan İddaa Programı",
    "source_url": PROGRAM,
    "date": bulletin_date,
    "matches": clean,
    "count": len(clean),
    "unmatched": len(unmatched),
}
with open("data/current_fixtures.json", "w", encoding="utf-8") as h:
    json.dump(payload, h, ensure_ascii=False, separators=(",", ":"))
print("fixtures written:", len(clean))
