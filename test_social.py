"""Run with python -m unittest test_social. Uses a temporary database only."""
import json
import os
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import http.cookiejar
import io
from unittest.mock import patch
from datetime import date, timedelta

TEMP = tempfile.TemporaryDirectory()
os.environ['SUPOKU_DB'] = os.path.join(TEMP.name, 'test.sqlite3')
import social
from server import Handler, ThreadingHTTPServer
from daily import CATS, fresh, action


class SocialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        TEMP.cleanup()

    def client(self):
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, client, path, method='GET', body=None, headers=None):
        req = urllib.request.Request(self.url + path, data=json.dumps(body or {}).encode() if method != 'GET' else None,
                                     method=method, headers=headers or {'Content-Type':'application/json', 'X-SuPoku-Request':'1'})
        try:
            response = client.open(req)
        except urllib.error.HTTPError as e:
            response = e
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if 'application/json' in response.headers.get('Content-Type','') else raw

    def test_account_game_friends(self):
        a,b,guest = self.client(),self.client(),self.client()
        for client,name in [(a,'Player_A'),(b,'Player_B')]:
            self.assertEqual(self.call(client,'/api/social/register','POST',dict(username=name,password='good-test-password'))[0],200)
        self.assertEqual(self.call(guest,'/api/social/stats')[0],401)
        self.assertEqual(self.call(guest,'/api/social/register','POST',dict(username='player_a',password='good-test-password'))[0],400)
        self.assertEqual(self.call(a,'/api/social/friends','POST',dict(username='Player_B'))[0],200)
        self.assertEqual(len(self.call(a,'/api/social/friends')[1]['entries']),1)
        self.assertEqual(self.call(b,'/api/social/friends')[1]['entries'],[])
        self.assertEqual(self.call(a,'/api/social/game','POST',dict(points=999999))[0],400)
        game = self.call(a,'/api/social/game')[1]['game']
        for i in range(9):
            pid = next(p for p in CATS[game['rows'][i//3]]['ids'] & CATS[game['cols'][i%3]]['ids'] if p not in game['cells'])
            status,result = self.call(a,'/api/social/game','POST',dict(action='guess',cell=i,pokemon=pid,day=game['day'],revision=game['revision']))
            self.assertEqual(status,200,result)
            game = result['game']
        self.assertTrue(game['over'])
        self.assertEqual(game['points'],900)
        self.assertEqual(self.call(a,'/api/social/game','POST',dict(action='undo',cell=0,day=game['day'],revision=game['revision']))[0],400)
        self.assertEqual(self.call(a,'/api/social/stats')[1]['played'],1)
        self.assertEqual(self.call(guest,'/api/social/leaderboard')[1]['entries'][0]['points'],900)
        self.call(a,'/api/social/logout','POST')
        self.assertEqual(self.call(a,'/api/social/me')[1]['user'],None)
        self.assertEqual(self.call(a,'/api/social/login','POST',dict(username='PLAYER_A',password='wrong-password'))[0],400)
        self.assertEqual(self.call(a,'/api/social/login','POST',dict(username='PLAYER_A',password='good-test-password'))[0],200)
        self.assertEqual(self.call(a,'/api/social/game')[1]['game'],game)
        self.assertEqual(self.call(a,'/api/social/account','DELETE',dict(password='wrong-password'))[0],400)
        self.assertEqual(self.call(a,'/api/social/account','DELETE',dict(password='good-test-password'))[0],200)
        self.assertEqual(self.call(guest,'/api/social/leaderboard')[1]['entries'],[])

    def test_static_and_csrf(self):
        c = self.client()
        for path in ['/data/social.sqlite3','/social.py','/server.py','/data/picks.json','/assets/../server.py','/data/']:
            self.assertEqual(self.call(c,path)[0],404,path)
        self.assertEqual(self.call(c,'/api/social/register','POST',{}, {'Content-Type':'application/json','X-SuPoku-Request':'1','Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.call(c,'/api/social/register','POST',{}, {'Content-Type':'application/json'})[0],403)
        self.assertEqual(self.call(c,'/index.html')[0],200)

    def test_rules_and_revision(self):
        g = fresh('2026-09-07')
        wrong = next(p for p in social.fresh.__globals__['POKEMON'] if p not in CATS[g['rows'][0]]['ids'] & CATS[g['cols'][0]]['ids'])
        action(g,dict(action='guess',cell=0,pokemon=wrong,revision=0))
        self.assertEqual(g['guesses'],9)
        action(g,dict(action='guess',cell=0,pokemon=wrong,revision=1))
        self.assertEqual(g['guesses'],8)
        with self.assertRaises(ValueError):
            action(g,dict(action='undo',cell=0,revision=0))
        action(g,dict(action='undo',cell=0,revision=2))
        self.assertEqual(g['guesses'],9)
        self.assertEqual(g['mistakes'],2)
        with self.assertRaises(ValueError):
            action(g,dict(action='undo',cell=0,revision=3))

    def test_loss_breaks_streak(self):
        with social.connect() as db:
            uid = db.execute('INSERT INTO users(username,password,created) VALUES(?,?,0)', ('Streak_Test','unused')).lastrowid
            day = date.fromisoformat(social.today())
            for ago,filled in [(2,9),(1,9),(0,3)]:
                db.execute('INSERT INTO games VALUES(?,?,?,?,?,?)', (uid,(day-timedelta(days=ago)).isoformat(),'{}',filled*100,filled,1))
            st = social.stats(db,uid)
            self.assertEqual(st['bestStreak'],2)
            self.assertEqual(st['currentStreak'],0)
            db.execute('DELETE FROM users WHERE id=?',(uid,))

    def test_render_adapter_and_cross_origin_session(self):
        from wsgi import application
        origin = 'https://example-player.github.io'
        def call(path, method='GET', body=None, token='', site=origin):
            raw = json.dumps(body or {}).encode()
            env = {'PATH_INFO':path, 'REQUEST_METHOD':method, 'HTTP_HOST':'example-api.onrender.com',
                   'HTTP_ORIGIN':site,'HTTP_SEC_FETCH_SITE':'cross-site','HTTP_X_SUPOKU_AUTH':'bearer',
                   'HTTP_X_SUPOKU_REQUEST':'1','CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw)),
                   'wsgi.input':io.BytesIO(raw), 'REMOTE_ADDR':'127.0.0.2'}
            if token:
                env['HTTP_AUTHORIZATION'] = 'Bearer ' + token
            response = {}
            def start(status, headers):
                response.update(status=int(status[:3]), headers=dict(headers))
            raw_response = b''.join(application(env,start))
            response['body'] = json.loads(raw_response) if raw_response else {}
            return response
        with patch.dict(os.environ, SUPOKU_ALLOWED_ORIGINS=origin, SUPOKU_ORIGIN='https://example-api.onrender.com'):
            self.assertEqual(call('/api/health')['status'],200)
            self.assertEqual(call('/data/social.sqlite3')['status'],404)
            preflight = call('/api/social/login','OPTIONS')
            self.assertEqual(preflight['status'],204)
            self.assertEqual(preflight['headers']['Access-Control-Allow-Origin'],origin)
            self.assertNotIn('Access-Control-Allow-Credentials',preflight['headers'])
            blocked = call('/api/social/login','POST',site='https://evil.example')
            self.assertEqual(blocked['status'],403)
            self.assertNotIn('Access-Control-Allow-Origin',blocked['headers'])
            register = call('/api/social/register','POST',dict(username='Cross_Host',password='test-cross-host-password'))
            self.assertEqual(register['status'],200,register)
            self.assertNotIn('Set-Cookie',register['headers'])
            token = register['body']['token']
            self.assertEqual(call('/api/social/me',token=token)['body']['user']['username'],'Cross_Host')
            self.assertIsNone(call('/api/social/me')['body']['user'])
            self.assertEqual(call('/api/social/account','DELETE',dict(password='test-cross-host-password'),token=token)['status'],200)
            self.assertIsNone(call('/api/social/me',token=token)['body']['user'])


if __name__ == '__main__':
    unittest.main()
