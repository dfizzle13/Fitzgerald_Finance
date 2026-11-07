from contextlib import closing
import http.cookiejar
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Server'))
from main import FinanceHTTPServer

DATA = {'budgets': [], 'transactions': [], 'incomes': [], 'categories': [], 'bills': [], 'monthlyArchives': [], 'theme': 'evergreen'}
PASSWORD = 'test-household-password'

class Client:
    def __init__(self, url):
        self.url, self.csrf = url, ''
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(self, path, method='GET', data=None, csrf=True):
        headers = {'Content-Type': 'application/json', 'X-Finance-Request': '1'}
        if csrf:
            headers['X-CSRF-Token'] = self.csrf
        request = urllib.request.Request(self.url + path, data=None if data is None else json.dumps(data).encode(), method=method, headers=headers)
        try:
            response = self.opener.open(request)
        except urllib.error.HTTPError as error:
            response = error
        raw = response.read()
        response.close()
        result = json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw.decode()
        if isinstance(result, dict) and 'csrf' in result:
            self.csrf = result['csrf']
        return response.status, result

class HouseholdServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'finance.sqlite3'
        self.server = FinanceHTTPServer(('127.0.0.1', 0), self.path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
        self.admin = Client(self.url)
        status, result = self.admin.call('/api/setup', 'POST', {'username': 'householdAdmin', 'password': PASSWORD, 'data': DATA})
        self.assertEqual(status, 201)
        self.assertEqual(result['user']['role'], 'admin')
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()
    def member(self):
        self.assertEqual(self.admin.call('/api/users', 'POST', {'username': 'spouse', 'password': PASSWORD})[0], 201)
        member = Client(self.url)
        self.assertEqual(member.call('/api/login', 'POST', {'username': 'spouse', 'password': PASSWORD})[0], 200)
        return member
    def test_two_accounts_share_data_and_stale_writes_are_rejected(self):
        member = self.member()
        data = dict(DATA, transactions=[{'id': 'receipt', 'date': '2026-11-07', 'amount': 12.50}])
        status, saved = self.admin.call('/api/state', 'PUT', {'revision': 1, 'data': data})
        self.assertEqual(status, 200)
        self.assertEqual(member.call('/api/state')[1]['data']['transactions'][0]['amount'], 12.50)
        status, conflict = member.call('/api/state', 'PUT', {'revision': 1, 'data': DATA})
        self.assertEqual(status, 409)
        self.assertEqual(conflict['revision'], saved['revision'])
        self.assertEqual(self.admin.call('/api/state')[1]['data']['transactions'], data['transactions'])
        with closing(sqlite3.connect(self.path)) as con:
            self.assertEqual(json.loads(con.execute('SELECT data FROM household').fetchone()[0])['transactions'], data['transactions'])
        self.assertTrue(list((self.path.parent / 'backups').glob('*.sqlite3')))
    def test_auth_csrf_roles_password_and_logout(self):
        anonymous = Client(self.url)
        self.assertEqual(anonymous.call('/api/state')[0], 401)
        self.assertEqual(anonymous.call('/api/setup', 'POST', {'username': 'attacker', 'password': PASSWORD, 'data': DATA})[0], 409)
        self.assertEqual(self.admin.call('/api/state', 'PUT', {'revision': 1, 'data': DATA}, csrf=False)[0], 403)
        member = self.member()
        self.assertEqual(member.call('/api/users')[0], 403)
        self.assertEqual(member.call('/api/users', 'POST', {'username': 'stranger', 'password': PASSWORD})[0], 403)
        self.assertEqual(member.call('/api/password', 'POST', {'current': PASSWORD, 'password': 'a-new-password-123'})[0], 200)
        self.assertEqual(anonymous.call('/api/login', 'POST', {'username': 'spouse', 'password': PASSWORD})[0], 401)
        self.assertEqual(anonymous.call('/api/login', 'POST', {'username': 'spouse', 'password': 'a-new-password-123'})[0], 200)
        self.assertEqual(member.call('/api/logout', 'POST', {})[0], 200)
        self.assertEqual(member.call('/api/state')[0], 401)
    def test_only_app_files_are_served_and_hosted_mode_is_explicit(self):
        anonymous = Client(self.url)
        for path in ('/Database/finance.sqlite3', '/Server/main.py', '/.git/config', '/../Database/finance.sqlite3'):
            self.assertEqual(anonymous.call(path)[0], 404)
        status, html = anonymous.call('/')
        self.assertEqual(status, 200)
        self.assertIn('window.FITZGERALD_SHARED=true', html)
        self.assertNotIn('password_hash', html)
        self.assertEqual(anonymous.call('/shared-client.js')[0], 200)
        headers = {'Content-Type': 'application/json', 'X-Finance-Request': '1', 'Origin': 'https://another-site.example'}
        request = urllib.request.Request(self.url + '/api/login', data=b'{}', headers=headers)
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 403)
    def test_unsafe_data_and_untrusted_host_are_rejected(self):
        for row in ({'id': '\" onclick=bad', 'date': '2026-11-07', 'amount': 10}, {'id': 'bad', 'date': 'not-a-date', 'amount': 10}, {'id': 'bad', 'date': '2026-11-07', 'amount': -1}):
            self.assertEqual(self.admin.call('/api/state', 'PUT', {'revision': 1, 'data': dict(DATA, transactions=[row])})[0], 400)
        request = urllib.request.Request(self.url + '/api/status', headers={'Host': 'untrusted.example'})
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 403)
    def test_hosted_app_integration(self):
        result = subprocess.run(['node', 'tests/hosted-app.test.cjs', self.url], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout)
    def test_data_validation_and_password_hashing(self):
        self.assertEqual(self.admin.call('/api/state', 'PUT', {'revision': 1, 'data': {'budgets': 'wrong'}})[0], 400)
        self.assertEqual(self.admin.call('/api/users', 'POST', {'username': 'spouse', 'password': 'short'})[0], 400)
        with closing(sqlite3.connect(self.path)) as con:
            account = con.execute('SELECT salt,password_hash FROM accounts').fetchone()
            self.assertNotEqual(account[1], PASSWORD)
            self.assertEqual(len(account[0]), 32)
            self.assertNotIn(PASSWORD, self.path.read_bytes().decode('utf-8', errors='ignore'))

if __name__ == '__main__':
    unittest.main()
