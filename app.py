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

@app.get("/proxy")
def proxy():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "url gerekli"}), 400

    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        return jsonify({"error": "izin verilmeyen kaynak"}), 403

    try:
        r = requests.get(
            url,
            timeout=25,
            headers={
                "User-Agent": "Mozilla/5.0 TersKose/1.0",
                "Accept": "text/csv,text/plain,*/*",
            },
        )
        r.raise_for_status()
    except requests.RequestException as e:
        return jsonify({"error": "veri kaynagina ulasilamadi", "detail": str(e)}), 502

    content_type = r.headers.get("Content-Type", "text/plain; charset=utf-8")
    return Response(r.content, status=200, content_type=content_type)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
