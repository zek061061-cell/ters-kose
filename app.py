from flask import Flask, request, Response, jsonify
import requests
from urllib.parse import urlparse

app = Flask(__name__)

ALLOWED_HOSTS = {"www.football-data.co.uk", "football-data.co.uk"}

@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

@app.get("/")
def home():
    return jsonify({"ok": True, "service": "Ters Kose data proxy"})

@app.get("/health")
def health():
    return jsonify({"ok": True})

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
        try:
            r = requests.get(candidate, timeout=30, headers=headers, allow_redirects=True)
            if r.ok and r.content:
                return r
            last_error = requests.HTTPError(f"{r.status_code} Server Error for url: {candidate}")
        except requests.RequestException as e:
            last_error = e
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
    except requests.RequestException as e:
        return jsonify({"error": "veri kaynagina ulasilamadi", "detail": str(e)}), 502

    return Response(r.content, status=200, content_type=r.headers.get("Content-Type", "text/csv; charset=utf-8"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
