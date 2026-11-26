"""Production API entry point for Gunicorn on Render; serves no workspace files."""
import io
import json
from email.message import Message
from http import HTTPStatus

from api_config import cors_headers
from server import Handler
import social


class APIHandler(Handler):
    def __init__(self, environ):
        self.path = environ.get('PATH_INFO', '/')
        if environ.get('QUERY_STRING'):
            self.path += '?' + environ['QUERY_STRING']
        self.headers = Message()
        for key, value in environ.items():
            if key.startswith('HTTP_'):
                self.headers[key[5:].replace('_', '-')] = value
        self.headers['Content-Type'] = environ.get('CONTENT_TYPE', '')
        self.headers['Content-Length'] = environ.get('CONTENT_LENGTH', '0') or '0'
        self.rfile = environ['wsgi.input']
        self.wfile = io.BytesIO()
        self.client_address = (environ.get('REMOTE_ADDR', ''), 0)
        self.status = 200
        self.response_headers = []

    def send_response(self, code, message=None):
        self.status = code

    def send_header(self, key, value):
        self.response_headers.append((key, str(value)))

    def end_headers(self):
        self.response_headers.extend(cors_headers(self.headers))
        self.response_headers.append(('X-Content-Type-Options', 'nosniff'))

    def send_error(self, code, message=None, explain=None):
        self._send_json({'error': message or HTTPStatus(code).phrase}, code)

    def public_path(self):
        self.send_error(404)
        return False


def application(environ, start_response):
    h = APIHandler(environ)
    method = environ.get('REQUEST_METHOD', 'GET')
    try:
        length = int(h.headers.get('Content-Length', '0'))
        if not 0 <= length <= 8192:
            h.send_error(413)
        elif h.path == '/api/health' and method in ('GET', 'HEAD'):
            with social.connect() as db:
                db.execute('SELECT 1 FROM users LIMIT 1').fetchone()
            h._send_json({'ok': True})
        elif method in ('GET', 'POST', 'DELETE', 'OPTIONS') and h.path.startswith('/api/'):
            getattr(h, 'do_' + method)()
        else:
            h.send_error(404)
    except ValueError:
        h.send_error(400, 'Invalid request.')
    except Exception:
        # Never return exception details, database paths or secrets to callers.
        h.status = 503
        h.response_headers = [('Content-Type', 'application/json'), ('Cache-Control', 'no-store')]
        h.response_headers.extend(cors_headers(h.headers))
        h.wfile = io.BytesIO(json.dumps({'error': 'Service unavailable. Please try again.'}).encode())
    body = h.wfile.getvalue()
    if not any(k.lower() == 'content-length' for k, _ in h.response_headers):
        h.response_headers.append(('Content-Length', str(len(body))))
    start_response(f'{h.status} {HTTPStatus(h.status).phrase}', h.response_headers)
    return [b'' if method == 'HEAD' else body]
