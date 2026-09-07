from flask import Flask, request, Response, jsonify, send_from_directory
import requests
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

app = Flask(__name__)

ALLOWED_HOSTS = {"www.football-data.co.uk", "football-data.co.uk"}
APP_VERSION = "3.5"
SOURCE_CACHE = {}

ESPN_LEAGUES = {
    "tur.1": "Türkiye Süper Lig",
    "eng.1": "İngiltere Premier League",
    "eng.2": "İngiltere EFL Championship",
    "eng.3": "İngiltere EFL League One",
    "eng.4": "İngiltere EFL League Two",
    "sco.1": "İskoçya Premiership",
    "sco.2": "İskoçya Championship",
    "ger.1": "Almanya Bundesliga",
    "ger.2": "Almanya 2. Bundesliga",
    "esp.1": "İspanya La Liga",
    "esp.2": "İspanya LaLiga 2",
    "ita.1": "İtalya Serie A",
    "ita.2": "İtalya Serie B",
    "fra.1": "Fransa Ligue 1",
    "fra.2": "Fransa Ligue 2",
    "ned.1": "Hollanda Eredivisie",
    "bel.1": "Belçika Pro League",
    "por.1": "Portekiz Primeira Liga",
    "gre.1": "Yunanistan Super League",
    "aut.1": "Avusturya Bundesliga",
    "sui.1": "İsviçre Super League",
    "den.1": "Danimarka Superliga",
    "nor.1": "Norveç Eliteserien",
    "swe.1": "İsveç Allsvenskan",
    "swe.2": "İsveç Superettan",
    "irl.1": "İrlanda Premier Division",
    "pol.1": "Polonya Ekstraklasa",
    "cze.1": "Çekya First League",
    "rou.1": "Romanya Liga I",
    "cro.1": "Hırvatistan HNL",
    "srp.1": "Sırbistan SuperLiga",
    "ukr.1": "Ukrayna Premier League",
    "rus.1": "Rusya Premier League",
    "jpn.1": "Japonya J1 League",
    "jpn.2": "Japonya J2 League",
    "kor.1": "Güney Kore K League 1",
    "chn.1": "Çin Süper Ligi",
    "aus.1": "Avustralya A-League Men",
    "ind.1": "Hindistan Super League",
    "idn.1": "Endonezya Liga 1",
    "tha.1": "Tayland League 1",
    "mys.1": "Malezya Super League",
    "sgp.1": "Singapur Premier League",
    "bra.1": "Brezilya Série A",
    "bra.2": "Brezilya Série B",
    "arg.1": "Arjantin Primera División",
    "uru.1": "Uruguay Primera División",
    "chi.1": "Şili Primera División",
    "col.1": "Kolombiya Primera A",
    "ecu.1": "Ekvador LigaPro",
    "per.1": "Peru Liga 1",
    "par.1": "Paraguay Primera División",
    "usa.1": "ABD MLS",
    "mex.1": "Meksika Liga MX",
    "crc.1": "Kosta Rika Primera División",
    "ksa.1": "Suudi Arabistan Pro League",
    "qat.1": "Katar Stars League",
    "uae.1": "BAE Pro League",
    "rsa.1": "Güney Afrika Premiership",
    "egy.1": "Mısır Premier League",
    "mar.1": "Fas Botola Pro",
}

@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    if request.path in {"/", "/index.html", "/sw.js", "/manifest.json"}:
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp

@app.get("/")
def home():
    return send_from_directory(".", "index.html")

@app.get("/manifest.json")
def manifest():
    return send_from_directory(".", "manifest.json", mimetype="application/manifest+json")

@app.get("/sw.js")
def service_worker():
    resp = send_from_directory(".", "sw.js", mimetype="application/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    return resp

@app.get("/api")
def api_info():
    return jsonify({"ok": True, "service": "Ters Kose data proxy", "version": APP_VERSION})

@app.get("/index.html")
def index_file():
    return send_from_directory(".", "index.html")

@app.get("/health")
def health():
    return jsonify({"ok": True, "frontend": True, "proxy": True, "version": APP_VERSION, "cache_entries": len(SOURCE_CACHE)})


@app.get("/leagues")
def leagues():
    rows = [{"code": code, "name": name} for code, name in ESPN_LEAGUES.items()]
    rows.sort(key=lambda x: x["name"])
    return jsonify({"ok": True, "leagues": rows, "count": len(rows)})

@app.get("/teams")
def teams():
    league = request.args.get("league", "").strip()
    codes = [league] if league in ESPN_LEAGUES else list(ESPN_LEAGUES.keys())
    out, errors = [], []

    def fetch_teams(code):
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/teams?limit=200"
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if not r.ok:
                return [], {"league": code, "status": r.status_code}
            data = r.json()
            items = []
            for sport in data.get("sports", []):
                for lg in sport.get("leagues", []):
                    for item in lg.get("teams", []):
                        team = item.get("team", {})
                        logos = team.get("logos") or []
                        items.append({
                            "league_code": code,
                            "league": ESPN_LEAGUES.get(code, code),
                            "name": team.get("displayName") or team.get("name") or "",
                            "short": team.get("shortDisplayName") or "",
                            "abbreviation": team.get("abbreviation") or "",
                            "slug": team.get("slug") or "",
                            "logo": (logos[0].get("href") if logos else team.get("logo")) or "",
                        })
            return items, None
        except Exception as e:
            return [], {"league": code, "detail": str(e)}

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_teams, code) for code in codes]
        for fut in as_completed(futures):
            rows, err = fut.result()
            out.extend(rows)
            if err:
                errors.append(err)
    return jsonify({"ok": True, "teams": out, "count": len(out), "errors": errors})

@app.get("/fixtures")
def fixtures():
    date = request.args.get("date", "").strip().replace("-", "")
    if len(date) != 8 or not date.isdigit():
        return jsonify({"error": "date YYYY-MM-DD gerekli"}), 400

    def fetch_league(item):
        league_code, league_name = item
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_code}/scoreboard?dates={date}&limit=100"
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if not r.ok:
                return [], {"league": league_name, "status": r.status_code}
            data = r.json()
            out = []
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
                officials = comp.get("officials") or []
                referee = ""
                for off in officials:
                    if str(off.get("position", {}).get("name", "")).lower() in {"referee", "hakem"} or not referee:
                        referee = off.get("fullName") or off.get("displayName") or off.get("name") or referee
                out.append({
                    "event_id": event.get("id", ""),
                    "date": (event.get("date") or "")[:10],
                    "kickoff": event.get("date", ""),
                    "league": league_name,
                    "league_code": league_code,
                    "home": ht.get("displayName") or ht.get("name") or "",
                    "away": at.get("displayName") or at.get("name") or "",
                    "home_logo": ht.get("logo") or "",
                    "away_logo": at.get("logo") or "",
                    "status": status.get("description") or status.get("detail") or "",
                    "completed": bool(status.get("completed")),
                    "state": status.get("state") or "",
                    "referee": referee,
                })
            return out, None
        except Exception as e:
            return [], {"league": league_name, "detail": str(e)}

    all_matches, errors = [], []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_league, item) for item in ESPN_LEAGUES.items()]
        for fut in as_completed(futures):
            rows, err = fut.result()
            all_matches.extend(rows)
            if err:
                errors.append(err)
    all_matches.sort(key=lambda x: (x.get("kickoff") or "", x.get("league") or "", x.get("home") or ""))
    return jsonify({"ok": True, "date": date, "matches": all_matches, "count": len(all_matches), "errors": errors})

@app.get("/smoke")
def smoke():
    files = {}
    for name in ("index.html", "manifest.json", "sw.js", "requirements.txt"):
        files[name] = {"exists": os.path.exists(name), "bytes": os.path.getsize(name) if os.path.exists(name) else 0}
    frontend_ok = files["index.html"]["exists"] and files["index.html"]["bytes"] > 1000
    pwa_ok = files["manifest.json"]["exists"] and files["sw.js"]["exists"]
    source = {"ok": False, "status": None, "bytes": 0, "detail": ""}
    try:
        probe = fetch_source("https://www.football-data.co.uk/matches/resources/fixtures.csv")
        source = {"ok": bool(probe.ok and probe.content), "status": probe.status_code, "bytes": len(probe.content), "detail": "live"}
    except Exception as e:
        cached = SOURCE_CACHE.get("https://www.football-data.co.uk/matches/resources/fixtures.csv")
        if cached:
            source = {"ok": True, "status": 200, "bytes": len(cached["content"]), "detail": "cache"}
        else:
            source = {"ok": False, "status": None, "bytes": 0, "detail": str(e)}
    overall_ok = frontend_ok and pwa_ok and source["ok"]
    payload = {
        "ok": overall_ok,
        "version": APP_VERSION,
        "frontend_ok": frontend_ok,
        "pwa_ok": pwa_ok,
        "files": files,
        "fixture_source": source,
    }
    return jsonify(payload), (200 if overall_ok else 503)

def fetch_source(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36",
        "Accept": "text/csv,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.football-data.co.uk/",
        "Connection": "close",
    }
    last_error = None
    p = urlparse(url)
    for host in ("www.football-data.co.uk", "football-data.co.uk"):
        candidate = p._replace(netloc=host).geturl()
        for attempt in range(3):
            try:
                r = requests.get(candidate, timeout=25, headers=headers, allow_redirects=True)
                if r.ok and r.content:
                    SOURCE_CACHE[url] = {
                        "content": r.content,
                        "content_type": r.headers.get("Content-Type", "text/csv; charset=utf-8"),
                        "saved_at": time.time(),
                    }
                    if len(SOURCE_CACHE) > 128:
                        oldest = min(SOURCE_CACHE, key=lambda k: SOURCE_CACHE[k]["saved_at"])
                        SOURCE_CACHE.pop(oldest, None)
                    return r
                if r.status_code == 404:
                    last_error = requests.HTTPError(f"404 Not Found for url: {candidate}")
                    break
                last_error = requests.HTTPError(f"{r.status_code} Server Error for url: {candidate}")
            except requests.RequestException as e:
                last_error = e
            if attempt < 2:
                time.sleep(0.6 * (attempt + 1))
    raise last_error or requests.RequestException("football-data kaynagina ulasilamadi")

@app.get("/proxy")
def proxy():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "url gerekli"}), 400

    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        return jsonify({"error": "izin verilmeyen kaynak"}), 403

    try:
        r = fetch_source(url)
        resp = Response(r.content, status=200, content_type=r.headers.get("Content-Type", "text/csv; charset=utf-8"))
        resp.headers["X-TersKose-Source"] = "live"
        return resp
    except requests.RequestException as e:
        cached = SOURCE_CACHE.get(url)
        if cached:
            resp = Response(cached["content"], status=200, content_type=cached["content_type"])
            resp.headers["X-TersKose-Source"] = "cache"
            resp.headers["X-TersKose-Cache-Age"] = str(int(time.time() - cached["saved_at"]))
            return resp
        return jsonify({"error": "veri kaynagina ulasilamadi", "detail": str(e)}), 502

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
