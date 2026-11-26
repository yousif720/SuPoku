"""Exact-origin allowlist shared by local and production HTTP adapters."""
import os


def allowed_origin(headers):
    origin = headers.get('Origin')
    if not origin:
        return headers.get('Sec-Fetch-Site') != 'cross-site'
    configured = {v.strip().rstrip('/') for v in os.environ.get('SUPOKU_ALLOWED_ORIGINS', '').split(',') if v.strip()}
    own = os.environ.get('SUPOKU_ORIGIN') or os.environ.get('RENDER_EXTERNAL_URL') or 'http://' + headers.get('Host', '')
    return origin in configured or origin == own


def cors_headers(headers):
    origin = headers.get('Origin')
    if origin and allowed_origin(headers):
        return [('Access-Control-Allow-Origin', origin), ('Vary', 'Origin'),
                ('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS'),
                ('Access-Control-Allow-Headers', 'Content-Type, X-SuPoku-Request, X-SuPoku-Auth, Authorization'),
                ('Access-Control-Max-Age', '600')]
    return []
