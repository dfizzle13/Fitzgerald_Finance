"""Private household finance server with device authentication."""
from contextlib import contextmanager, closing
from datetime import date as calendar_date
import ipaddress
import math
import socket
import device_auth
import account_admin
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
MAX_BODY = 8 * 1024 * 1024
SESSION_DAYS = 30

class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message

def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

def verify_password(con, account, password):
    legacy = con.execute('SELECT salt FROM legacy_account_auth WHERE account_id=?', (account['id'],)).fetchone() if account else None
    candidate = hashlib.sha256((legacy['salt'] + ':' + password).encode()).hexdigest() if legacy else password
    valid = hmac.compare_digest(password_hash(candidate, account['salt'] if account else '00' * 16), account['password_hash'] if account else '00' * 64)
    if valid and legacy:
        salt = secrets.token_hex(16)
        con.execute('UPDATE accounts SET salt=?,password_hash=? WHERE id=?', (salt, password_hash(password, salt), account['id']))
        con.execute('DELETE FROM legacy_account_auth WHERE account_id=?', (account['id'],))
    return bool(account and valid)

def validate_data(data):
    if not isinstance(data, dict):
        raise APIError(400, 'Invalid household data.')
    for key in ('budgets', 'transactions', 'incomes', 'categories', 'bills', 'monthlyArchives'):
        if not isinstance(data.get(key, []), list):
            raise APIError(400, 'Invalid ' + key + ' list.')
        if any(not isinstance(row, dict) for row in data.get(key, [])):
            raise APIError(400, 'Invalid ' + key + ' record.')
    for key in ('budgets', 'transactions', 'incomes'):
        if key not in data:
            raise APIError(400, 'Missing ' + key + '.')
    def valid_date(value):
        try:
            return isinstance(value, str) and calendar_date.fromisoformat(value).isoformat() == value
        except ValueError:
            return False
    for key in ('budgets', 'transactions', 'incomes', 'bills'):
        identifiers = set()
        for row in data.get(key, []):
            identifier = row.get('id')
            if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', identifier) or identifier in identifiers:
                raise APIError(400, 'Every ' + key + ' record needs a unique valid ID.')
            identifiers.add(identifier)
            if 'amount' in row and (type(row['amount']) not in (int, float) or not math.isfinite(row['amount']) or not 0 <= row['amount'] <= 1e12):
                raise APIError(400, 'Invalid monetary amount.')
            if key in ('transactions', 'incomes') and not valid_date(row.get('date')):
                raise APIError(400, 'Use a valid transaction date.')
            if key == 'transactions' and row.get('fundsTransfer') is not None:
                transfer = row['fundsTransfer']
                if (not isinstance(transfer, dict)
                        or not valid_date(transfer.get('date'))
                        or transfer['date'] > calendar_date.today().isoformat()
                        or type(transfer.get('amount')) not in (int, float)
                        or transfer['amount'] != row.get('amount')
                        or transfer.get('budgetId') != row.get('budgetId')
                        or transfer.get('purchaseDate') != row.get('date')
                        or ('source' in transfer and transfer['source'] not in ('budget', 'covered', 'slush'))
                        or (transfer.get('source') == 'budget' and not row.get('budgetId'))
                        or (transfer.get('source') in ('covered', 'slush') and bool(row.get('budgetId')))):
                    raise APIError(400, 'Transfer confirmation must match the purchase and use a valid transfer date.')
            if key == 'bills' and row.get('startDate') is not None and not valid_date(row['startDate']):
                raise APIError(400, 'Use a valid bill start date.')
            if key == 'budgets':
                if row.get('cadence') not in ('weekly', 'monthly', 'annual'):
                    raise APIError(400, 'Invalid budget cadence.')
                if row.get('recurrence', 'recurring') not in ('recurring', 'one-time') or (row.get('recurrence') == 'one-time' and not valid_date(row.get('budgetDate'))):
                    raise APIError(400, 'Choose recurring or a one-time budget with a valid date.')
                for entry in row.get('history', []):
                    if not isinstance(entry, dict) or not valid_date(entry.get('from')) or entry.get('cadence') not in ('weekly', 'monthly', 'annual') or type(entry.get('amount')) not in (int, float) or not math.isfinite(entry['amount']) or entry['amount'] < 0:
                        raise APIError(400, 'Invalid budget history.')
                    if entry.get('recurrence', 'recurring') not in ('recurring', 'one-time') or (entry.get('recurrence') == 'one-time' and not valid_date(entry.get('budgetDate'))):
                        raise APIError(400, 'Invalid budget recurrence history.')
    if data.get('activeBudgetMonth') and not valid_date(str(data['activeBudgetMonth']) + '-01'):
        raise APIError(400, 'Invalid active budget month.')
    # Device authenticator identifiers are never shared between phones.
    data = dict(data)
    data['biometric'] = {'enabled': False, 'id': None, 'failures': 0}
    return data

class FinanceHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, database, secure_cookie=False):
        self.database = Path(database).resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.secure_cookie = secure_cookie
        self.write_lock = threading.RLock()
        self.attempts = {}
        self.device_challenges = {}
        super().__init__(address, Handler)
        with self.connect() as con:
            con.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY, username TEXT UNIQUE COLLATE NOCASE,
                salt TEXT NOT NULL, password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','user')), created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS device_transfers (id TEXT PRIMARY KEY,digest TEXT NOT NULL,result TEXT NOT NULL,actor TEXT NOT NULL,created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS legacy_account_auth (account_id TEXT PRIMARY KEY, salt TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL,
                csrf TEXT NOT NULL, expires INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS household (
                id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL,
                data TEXT NOT NULL, updated_by TEXT, updated_at INTEGER NOT NULL);
            ''')
            device_auth.initialize(con)
    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.database, timeout=15)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()
    def backup(self):
        folder = self.database.parent / 'backups'
        folder.mkdir(exist_ok=True)
        destination = folder / ('finance-' + time.strftime('%Y-%m-%d') + '.sqlite3')
        temporary = destination.with_suffix('.tmp')
        with self.connect() as source, closing(sqlite3.connect(temporary)) as target:
            source.backup(target)
        temporary.replace(destination)
        for old in sorted(folder.glob('finance-*.sqlite3'))[:-14]:
            old.unlink()

class Handler(BaseHTTPRequestHandler):
    server_version = 'FitzgeraldFinance'
    def log_message(self, fmt, *args):
        # Do not log passwords, request bodies, or session cookies.
        print(time.strftime('%Y-%m-%d %H:%M:%S'), self.address_string(), fmt % args, flush=True)
    def send_json(self, status, value, cookie=None):
        payload = json.dumps(value, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        if urlsplit(self.path).path == '/api/status':
            self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(payload)
    def body(self):
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise APIError(400, 'Invalid request size.')
        if not 0 < size <= MAX_BODY:
            raise APIError(413, 'Request is empty or too large (8 MB maximum).')
        if self.headers.get_content_type() != 'application/json':
            raise APIError(415, 'JSON is required.')
        try:
            result = json.loads(self.rfile.read(size), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError, RecursionError):
            raise APIError(400, 'Invalid JSON.')
        if not isinstance(result, dict):
            raise APIError(400, 'An object is required.')
        return result
    def check_origin(self):
        if self.headers.get('X-Finance-Request') != '1':
            raise APIError(403, 'Use the finance app to make changes.')
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc.lower() != self.headers.get('Host', '').lower():
            raise APIError(403, 'Cross-site requests are not allowed.')
    def session(self, con, mutation=False):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie', ''))
            token = cookies['finance_session'].value
        except (KeyError, ValueError, CookieError):
            raise APIError(401, 'Please sign in.')
        row = con.execute('''SELECT a.id,a.username,a.role,a.created_at,s.csrf,s.token_hash
            FROM sessions s JOIN accounts a ON a.id=s.account_id
            WHERE s.token_hash=? AND s.expires>?''',
            (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
        if not row:
            raise APIError(401, 'Your session expired. Please sign in.')
        if mutation and not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), row['csrf']):
            raise APIError(403, 'Please refresh the app before saving.')
        return row
    def account(self, row):
        return {'id': row['id'], 'username': row['username'], 'role': row['role'], 'createdAt': row['created_at'] * 1000}
    def state(self, con):
        row = con.execute('SELECT * FROM household WHERE id=1').fetchone()
        return {'data': json.loads(row['data']), 'revision': row['revision']}
    def credentials(self, body):
        name, password = body.get('username', ''), body.get('password', '')
        if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,32}', name):
            raise APIError(400, 'Username must be 3–32 letters, numbers, dots, underscores or hyphens.')
        if not isinstance(password, str) or not 12 <= len(password) <= 256:
            raise APIError(400, 'Use a password containing 12–256 characters.')
        return name, password
    def create_account(self, con, body, role='user'):
        name, password = self.credentials(body)
        salt, account_id = secrets.token_hex(16), secrets.token_hex(16)
        try:
            con.execute('INSERT INTO accounts VALUES (?,?,?,?,?,?)',
                (account_id, name, salt, password_hash(password, salt), role, int(time.time())))
        except sqlite3.IntegrityError:
            raise APIError(409, 'That username already exists.')
        return con.execute('SELECT * FROM accounts WHERE id=?', (account_id,)).fetchone()
    def new_session(self, con, account):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        con.execute('DELETE FROM sessions WHERE expires<=?', (int(time.time()),))
        con.execute('INSERT INTO sessions VALUES (?,?,?,?)',
            (hashlib.sha256(token.encode()).hexdigest(), account['id'], csrf, int(time.time()) + SESSION_DAYS * 86400))
        cookie = 'finance_session=' + token + '; Path=/; HttpOnly; SameSite=Strict; Max-Age=' + str(SESSION_DAYS * 86400)
        if self.server.secure_cookie:
            cookie += '; Secure'
        return {'user': self.account(account), 'csrf': csrf, **self.state(con)}, cookie
    def do_OPTIONS(self):
        if urlsplit(self.path).path != '/api/status':
            return self.send_json(403, {'error': 'Cross-origin access is not enabled.'})
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET')
        self.send_header('Access-Control-Allow-Headers', 'ngrok-skip-browser-warning, Content-Type')
        self.send_header('Content-Length', '0')
        self.end_headers()
    def do_GET(self):
        self.dispatch('GET')
    def do_POST(self):
        self.dispatch('POST')
    def do_PUT(self):
        self.dispatch('PUT')
    def dispatch(self, method):
        try:
            host = urlsplit('//' + self.headers.get('Host', '')).hostname or ''
            trusted = host.lower() in ('localhost', socket.gethostname().lower())
            try:
                trusted = trusted or ipaddress.ip_address(host).is_private
            except ValueError:
                pass
            if not trusted:
                raise APIError(403, 'Use the local PC address.')
            path = urlsplit(self.path).path
            if path.startswith('/api/'):
                if method != 'GET':
                    self.check_origin()
                with self.server.write_lock, self.server.connect() as con:
                    self.api(method, path, con)
            elif method == 'GET':
                self.static(path)
            else:
                raise APIError(404, 'Not found.')
        except APIError as error:
            self.send_json(error.status, {'error': error.message})
        except (sqlite3.Error, OSError, ValueError, TypeError, KeyError):
            self.log_error('Request failed; see server configuration/database permissions.')
            self.send_json(500, {'error': 'The server could not complete this request. Your data was not replaced.'})
    def api(self, method, path, con):
        if method == 'GET' and path == '/api/status':
            return self.send_json(200, {'shared': True, 'application': 'fitzgerald-finance', 'webAuthn': device_auth.WEBAUTHN, 'needsSetup': con.execute('SELECT COUNT(*) FROM accounts').fetchone()[0] == 0})
        if method == 'POST' and path == '/api/setup':
            if con.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]:
                raise APIError(409, 'Setup is complete. Sign in instead.')
            body = self.body()
            data = validate_data(body.get('data'))
            account = self.create_account(con, body, 'admin')
            con.execute('INSERT INTO household VALUES (1,1,?,?,?)', (json.dumps(data, allow_nan=False), account['id'], int(time.time())))
            response, cookie = self.new_session(con, account)
            con.commit()
            return self.send_json(201, response, cookie)
        if method == 'POST' and path == '/api/login':
            body = self.body()
            now = time.time()
            attempts = [stamp for stamp in self.server.attempts.get(self.client_address[0], []) if stamp > now - 300]
            if len(attempts) >= 10:
                raise APIError(429, 'Too many attempts. Try again in five minutes.')
            name, password = body.get('username', ''), body.get('password', '')
            if not isinstance(name, str) or not isinstance(password, str) or len(password) > 256:
                raise APIError(400, 'Invalid credentials.')
            row = con.execute('SELECT * FROM accounts WHERE username=?', (name,)).fetchone()
            if not verify_password(con, row, password):
                self.server.attempts[self.client_address[0]] = attempts + [now]
                raise APIError(401, 'Username or password is incorrect.')
            self.server.attempts.pop(self.client_address[0], None)
            response, cookie = self.new_session(con, row)
            con.commit()
            return self.send_json(200, response, cookie)
        if path.startswith('/api/biometric/'):
            return device_auth.handle(self, method, path, con, APIError)
        actor = self.session(con, method != 'GET')
        if method == 'GET' and path == '/api/session':
            return self.send_json(200, {'user': self.account(actor), 'csrf': actor['csrf'], **self.state(con)})
        if method == 'GET' and path == '/api/state':
            return self.send_json(200, self.state(con))
        if method == 'POST' and path == '/api/backup':
            self.body()
            self.server.backup()
            return self.send_json(200, {'ok': True})
        if method == 'POST' and path == '/api/logout':
            con.execute('DELETE FROM sessions WHERE token_hash=?', (actor['token_hash'],))
            con.commit()
            return self.send_json(200, {'ok': True}, 'finance_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0')
        if method == 'PUT' and path == '/api/state':
            body = self.body()
            data = validate_data(body.get('data'))
            current = self.state(con)
            if type(body.get('revision')) is not int or body['revision'] != current['revision']:
                return self.send_json(409, {'error': 'The household was updated by another device.', **current})
            self.server.backup()
            revision = current['revision'] + 1
            con.execute('UPDATE household SET revision=?,data=?,updated_by=?,updated_at=? WHERE id=1',
                (revision, json.dumps(data, allow_nan=False), actor['id'], int(time.time())))
            con.commit()
            return self.send_json(200, {'revision': revision, 'data': data})
        if method == 'POST' and path == '/api/password':
            body = self.body()
            row = con.execute('SELECT * FROM accounts WHERE id=?', (actor['id'],)).fetchone()
            current = body.get('current', '')
            if not isinstance(current, str) or len(current) > 256 or not verify_password(con, row, current):
                raise APIError(403, 'Current password is incorrect.')
            _, password = self.credentials({'username': actor['username'], 'password': body.get('password')})
            salt = secrets.token_hex(16)
            con.execute('UPDATE accounts SET salt=?,password_hash=? WHERE id=?', (salt, password_hash(password, salt), actor['id']))
            con.execute('DELETE FROM sessions WHERE account_id=? AND token_hash<>?', (actor['id'], actor['token_hash']))
            con.execute('DELETE FROM device_credentials WHERE account_id=?', (actor['id'],))
            con.execute('DELETE FROM legacy_account_auth WHERE account_id=?', (actor['id'],))
            con.commit()
            return self.send_json(200, {'ok': True})
        if actor['role'] != 'admin':
            raise APIError(403, 'Administrator access required.')
        if account_admin.handle(self, method, path, con, actor, APIError):
            return
        if method == 'GET' and path == '/api/users':
            return self.send_json(200, {'users': [self.account(row) for row in con.execute('SELECT * FROM accounts ORDER BY created_at,username')]})
        if method == 'POST' and path == '/api/users':
            account = self.create_account(con, self.body())
            con.commit()
            return self.send_json(201, {'user': self.account(account)})
        if method == 'PUT' and path == '/api/users/role':
            body = self.body()
            if body.get('id') == actor['id'] or body.get('role') not in ('user', 'admin'):
                raise APIError(400, 'You cannot change your own role; select a valid role.')
            updated = con.execute('UPDATE accounts SET role=? WHERE id=?', (body['role'], body.get('id')))
            if updated.rowcount != 1:
                raise APIError(404, 'Account not found.')
            con.commit()
            return self.send_json(200, {'ok': True})
        raise APIError(404, 'Not found.')
    def static(self, path):
        allowed = {'/': ('index.html', 'text/html'), '/index.html': ('index.html', 'text/html'),
            '/account-client.js': ('account-client.js', 'text/javascript'), '/shared-client.js': ('shared-client.js', 'text/javascript'), '/device-client.js': ('device-client.js', 'text/javascript'), '/connection-client.js': ('connection-client.js', 'text/javascript'), '/sw.js': ('sw.js', 'text/javascript'),
            '/manifest.webmanifest': ('manifest.webmanifest', 'application/manifest+json'), '/icon.svg': ('icon.svg', 'image/svg+xml')}
        if path not in allowed:
            raise APIError(404, 'Not found.')
        name, content_type = allowed[path]
        payload = (ROOT / name).read_bytes()
        if name == 'index.html':
            payload = payload.replace(b'<script src="./account-client.js">', b'<script>window.FITZGERALD_SHARED=true;</script><script src="./account-client.js">', 1)
            # Android adds the ngrok bypass header to the main navigation only.
            # Keep startup self-contained so script requests cannot become ngrok HTML warnings.
            for client in ('account-client.js', 'connection-client.js', 'device-client.js', 'shared-client.js'):
                source = (ROOT / client).read_bytes()
                source = re.sub(br'</script', lambda match: b'<\\/' + match.group()[2:], source, flags=re.I)
                tag = ('<script src="./' + client + '"></script>').encode()
                payload = payload.replace(tag, b'<script>\n' + source + b'\n</script>', 1)
        self.send_response(200)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(payload)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8088)
    parser.add_argument('--database', default=str(ROOT / 'Database' / 'finance.sqlite3'))
    parser.add_argument('--secure-cookie', action='store_true', help='Enable when all clients use HTTPS through a private proxy.')
    args = parser.parse_args()
    server = FinanceHTTPServer((args.host, args.port), args.database, args.secure_cookie)
    server.backup()
    print(f'Fitzgerald Finance is running at http://{args.host}:{server.server_port}', flush=True)
    print(f'Database: {server.database}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
