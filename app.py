from flask import Flask, request, Response, jsonify, send_from_directory
import requests
import time
from urllib.parse import urlparse

app = Flask(__name__)

ALLOWED_HOSTS = {"www.football-data.co.uk", "football-data.co.uk"}
APP_VERSION = "3.2"
SOURCE_CACHE = {}

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
