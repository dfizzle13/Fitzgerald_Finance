"""Device-local biometric authentication: WebAuthn public keys or native vault tokens.
No fingerprint/face templates or device private keys are accepted by this server.
"""
import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
import time
from urllib.parse import urlsplit
try:
    from fido2.server import Fido2Server
    from fido2.webauthn import AttestedCredentialData,AuthenticationResponse
    WEBAUTHN=True
except ImportError:
    WEBAUTHN=False

def b64(value):return base64.urlsafe_b64encode(bytes(value)).rstrip(b'=').decode()
def origin_for(handler):
    forwarded=handler.headers.get('X-Finance-Original-Origin')
    origin=forwarded if forwarded and ipaddress.ip_address(handler.client_address[0]).is_loopback else handler.headers.get('Origin')
    origin=origin or 'http://'+handler.headers.get('Host','localhost')
    parsed=urlsplit(origin)
    if parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password or not parsed.hostname:raise ValueError('Invalid authentication origin.')
    if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1','::1')):raise ValueError('Biometric sign-in requires HTTPS or localhost.')
    return origin,parsed.hostname

def initialize(con):
    con.executescript('''CREATE TABLE IF NOT EXISTS device_credentials (
        id TEXT PRIMARY KEY,account_id TEXT NOT NULL,kind TEXT NOT NULL,
        origin TEXT NOT NULL,rp_id TEXT NOT NULL,label TEXT NOT NULL,
        token_hash TEXT,credential BLOB,credential_id TEXT,counter INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL,expires INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS device_accounts ON device_credentials(account_id);
    ''')

def handle(handler,method,path,con,error):
    if method!='POST':raise error(405,'Use POST for device authentication.')
    body=handler.body();now=int(time.time())
    origin,rp_id=origin_for(handler)
    challenges=handler.server.device_challenges
    for key in list(challenges):
        if challenges[key]['expires']<now:challenges.pop(key,None)
    def actor():return handler.session(con,True)
    def password_check(user):
        from main import password_hash
        saved=con.execute('SELECT * FROM accounts WHERE id=?',(user['id'],)).fetchone()
        password=body.get('password','')
        if not isinstance(password,str) or len(password)>256 or not hmac.compare_digest(password_hash(password,saved['salt']),saved['password_hash']):raise error(403,'Confirm your current password to enable this device.')
    def fido(origin_value,rp):
        if not WEBAUTHN:raise error(503,'Install the server WebAuthn dependencies to enable browser biometrics.')
        return Fido2Server({'id':rp,'name':'Fitzgerald Finance'},verify_origin=lambda value:value==origin_value)
    def challenge(kind,user,state):
        if len(challenges)>200:raise error(429,'Please wait before trying device authentication again.')
        identifier=secrets.token_urlsafe(32);challenges[identifier]={'kind':kind,'account':user['id'],'origin':origin,'rp_id':rp_id,'state':state,'expires':now+300}
        return identifier
    def consume(kind,user=None):
        identifier=body.get('challengeId','')
        if not isinstance(identifier,str):raise error(400,'Invalid authentication challenge.')
        item=challenges.pop(identifier,None)
        if not item or item['kind']!=kind or item['expires']<now or item['origin']!=origin or (user and item['account']!=user['id']):raise error(401,'Device challenge expired. Please try again.')
        return item
    def signed_in(account_id):
        account=con.execute('SELECT * FROM accounts WHERE id=?',(account_id,)).fetchone()
        if not account:raise error(401,'Please use your password to sign in.')
        response,cookie=handler.new_session(con,account);con.commit();return handler.send_json(200,response,cookie)
    if path=='/api/biometric/native/enroll':
        user=actor();password_check(user);identifier=secrets.token_hex(16);token=secrets.token_urlsafe(32)
        con.execute('INSERT INTO device_credentials (id,account_id,kind,origin,rp_id,label,token_hash,created_at,expires) VALUES (?,?,?,?,?,?,?,?,?)',(identifier,user['id'],'native',origin,rp_id,str(body.get('label','This phone'))[:80],hashlib.sha256(token.encode()).hexdigest(),now,now+90*86400));con.commit()
        return handler.send_json(201,{'deviceId':identifier,'token':token})
    if path=='/api/biometric/native/login':
        identifier=body.get('deviceId');token=body.get('token')
        if not isinstance(identifier,str) or not isinstance(token,str) or len(token)>256:raise error(401,'Use your password and enable this device again.')
        row=con.execute("SELECT * FROM device_credentials WHERE id=? AND kind='native' AND origin=? AND expires>?",(identifier,origin,now)).fetchone()
        if not row or not hmac.compare_digest(row['token_hash'],hashlib.sha256(token.encode()).hexdigest()):raise error(401,'Use your password and enable this device again.')
        return signed_in(row['account_id'])
    if path=='/api/biometric/revoke':
        user=actor();con.execute('DELETE FROM device_credentials WHERE id=? AND account_id=?',(body.get('deviceId'),user['id']));con.commit();return handler.send_json(200,{'ok':True})
    if path=='/api/biometric/enroll/options':
        user=actor();password_check(user)
        credentials=[AttestedCredentialData(row['credential']) for row in con.execute("SELECT credential FROM device_credentials WHERE account_id=? AND rp_id=? AND kind='webauthn'",(user['id'],rp_id))]
        options,state=fido(origin,rp_id).register_begin({'id':user['id'].encode(),'name':user['username'],'displayName':user['username']},credentials,user_verification='required',authenticator_attachment='platform',resident_key_requirement='discouraged')
        return handler.send_json(200,{'challengeId':challenge('enroll',user,state),**dict(options)})
    if path=='/api/biometric/enroll/complete':
        user=actor();item=consume('enroll',user)
        try:auth=fido(origin,rp_id).register_complete(item['state'],body['credential'])
        except (ValueError,KeyError,TypeError):raise error(401,'Device enrollment could not be verified.')
        credential=auth.credential_data
        if credential is None:raise error(401,'No device credential was returned.')
        identifier=secrets.token_hex(16)
        con.execute("DELETE FROM device_credentials WHERE account_id=? AND credential_id=? AND kind='webauthn'",(user['id'],b64(credential.credential_id)))
        con.execute('INSERT INTO device_credentials (id,account_id,kind,origin,rp_id,label,credential,credential_id,counter,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',(identifier,user['id'],'webauthn',origin,rp_id,str(body.get('label','This device'))[:80],bytes(credential),b64(credential.credential_id),auth.counter,now));con.commit()
        return handler.send_json(201,{'deviceId':identifier,'credentialId':b64(credential.credential_id)})
    if path=='/api/biometric/options':
        username=body.get('username','');credential_id=body.get('credentialId','')
        if not isinstance(username,str) or not isinstance(credential_id,str):raise error(401,'Use your password to sign in.')
        row=con.execute("SELECT d.*,a.username FROM device_credentials d JOIN accounts a ON a.id=d.account_id WHERE a.username=? AND d.credential_id=? AND d.rp_id=? AND d.kind='webauthn'",(username,credential_id,rp_id)).fetchone()
        if not row:raise error(401,'Use your password and enable biometrics on this device again.')
        options,state=fido(origin,rp_id).authenticate_begin([AttestedCredentialData(row['credential'])],user_verification='required')
        return handler.send_json(200,{'challengeId':challenge('login',{'id':row['account_id']},state),**dict(options)})
    if path=='/api/biometric/complete':
        item=consume('login');rows=list(con.execute("SELECT * FROM device_credentials WHERE account_id=? AND rp_id=? AND kind='webauthn'",(item['account'],rp_id)))
        try:
            parsed=AuthenticationResponse.from_dict(body['credential']);credential=fido(origin,rp_id).authenticate_complete(item['state'],[AttestedCredentialData(row['credential']) for row in rows],parsed)
            row=next(row for row in rows if row['credential_id']==b64(credential.credential_id));counter=parsed.response.authenticator_data.counter
            if row['counter'] and counter and counter<=row['counter']:raise ValueError('Device counter did not advance.')
        except (ValueError,KeyError,TypeError,StopIteration):raise error(401,'Device authentication could not be verified.')
        con.execute('UPDATE device_credentials SET counter=? WHERE id=?',(counter,row['id']));return signed_in(item['account'])
    raise error(404,'Device authentication route not found.')
