from flask import Flask, request, Response, jsonify, send_from_directory
import requests
import time
import os
import csv
import io
import json
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import gzip
from urllib.parse import urlparse

app = Flask(__name__)

ALLOWED_HOSTS = {"www.football-data.co.uk", "football-data.co.uk"}
APP_VERSION = "4.1"
SOURCE_CACHE = {}
FIXTURE_CACHE = {}
TEAM_CACHE = {}

MAIN_HISTORY_LEAGUES = {
    "T1": "Türkiye Süper Lig", "E0": "İngiltere Premier League", "E1": "İngiltere EFL Championship",
    "E2": "İngiltere EFL League One", "E3": "İngiltere EFL League Two", "SC0": "İskoçya Premiership",
    "SC1": "İskoçya Championship", "D1": "Almanya Bundesliga", "D2": "Almanya 2. Bundesliga",
    "SP1": "İspanya La Liga", "SP2": "İspanya LaLiga 2", "I1": "İtalya Serie A", "I2": "İtalya Serie B",
    "F1": "Fransa Ligue 1", "F2": "Fransa Ligue 2", "N1": "Hollanda Eredivisie",
    "B1": "Belçika Pro League", "P1": "Portekiz Primeira Liga", "G1": "Yunanistan Super League",
}
EXTRA_HISTORY_LEAGUES = {
    "ARG": "Arjantin Primera División", "AUT": "Avusturya Bundesliga", "BRA": "Brezilya Série A",
    "CHN": "Çin Süper Ligi", "DNK": "Danimarka Superliga", "FIN": "Finlandiya Veikkausliiga",
    "IRL": "İrlanda Premier Division", "JPN": "Japonya J1 League", "MEX": "Meksika Liga MX",
    "NOR": "Norveç Eliteserien", "POL": "Polonya Ekstraklasa", "ROU": "Romanya Liga I",
    "RUS": "Rusya Premier League", "SWE": "İsveç Allsvenskan", "SWZ": "İsviçre Super League",
    "USA": "ABD MLS",
}
HISTORY_DIR = os.path.join(os.path.dirname(__file__), "data")
HISTORY_FILE = os.path.join(HISTORY_DIR, "history_10y.json")
HISTORY_META_FILE = os.path.join(HISTORY_DIR, "history_meta.json")
HISTORY_LOCK = False
HISTORY_RETRY_LOCK = False
HISTORY_RESPONSE_CACHE = {"mtime": None, "plain": None, "gzip": None, "count": 0}

def _main_code_for_name(name):
    for code, league_name in MAIN_HISTORY_LEAGUES.items():
        if league_name == name:
            return code
    return None

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
    meta = {}
    if os.path.exists(HISTORY_META_FILE):
        try:
            with open(HISTORY_META_FILE, "r", encoding="utf-8") as h:
                meta = json.load(h)
        except Exception:
            meta = {}
    return jsonify({
        "ok": True, "frontend": True, "proxy": True, "version": APP_VERSION,
        "cache_entries": len(SOURCE_CACHE),
        "history_built": os.path.exists(HISTORY_FILE),
        "history_matches": meta.get("matches", 0),
        "history_failures": meta.get("critical_failures", 0),
    })


def _num(v):
    try:
        if v is None or str(v).strip() == "":
            return None
        return int(float(str(v).strip()))
    except Exception:
        return None

def _float_num(v):
    """Parse decimal market values without truncating bookmaker odds."""
    try:
        if v is None or str(v).strip() == "":
            return None
        return float(str(v).strip().replace(",", "."))
    except Exception:
        return None

def _date(v):
    v = str(v or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return v[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", v) else v

def _season_from_row(row, date_value):
    raw = str(row.get("Season") or row.get("season") or "").strip()
    if raw:
        m = re.search(r"(20\d{2})", raw)
        if m:
            y = int(m.group(1))
            return f"{y}/{str(y+1)[-2:]}"
        m = re.search(r"(\d{4})", raw)
        if m:
            y = int(m.group(1))
            return f"{y}/{str(y+1)[-2:]}"
    try:
        d = datetime.strptime(date_value, "%Y-%m-%d")
        y = d.year if d.month >= 7 else d.year - 1
        return f"{y}/{str(y+1)[-2:]}"
    except Exception:
        return ""

def _parse_history_csv(content, league_name, season_label="", calendar_season=False):
    text = content.decode("utf-8-sig", errors="replace")
    if "\ufffd" in text[:1000]:
        text = content.decode("cp1252", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    out = []
    for r in rows:
        home = str(r.get("HomeTeam") or r.get("Home") or "").strip()
        away = str(r.get("AwayTeam") or r.get("Away") or "").strip()
        fh = _num(r.get("FTHG") if r.get("FTHG") not in (None, "") else r.get("HG"))
        fa = _num(r.get("FTAG") if r.get("FTAG") not in (None, "") else r.get("AG"))
        if not home or not away or fh is None or fa is None:
            continue
        date = _date(r.get("Date"))
        ht_h = _num(r.get("HTHG") if r.get("HTHG") not in (None, "") else r.get("HHG"))
        ht_a = _num(r.get("HTAG") if r.get("HTAG") not in (None, "") else r.get("HAG"))
        week = _num(r.get("MW") or r.get("Round") or r.get("Matchday"))

        # Prefer market-average closing prices when football-data provides them.
        # Fallbacks keep older seasons useful because column availability changes by year.
        odds_h = _float_num(r.get("AvgH") or r.get("B365H") or r.get("PSH") or r.get("PSCH") or r.get("MaxH"))
        odds_d = _float_num(r.get("AvgD") or r.get("B365D") or r.get("PSD") or r.get("PSCD") or r.get("MaxD"))
        odds_a = _float_num(r.get("AvgA") or r.get("B365A") or r.get("PSA") or r.get("PSCA") or r.get("MaxA"))
        odds_o25 = _float_num(r.get("Avg>2.5") or r.get("B365>2.5") or r.get("P>2.5") or r.get("Max>2.5"))
        odds_u25 = _float_num(r.get("Avg<2.5") or r.get("B365<2.5") or r.get("P<2.5") or r.get("Max<2.5"))

        if season_label:
            parsed_season = season_label
        elif calendar_season:
            raw_season = str(r.get("Season") or r.get("season") or "").strip()
            m = re.search(r"(20\d{2})", raw_season)
            if m:
                parsed_season = m.group(1)
            else:
                try:
                    parsed_season = str(datetime.strptime(date, "%Y-%m-%d").year)
                except Exception:
                    parsed_season = ""
        else:
            parsed_season = _season_from_row(r, date)

        out.append({
            "date": date, "league": league_name, "season": parsed_season,
            "week": week or 0, "home": home, "away": away,
            "ht_home": ht_h, "ht_away": ht_a, "ft_home": fh, "ft_away": fa,
            "referee": str(r.get("Referee") or "").strip(),
            "odds_home": odds_h, "odds_draw": odds_d, "odds_away": odds_a,
            "odds_over25": odds_o25, "odds_under25": odds_u25,
        })
    return out

def _infer_history_weeks(rows):
    """Fill missing matchweeks deterministically within each league/season.

    football-data historical CSVs generally do not provide a matchweek column.
    We preserve any source-provided week and infer only missing values from each
    team's chronological appearance count. Postponements can make an inferred
    week differ from an official round, so those rows are explicitly marked.
    """
    groups = {}
    for row in rows:
        key = (str(row.get("league") or ""), str(row.get("season") or ""))
        groups.setdefault(key, []).append(row)

    for group_rows in groups.values():
        counts = {}
        ordered = sorted(
            group_rows,
            key=lambda x: (
                str(x.get("date") or "9999-99-99"),
                str(x.get("home") or "").casefold(),
                str(x.get("away") or "").casefold(),
            ),
        )
        for row in ordered:
            if row.get("week"):
                row["week_inferred"] = False
            else:
                home = str(row.get("home") or "")
                away = str(row.get("away") or "")
                row["week"] = max(counts.get(home, 0), counts.get(away, 0)) + 1
                row["week_inferred"] = True
            home = str(row.get("home") or "")
            away = str(row.get("away") or "")
            counts[home] = counts.get(home, 0) + 1
            counts[away] = counts.get(away, 0) + 1
    return rows

def _dedupe_history(rows):
    best = {}
    for x in rows:
        k = "|".join([str(x.get("date","")), str(x.get("league","")), str(x.get("season","")),
                      str(x.get("home","")).lower(), str(x.get("away","")).lower()])
        richness = sum(1 for z in ("week","ht_home","ht_away","referee","odds_home","odds_draw","odds_away","odds_over25","odds_under25") if x.get(z) not in (None,"",0))
        old = best.get(k)
        if old is None or richness > old[0]:
            best[k] = (richness, x)
    return [v[1] for v in best.values()]

def _audit_history_rows(rows):
    bad_team = bad_score = missing_date = missing_week = missing_ht = missing_odds = 0
    groups = {}
    seen = set()
    duplicate_keys = 0
    for x in rows:
        home = str(x.get("home") or "").strip()
        away = str(x.get("away") or "").strip()
        if not home or not away or home.casefold() == away.casefold():
            bad_team += 1
        try:
            fh, fa = float(x.get("ft_home")), float(x.get("ft_away"))
            if fh < 0 or fa < 0:
                bad_score += 1
        except Exception:
            bad_score += 1
        if not x.get("date"):
            missing_date += 1
        if not x.get("week"):
            missing_week += 1
        if x.get("ht_home") is None or x.get("ht_away") is None:
            missing_ht += 1
        if not all(x.get(k) not in (None, "", 0) for k in ("odds_home", "odds_draw", "odds_away")):
            missing_odds += 1
        key = "|".join([str(x.get("date","")), str(x.get("league","")), str(x.get("season","")),
                        home.casefold(), away.casefold()])
        if key in seen:
            duplicate_keys += 1
        seen.add(key)
        gk = (str(x.get("league","")), str(x.get("season","")))
        g = groups.setdefault(gk, {"rows": 0, "teams": set(), "missing_ht": 0, "missing_week": 0})
        g["rows"] += 1
        g["teams"].update([home, away])
        if x.get("ht_home") is None or x.get("ht_away") is None:
            g["missing_ht"] += 1
        if not x.get("week"):
            g["missing_week"] += 1

    group_audit = []
    thin_groups = 0
    for (league, season), g in sorted(groups.items()):
        teams = len([t for t in g["teams"] if t])
        thin = g["rows"] < 80 or teams < 8
        if thin:
            thin_groups += 1
        group_audit.append({
            "league": league, "season": season, "rows": g["rows"], "teams": teams,
            "ht_coverage": round(1 - g["missing_ht"] / max(1, g["rows"]), 4),
            "week_coverage": round(1 - g["missing_week"] / max(1, g["rows"]), 4),
            "thin": thin,
        })

    total = max(1, len(rows))
    score = 1.0
    score -= min(0.35, (bad_team + bad_score + duplicate_keys) / total * 4)
    score -= min(0.20, missing_date / total)
    score -= min(0.15, missing_ht / total * 0.5)
    score -= min(0.10, thin_groups / max(1, len(groups)) * 0.25)
    score = max(0.0, min(1.0, score))
    return {
        "rows": len(rows), "bad_team": bad_team, "bad_score": bad_score,
        "missing_date": missing_date, "missing_week": missing_week, "missing_ht": missing_ht, "missing_odds": missing_odds,
        "duplicate_keys": duplicate_keys, "groups": len(groups), "thin_groups": thin_groups,
        "quality_score": round(score, 4), "group_audit": group_audit,
    }

def _season_start_now():
    now = datetime.utcnow()
    return now.year if now.month >= 7 else now.year - 1

def _load_main_history_season(code, name, y):
    sc = f"{str(y)[-2:]}{str(y+1)[-2:]}"
    season = f"{y}/{str(y+1)[-2:]}"
    url = f"https://www.football-data.co.uk/mmz4281/{sc}/{code}.csv"
    try:
        r = fetch_source(url)
        rows = _parse_history_csv(r.content, name, season)
        if rows:
            return rows, {"league": name, "season": season, "rows": len(rows), "ok": True, "source": "live"}
    except Exception as first_error:
        cached = SOURCE_CACHE.get(url)
        if cached and cached.get("content"):
            rows = _parse_history_csv(cached["content"], name, season)
            if rows:
                return rows, {"league": name, "season": season, "rows": len(rows), "ok": True, "source": "cache", "recovered": True}
        return [], {"league": name, "season": season, "rows": 0, "ok": False, "error": str(first_error)[:120]}
    return [], {"league": name, "season": season, "rows": 0, "ok": False, "error": "empty_source"}

def build_history_10y():
    global HISTORY_LOCK
    if HISTORY_LOCK:
        return {"ok": False, "detail": "already_building"}
    HISTORY_LOCK = True
    try:
        os.makedirs(HISTORY_DIR, exist_ok=True)
        all_rows, audit = [], []
        current_start = _season_start_now()
        # Last 10 completed seasons + current season (current can legitimately be partial).
        completed_starts = list(range(current_start - 10, current_start))
        starts = completed_starts + [current_start]

        def _main_task(code, name, y):
            rows, item = _load_main_history_season(code, name, y)
            if y == current_start:
                item["expected_partial"] = True
            return rows, item

        calendar_codes = {"ARG", "BRA", "CHN", "FIN", "IRL", "JPN", "NOR", "SWE", "USA"}

        def _extra_task(code, name):
            url = f"https://www.football-data.co.uk/new/{code}.csv"
            try:
                r = fetch_source(url)
                rows = _parse_history_csv(r.content, name, calendar_season=code in calendar_codes)
                filtered = []
                for x in rows:
                    try:
                        y = int(str(x.get("season",""))[:4])
                    except Exception:
                        try:
                            y = datetime.strptime(x["date"], "%Y-%m-%d").year
                        except Exception:
                            y = 0
                    if y >= current_start - 10:
                        filtered.append(x)
                return filtered, {"league": name, "season": f"{current_start-10}-{current_start}", "rows": len(filtered), "ok": bool(filtered)}
            except Exception as e:
                return [], {"league": name, "season": f"{current_start-10}-{current_start}", "rows": 0, "ok": False, "error": str(e)[:120]}

        jobs = []
        with ThreadPoolExecutor(max_workers=14) as pool:
            for code, name in MAIN_HISTORY_LEAGUES.items():
                for y in starts:
                    jobs.append(pool.submit(_main_task, code, name, y))
            for code, name in EXTRA_HISTORY_LEAGUES.items():
                jobs.append(pool.submit(_extra_task, code, name))
            for fut in as_completed(jobs):
                rows, item = fut.result()
                all_rows.extend(rows)
                audit.append(item)

        audit.sort(key=lambda a: (str(a.get("league","")), str(a.get("season",""))))
        all_rows = _dedupe_history(all_rows)
        all_rows = _infer_history_weeks(all_rows)
        quality = _audit_history_rows(all_rows)
        league_counts = {}
        for x in all_rows:
            league_counts[x["league"]] = league_counts.get(x["league"], 0) + 1
        failures = sum(1 for a in audit if not a["ok"] and not a.get("expected_partial"))
        current_partial_failures = sum(1 for a in audit if not a["ok"] and a.get("expected_partial"))
        missing_completed = [{"league": a.get("league"), "season": a.get("season"), "error": a.get("error", "")}
                             for a in audit if not a["ok"] and not a.get("expected_partial")]
        thin_completed = [g for g in quality.get("group_audit", [])
                          if g.get("thin") and str(g.get("season","")) != f"{current_start}/{str(current_start+1)[-2:]}"]
        ht_covered = max(0, len(all_rows) - int(quality.get("missing_ht") or 0))
        odds_covered = max(0, len(all_rows) - int(quality.get("missing_odds") or 0))
        meta = {
            "ok": True, "generated_at": datetime.utcnow().isoformat()+"Z", "matches": len(all_rows),
            "leagues": len(league_counts), "league_counts": league_counts, "audit": audit,
            "ht_coverage": round(ht_covered / max(1, len(all_rows)), 4),
            "odds_coverage": round(odds_covered / max(1, len(all_rows)), 4),
            "critical_failures": failures, "current_partial_failures": current_partial_failures,
            "missing_completed": missing_completed, "thin_completed": thin_completed,
            "current_season": f"{current_start}/{str(current_start+1)[-2:]}", "quality": quality,
            "verified": failures == 0 and quality["bad_team"] == 0 and quality["bad_score"] == 0 and quality["duplicate_keys"] == 0,
            "promoted": False,
        }

        # Last-known-good protection: a transient source outage must not overwrite a healthier warehouse.
        old_meta = None
        if os.path.exists(HISTORY_META_FILE):
            try:
                with open(HISTORY_META_FILE, "r", encoding="utf-8") as h:
                    old_meta = json.load(h)
            except Exception:
                old_meta = None
        worse_than_existing = False
        if old_meta and os.path.exists(HISTORY_FILE):
            old_matches = int(old_meta.get("matches") or 0)
            old_failures = int(old_meta.get("critical_failures") or 0)
            old_quality = float((old_meta.get("quality") or {}).get("quality_score") or 0)
            if old_matches and len(all_rows) < old_matches * 0.95:
                worse_than_existing = True
            if failures > old_failures and len(all_rows) <= old_matches:
                worse_than_existing = True
            # A much larger warehouse can legitimately have lower optional-field
            # coverage (for example HT scores in extra leagues). Reject a quality
            # drop only when the replacement is not materially expanding coverage.
            if old_quality and len(all_rows) <= old_matches * 1.05 and quality["quality_score"] + 0.03 < old_quality:
                worse_than_existing = True

        if worse_than_existing:
            meta["ok"] = False
            meta["promoted"] = False
            meta["preserved_previous"] = True
            meta["detail"] = "new_build_failed_quality_gate"
            meta["previous_matches"] = int((old_meta or {}).get("matches") or 0)
            return meta

        with open(HISTORY_FILE+".tmp", "w", encoding="utf-8") as h:
            json.dump(all_rows, h, ensure_ascii=False, separators=(",",":"))
        os.replace(HISTORY_FILE+".tmp", HISTORY_FILE)
        meta["promoted"] = True
        with open(HISTORY_META_FILE, "w", encoding="utf-8") as h:
            json.dump(meta, h, ensure_ascii=False, indent=2)
        return meta
    finally:
        HISTORY_LOCK = False

@app.get("/history")
def history():
    if not os.path.exists(HISTORY_FILE):
        return jsonify({"ok": False, "error": "history_not_built"}), 404

    league = request.args.get("league", "").strip()
    if league:
        with open(HISTORY_FILE, "r", encoding="utf-8") as h:
            rows = [x for x in json.load(h) if x.get("league") == league]
        return jsonify({"ok": True, "matches": rows, "count": len(rows)})

    # The full warehouse is large on mobile. Avoid parsing/re-serializing the
    # 34 MB JSON array and cache a gzip representation keyed by file mtime.
    mtime = os.path.getmtime(HISTORY_FILE)
    if HISTORY_RESPONSE_CACHE.get("mtime") != mtime:
        with open(HISTORY_FILE, "rb") as h:
            raw = h.read()
        count = 0
        try:
            if os.path.exists(HISTORY_META_FILE):
                with open(HISTORY_META_FILE, "r", encoding="utf-8") as h:
                    count = int(json.load(h).get("matches") or 0)
        except Exception:
            count = 0
        payload = b'{"ok":true,"matches":' + raw + b',"count":' + str(count).encode("ascii") + b"}"
        HISTORY_RESPONSE_CACHE.update({
            "mtime": mtime,
            "plain": payload,
            "gzip": gzip.compress(payload, compresslevel=5),
            "count": count,
        })

    accepts_gzip = "gzip" in (request.headers.get("Accept-Encoding") or "").lower()
    body = HISTORY_RESPONSE_CACHE["gzip"] if accepts_gzip else HISTORY_RESPONSE_CACHE["plain"]
    resp = Response(body, mimetype="application/json")
    if accepts_gzip:
        resp.headers["Content-Encoding"] = "gzip"
    resp.headers["Vary"] = "Accept-Encoding"
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp

@app.get("/history/status")
def history_status():
    if not os.path.exists(HISTORY_META_FILE):
        return jsonify({"ok": False, "built": False})
    with open(HISTORY_META_FILE, "r", encoding="utf-8") as h:
        meta = json.load(h)
    meta["built"] = os.path.exists(HISTORY_FILE)
    return jsonify(meta)

@app.get("/history/ensure")
def history_ensure():
    """
    Non-blocking initializer for the historical warehouse.
    Returns immediately and builds in a daemon thread when the warehouse is missing.
    Safe to call repeatedly.
    """
    if os.path.exists(HISTORY_FILE) and os.path.exists(HISTORY_META_FILE):
        with open(HISTORY_META_FILE, "r", encoding="utf-8") as h:
            meta = json.load(h)
        return jsonify({"ok": True, "started": False, "built": True, "matches": meta.get("matches", 0),
                        "critical_failures": meta.get("critical_failures", 0)})

    if HISTORY_LOCK:
        return jsonify({"ok": True, "started": False, "built": False, "detail": "build_already_running"})

    def _job():
        try:
            build_history_10y()
        except Exception as e:
            try:
                os.makedirs(HISTORY_DIR, exist_ok=True)
                with open(HISTORY_META_FILE + ".error", "w", encoding="utf-8") as h:
                    h.write(str(e))
            except Exception:
                pass

    threading.Thread(target=_job, daemon=True, name="ters-kose-history-build").start()
    return jsonify({"ok": True, "started": True, "built": False})


def retry_history_gaps():
    global HISTORY_RETRY_LOCK
    if HISTORY_RETRY_LOCK:
        return {"ok": False, "detail": "retry_already_running"}
    HISTORY_RETRY_LOCK = True
    try:
        if not os.path.exists(HISTORY_META_FILE) or not os.path.exists(HISTORY_FILE):
            return {"ok": False, "detail": "history_not_built"}

        with open(HISTORY_META_FILE, "r", encoding="utf-8") as h:
            meta = json.load(h)
        with open(HISTORY_FILE, "r", encoding="utf-8") as h:
            rows = json.load(h)

        gaps = list(meta.get("missing_completed", []))
        recovered, failed = [], []
        for item in gaps:
            league = item.get("league")
            season = str(item.get("season") or "")
            code = _main_code_for_name(league)
            m = re.match(r"^(20\d{2})/", season)
            if not code or not m:
                failed.append({"league": league, "season": season, "error": "unsupported_gap"})
                continue
            y = int(m.group(1))
            new_rows, audit_item = _load_main_history_season(code, league, y)
            if new_rows:
                rows.extend(new_rows)
                recovered.append({"league": league, "season": season, "rows": len(new_rows), "source": audit_item.get("source", "live")})
            else:
                failed.append({"league": league, "season": season, "error": audit_item.get("error", "retry_failed")})

        if recovered:
            rows = _dedupe_history(rows)
            quality = _audit_history_rows(rows)

            # Recompute missing completed gaps from previous gap list minus recovered items.
            recovered_keys = {(x["league"], x["season"]) for x in recovered}
            remaining = [g for g in gaps if (g.get("league"), str(g.get("season") or "")) not in recovered_keys]
            # Preserve explicitly failed retry detail.
            fail_map = {(x["league"], x["season"]): x for x in failed}
            remaining = [
                {"league": g.get("league"), "season": g.get("season"),
                 "error": fail_map.get((g.get("league"), str(g.get("season") or "")), g).get("error", "")}
                for g in remaining
            ]

            meta["matches"] = len(rows)
            meta["quality"] = quality
            meta["missing_completed"] = remaining
            meta["critical_failures"] = len(remaining)
            meta["verified"] = (
                len(remaining) == 0 and quality["bad_team"] == 0 and
                quality["bad_score"] == 0 and quality["duplicate_keys"] == 0
            )
            meta["last_gap_retry_at"] = datetime.utcnow().isoformat() + "Z"
            meta["last_gap_retry_recovered"] = recovered
            meta["last_gap_retry_failed"] = failed
            meta["league_counts"] = {}
            for x in rows:
                lg = x.get("league", "")
                meta["league_counts"][lg] = meta["league_counts"].get(lg, 0) + 1

            with open(HISTORY_FILE + ".tmp", "w", encoding="utf-8") as h:
                json.dump(rows, h, ensure_ascii=False, separators=(",", ":"))
            os.replace(HISTORY_FILE + ".tmp", HISTORY_FILE)
            with open(HISTORY_META_FILE + ".tmp", "w", encoding="utf-8") as h:
                json.dump(meta, h, ensure_ascii=False, indent=2)
            os.replace(HISTORY_META_FILE + ".tmp", HISTORY_META_FILE)

        return {
            "ok": True,
            "attempted": len(gaps),
            "recovered": recovered,
            "failed": failed,
            "remaining": len(meta.get("missing_completed", [])) if recovered else len(gaps),
        }
    finally:
        HISTORY_RETRY_LOCK = False

@app.get("/history/gaps")
def history_gaps():
    if not os.path.exists(HISTORY_META_FILE):
        return jsonify({"ok": False, "built": False, "missing_completed": [], "thin_completed": []}), 404
    with open(HISTORY_META_FILE, "r", encoding="utf-8") as h:
        meta = json.load(h)
    return jsonify({
        "ok": True,
        "current_season": meta.get("current_season"),
        "missing_completed": meta.get("missing_completed", []),
        "thin_completed": meta.get("thin_completed", []),
        "critical_failures": meta.get("critical_failures", 0),
    })

@app.post("/history/retry-gaps")
def history_retry_gaps():
    token = request.headers.get("X-Build-Token", "")
    expected = os.environ.get("HISTORY_BUILD_TOKEN", "")
    if expected and token != expected:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    return jsonify(retry_history_gaps())

@app.post("/history/build")
def history_build():
    token = request.headers.get("X-Build-Token", "")
    expected = os.environ.get("HISTORY_BUILD_TOKEN", "")
    if expected and token != expected:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    return jsonify(build_history_10y())

@app.get("/leagues")
def leagues():
    rows = [{"code": code, "name": name} for code, name in ESPN_LEAGUES.items()]
    rows.sort(key=lambda x: x["name"])
    return jsonify({"ok": True, "leagues": rows, "count": len(rows)})

@app.get("/teams")
def teams():
    league = request.args.get("league", "").strip()
    codes = [league] if league in ESPN_LEAGUES else list(ESPN_LEAGUES.keys())
    cache_key = league or "__all__"
    cached = TEAM_CACHE.get(cache_key)
    if cached and time.time() - cached["saved_at"] < 21600:
        resp = jsonify(cached["payload"])
        resp.headers["X-TersKose-Cache"] = "hit"
        return resp
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
    payload = {"ok": True, "teams": out, "count": len(out), "errors": errors}
    TEAM_CACHE[cache_key] = {"saved_at": time.time(), "payload": payload}
    resp = jsonify(payload)
    resp.headers["X-TersKose-Cache"] = "miss"
    return resp

@app.get("/fixtures")
def fixtures():
    date = request.args.get("date", "").strip().replace("-", "")
    if len(date) != 8 or not date.isdigit():
        return jsonify({"error": "date YYYY-MM-DD gerekli"}), 400

    cached = FIXTURE_CACHE.get(date)
    if cached and time.time() - cached["saved_at"] < 300:
        resp = jsonify(cached["payload"])
        resp.headers["X-TersKose-Cache"] = "hit"
        return resp

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
    payload = {"ok": True, "date": date, "matches": all_matches, "count": len(all_matches), "errors": errors}
    FIXTURE_CACHE[date] = {"saved_at": time.time(), "payload": payload}
    if len(FIXTURE_CACHE) > 16:
        oldest = min(FIXTURE_CACHE, key=lambda k: FIXTURE_CACHE[k]["saved_at"])
        FIXTURE_CACHE.pop(oldest, None)
    resp = jsonify(payload)
    resp.headers["X-TersKose-Cache"] = "miss"
    return resp

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

def _auto_history_bootstrap():
    """Build the warehouse in the background after each cold start when the free instance has no persisted copy."""
    if os.environ.get("TERS_KOSE_AUTO_HISTORY", "1") == "0":
        return
    if os.path.exists(HISTORY_FILE) and os.path.exists(HISTORY_META_FILE):
        return
    def _job():
        # Give gunicorn a moment to bind the port before starting external data work.
        time.sleep(2)
        try:
            build_history_10y()
        except Exception:
            pass
    threading.Thread(target=_job, daemon=True, name="ters-kose-auto-history").start()

_auto_history_bootstrap()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
