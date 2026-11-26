"""SQLite accounts, sessions, friends and authoritative daily games."""
import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from daily import fresh, action
from api_config import allowed_origin

DB = os.environ.get('SUPOKU_DB', str(Path(__file__).parent / 'data/social.sqlite3'))
LOCK = threading.RLock()
ATTEMPTS = {}


@contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE COLLATE NOCASE,
          password TEXT NOT NULL, created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user INTEGER REFERENCES users(id) ON DELETE CASCADE,
          expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS friends(user INTEGER REFERENCES users(id) ON DELETE CASCADE,
          friend INTEGER REFERENCES users(id) ON DELETE CASCADE, PRIMARY KEY(user,friend));
        CREATE TABLE IF NOT EXISTS games(user INTEGER REFERENCES users(id) ON DELETE CASCADE, day TEXT,
          state TEXT NOT NULL, points INTEGER, filled INTEGER, finished INTEGER, PRIMARY KEY(user,day));
        CREATE INDEX IF NOT EXISTS scores ON games(day,points DESC) WHERE finished IS NOT NULL;
        ''')


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return salt + ':' + key


def check_password(password, stored):
    return secrets.compare_digest(password_hash(password, stored.split(':')[0]), stored)


def today():
    return datetime.now(timezone.utc).date().isoformat()


def stats(db, uid):
    games = db.execute('SELECT day,points,filled FROM games WHERE user=? AND finished IS NOT NULL ORDER BY day', (uid,)).fetchall()
    wins = [g['day'] for g in games if g['filled'] == 9]
    best = run = 0
    previous = None
    for day in wins:
        date = datetime.fromisoformat(day).date()
        run = run + 1 if previous and date - previous == timedelta(days=1) else 1
        previous = date
        best = max(best, run)
    current = run if previous and (datetime.fromisoformat(today()).date() - previous).days <= 1 else 0
    if games and games[-1]['day'] == today() and games[-1]['filled'] != 9:
        current = 0
    return dict(played=len(games), wins=len(wins), currentStreak=current, bestStreak=best,
                bestScore=max((g['points'] for g in games), default=0),
                history=[dict(g) for g in games])


def handle(h, method):
    path = urlsplit(h.path).path
    if not path.startswith('/api/social/'):
        return False
    cookie = None

    def send(obj, status=200):
        body = json.dumps(obj).encode()
        h.send_response(status)
        h.send_header('Content-Type', 'application/json; charset=utf-8')
        h.send_header('Cache-Control', 'no-store')
        h.send_header('X-Content-Type-Options', 'nosniff')
        h.send_header('Content-Length', str(len(body)))
        if cookie:
            h.send_header('Set-Cookie', cookie)
        h.end_headers()
        h.wfile.write(body)

    try:
        req = {}
        if method != 'GET':
            if not allowed_origin(h.headers):
                send({'error': 'Cross-site request rejected.'}, 403)
                return True
            if h.headers.get('X-SuPoku-Request') != '1' or h.headers.get_content_type() != 'application/json':
                send({'error': 'JSON and the SuPoku request header are required.'}, 403)
                return True
            length = int(h.headers.get('Content-Length', '0'))
            if not 0 < length <= 8192:
                raise ValueError('Invalid request size.')
            req = json.loads(h.rfile.read(length))
            if not isinstance(req, dict):
                raise ValueError('Expected an object.')
        jar = SimpleCookie()
        jar.load(h.headers.get('Cookie', ''))
        token = jar['supoku_session'].value if 'supoku_session' in jar else ''
        bearer = h.headers.get('X-SuPoku-Auth') == 'bearer'
        if bearer:
            authorization = h.headers.get('Authorization', '')
            token = authorization[7:] if authorization.startswith('Bearer ') else ''
        with LOCK, connect() as db:
            db.execute('DELETE FROM sessions WHERE expires < ?', (int(time.time()),))
            user = db.execute('SELECT users.id,username FROM sessions JOIN users ON users.id=sessions.user WHERE token=?', (digest(token),)).fetchone()
            endpoint = path.removeprefix('/api/social/')
            if endpoint in ('register', 'login') and method == 'POST':
                ip = h.client_address[0]
                now = time.time()
                for key in list(ATTEMPTS):
                    if not ATTEMPTS[key] or ATTEMPTS[key][-1] < now - 900:
                        del ATTEMPTS[key]
                recent = [t for t in ATTEMPTS.get(ip, []) if t > now - 900]
                if len(recent) >= 20:
                    send({'error': 'Too many sign-in attempts. Try again in 15 minutes.'}, 429)
                    return True
                ATTEMPTS[ip] = recent + [now]
                username, password = req.get('username', ''), req.get('password', '')
                if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{3,20}', username):
                    raise ValueError('Use 3–20 letters, numbers, dots, hyphens or underscores for your username.')
                if not isinstance(password, str) or not 8 <= len(password) <= 128:
                    raise ValueError('Use a password with 8–128 characters.')
                existing = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
                if endpoint == 'register':
                    if existing:
                        raise ValueError('That username is taken.')
                    uid = db.execute('INSERT INTO users(username,password,created) VALUES(?,?,?)', (username, password_hash(password), int(now))).lastrowid
                else:
                    stored = existing['password'] if existing else password_hash('dummy-password', '0'*32)
                    valid = check_password(password, stored)
                    if not existing or not valid:
                        raise ValueError('Username or password is incorrect.')
                    uid = existing['id']
                    username = existing['username']
                db.execute('DELETE FROM sessions WHERE token=?', (digest(token),))
                token = secrets.token_urlsafe(32)
                db.execute('INSERT INTO sessions VALUES(?,?,?)', (digest(token), uid, int(now)+2592000))
                secure = '; Secure' if (os.environ.get('SUPOKU_ORIGIN') or os.environ.get('RENDER_EXTERNAL_URL', '')).startswith('https://') else ''
                if bearer:
                    send({'user': {'username': username}, 'token': token})
                else:
                    cookie = 'supoku_session=' + token + '; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000' + secure
                    send({'user': {'username': username}})
            elif endpoint == 'me' and method == 'GET':
                send({'user': {'username': user['username']} if user else None})
            elif endpoint == 'leaderboard' and method == 'GET':
                query = parse_qs(urlsplit(h.path).query)
                scope = query.get('scope', ['today'])[0]
                if scope not in ('today', 'all', 'friends', 'streaks'):
                    raise ValueError('Unknown leaderboard.')
                if scope == 'friends' and not user:
                    send({'error': 'Sign in to see your friends leaderboard.'}, 401)
                    return True
                clause, args = '', []
                if scope in ('today', 'friends'):
                    clause = ' AND g.day=?'
                    args.append(today())
                if scope == 'friends':
                    clause += ' AND (u.id=? OR u.id IN (SELECT friend FROM friends WHERE user=?))'
                    args.extend([user['id'], user['id']])
                rows = db.execute('SELECT u.id,u.username,MAX(g.points) AS points FROM users u JOIN games g ON g.user=u.id WHERE g.finished IS NOT NULL' + clause + ' GROUP BY u.id ORDER BY points DESC,u.username COLLATE NOCASE', args).fetchall()
                entries = []
                for row in rows:
                    st = stats(db, row['id'])
                    st.pop('history')
                    entries.append(dict(username=row['username'], points=row['points'], **st))
                if scope == 'streaks':
                    entries.sort(key=lambda r: (-r['bestStreak'], -r['currentStreak'], -r['wins'], r['username'].lower()))
                send({'day': today(), 'entries': entries[:100]})
            elif not user:
                send({'error': 'Sign in to use this feature.'}, 401)
            elif endpoint == 'logout' and method == 'POST':
                db.execute('DELETE FROM sessions WHERE token=?', (digest(token),))
                cookie = 'supoku_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0'
                send({'ok': True})
            elif endpoint == 'account' and method == 'DELETE':
                stored = db.execute('SELECT password FROM users WHERE id=?', (user['id'],)).fetchone()[0]
                password = req.get('password', '')
                if not isinstance(password, str) or len(password) > 128 or not check_password(password, stored):
                    raise ValueError('Enter your current password to delete your account.')
                db.execute('DELETE FROM users WHERE id=?', (user['id'],))
                cookie = 'supoku_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0'
                send({'ok': True})
            elif endpoint == 'stats' and method == 'GET':
                send(stats(db, user['id']))
            elif endpoint == 'friends':
                if method in ('POST', 'DELETE'):
                    name = req.get('username')
                    if not isinstance(name, str):
                        raise ValueError('Enter a username.')
                    friend = db.execute('SELECT id FROM users WHERE username=?', (name,)).fetchone()
                    if not friend or friend['id'] == user['id']:
                        raise ValueError('Choose another existing player.')
                    if method == 'POST':
                        if db.execute('SELECT count(*) FROM friends WHERE user=?', (user['id'],)).fetchone()[0] >= 200:
                            raise ValueError('You can follow up to 200 friends.')
                        db.execute('INSERT OR IGNORE INTO friends VALUES(?,?)', (user['id'], friend['id']))
                    else:
                        db.execute('DELETE FROM friends WHERE user=? AND friend=?', (user['id'], friend['id']))
                elif method != 'GET':
                    raise ValueError('Unsupported method.')
                friends = db.execute('SELECT u.id,u.username FROM users u JOIN friends f ON f.friend=u.id WHERE f.user=? ORDER BY u.username', (user['id'],)).fetchall()
                entries = []
                for friend in friends:
                    st = stats(db, friend['id'])
                    st.pop('history')
                    entries.append(dict(username=friend['username'], **st))
                send({'entries': entries})
            elif endpoint == 'game' and method in ('GET', 'POST'):
                day = today()
                row = db.execute('SELECT state FROM games WHERE user=? AND day=?', (user['id'], day)).fetchone()
                game = json.loads(row[0]) if row else fresh(day)
                if method == 'POST':
                    if req.get('day') != day:
                        raise ValueError('A new UTC day has started. Reload the daily puzzle.')
                    action(game, req)
                    if req.get('action') == 'guess' and game['cells'][req['cell']] == req.get('pokemon'):
                        i, pid = req['cell'], req['pokemon']
                        prior = db.execute('SELECT state FROM games WHERE day=? AND user<>?', (day, user['id'])).fetchall()
                        answers = [json.loads(r[0])['cells'][i] for r in prior]
                        answers = [p for p in answers if p is not None]
                        game.setdefault('rarities', [None]*9)[i] = {
                            'percent': 100 * answers.count(pid) / len(answers) if answers else 0,
                            'first': pid not in answers}
                filled = sum(p is not None for p in game['cells'])
                db.execute('INSERT INTO games VALUES(?,?,?,?,?,?) ON CONFLICT(user,day) DO UPDATE SET state=excluded.state,points=excluded.points,filled=excluded.filled,finished=COALESCE(games.finished,excluded.finished)',
                           (user['id'], day, json.dumps(game), game['points'], filled, int(time.time()) if game['over'] else None))
                send({'game': game})
            else:
                send({'error': 'No such endpoint.'}, 404)
    except (ValueError, TypeError) as exc:
        send({'error': str(exc)}, 400)
    except sqlite3.Error:
        send({'error': 'The account service is unavailable. Please try again.'}, 503)
    return True


initialize()
