import json
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit
from pathlib import Path
import social
from api_config import allowed_origin, cors_headers

ROOT = os.path.dirname(os.path.abspath(__file__))
STORE = os.environ.get('SUPOKU_PICKS', os.path.join(ROOT, "data", "picks.json"))
LOCK = threading.Lock()


def load():
    try:
        with open(STORE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save(data):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    os.replace(tmp, STORE)


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        for key, value in cors_headers(self.headers):
            self.send_header(key, value)
        super().end_headers()

    def do_OPTIONS(self):
        if not self.path.startswith('/api/') or not allowed_origin(self.headers):
            self._send_json({'error': 'Origin not allowed.'}, 403)
            return
        self.send_response(204)
        self.end_headers()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, fmt, *args):
        if not self.path.startswith("/api/"):
            return
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if social.handle(self, 'GET'):
            return
        if self.path.startswith("/api/stats"):
            with LOCK:
                data = load()
            self._send_json({
                "squares": len(data),
                "picks": sum(sum(t.values()) for t in data.values()),
            })
            return
        if self.path.startswith("/api/answers"):
            # Read-only tally for one square, shown after a game ends. Counts
            # only, keyed by Pokemon id; no player information is stored.
            square = parse_qs(urlsplit(self.path).query).get("square", [""])[0][:200]
            if not square:
                self._send_json({"error": "square is required"}, 400)
                return
            with LOCK:
                tally = dict(load().get(square, {}))
            self._send_json({"picks": tally, "total": sum(tally.values())})
            return
        if self.public_path():
            super().do_GET()

    def public_path(self):
        path = unquote(urlsplit(self.path).path).lstrip('/') or 'index.html'
        target = (Path(ROOT) / path).resolve()
        root = Path(ROOT).resolve()
        allowed = (target.parent == root and target.suffix in ('.html', '.css', '.js')) or path in ('data/pokedex.json', 'robots.txt', 'sitemap.xml', 'ads.txt') or target.is_relative_to(root / 'assets')
        if not target.is_relative_to(root) or not target.is_file() or not allowed:
            self.send_error(404)
            return False
        return True

    def do_HEAD(self):
        if self.public_path():
            super().do_HEAD()

    def do_DELETE(self):
        if not social.handle(self, 'DELETE'):
            self.send_error(404)

    def do_POST(self):
        if not allowed_origin(self.headers):
            self._send_json({'error': 'Origin not allowed.'}, 403)
            return
        if social.handle(self, 'POST'):
            return
        if self.path != "/api/pick":
            self.send_error(404, "no such endpoint")
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_json({'error': 'Invalid request size.'}, 400)
            return
        if not 0 <= length <= 4096:
            self._send_json({"error": "payload too large"}, 413)
            return
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(req, dict):
                raise ValueError('Expected an object')
        except ValueError:
            self._send_json({"error": "invalid json"}, 400)
            return

        square = str(req.get("square", ""))[:200]
        pick = str(req.get("pick", ""))[:20]
        if not square or not pick:
            self._send_json({"error": "square and pick are required"}, 400)
            return

        with LOCK:
            data = load()
            tally = data.setdefault(square, {})

            if req.get("undo"):
                if tally.get(pick, 0) > 1:
                    tally[pick] -= 1
                else:
                    tally.pop(pick, None)
                if not tally:
                    data.pop(square, None)
                save(data)
                self._send_json({"ok": True})
                return

            # Snapshot before recording: the player's own answer is excluded
            # from the percentage they see, and included for everyone after.
            others = sum(tally.values())
            mine_before = tally.get(pick, 0)
            tally[pick] = mine_before + 1
            save(data)
            self._send_json({"count": mine_before, "total": others})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
    print("SuPoku on http://localhost:%d  (picks in data/picks.json)" % port)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
