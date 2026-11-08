"""Administrator-approved transfer of legacy device accounts and password resets."""
import hashlib
import json
import re
import secrets
import time


def handle(handler, method, path, con, actor, error):
    from main import password_hash, verify_password, validate_data
    if method != 'POST' or path not in ('/api/users/import', '/api/users/password'):
        return False
    body = handler.body()
    current = body.get('current', '')
    account = con.execute('SELECT * FROM accounts WHERE id=?', (actor['id'],)).fetchone()
    if not isinstance(current, str) or len(current) > 256 or not verify_password(con, account, current):
        raise error(403, 'Confirm your server administrator password.')
    if path == '/api/users/password':
        target = con.execute('SELECT * FROM accounts WHERE id=?', (body.get('id'),)).fetchone()
        if not target:
            raise error(404, 'Account not found.')
        _, password = handler.credentials({'username': target['username'], 'password': body.get('password')})
        handler.server.backup()
        salt = secrets.token_hex(16)
        con.execute('UPDATE accounts SET salt=?,password_hash=? WHERE id=?', (salt, password_hash(password, salt), target['id']))
        con.execute('DELETE FROM legacy_account_auth WHERE account_id=?', (target['id'],))
        con.execute('DELETE FROM device_credentials WHERE account_id=?', (target['id'],))
        con.execute('DELETE FROM sessions WHERE account_id=? AND token_hash<>?', (target['id'], actor['token_hash']))
        con.commit()
        handler.send_json(200, {'ok': True})
        return True
    transfer = body.get('transfer')
    if not isinstance(transfer, dict) or transfer.get('format') != 'fitzgerald-account-transfer' or transfer.get('version') != 1:
        raise error(400, 'Paste a phone account transfer created by the app.')
    users = transfer.get('users')
    financial = transfer.get('financial', [])
    transfer_id = transfer.get('id', '')
    if not isinstance(transfer_id, str) or not re.fullmatch('[a-f0-9]{32}', transfer_id):
        raise error(400, 'Invalid device transfer identifier.')
    if not isinstance(users, list) or len(users) > 100 or not isinstance(financial, list) or len(financial) > 200 or not (users or financial):
        raise error(400, 'Invalid or empty device transfer.')
    states = []
    for item in financial:
        if not isinstance(item, dict):
            raise error(400, 'Invalid financial transfer.')
        states.append(validate_data(item.get('data')))
    digest = hashlib.sha256(json.dumps({'transfer':transfer,'merge':bool(body.get('mergeFinancial'))},sort_keys=True,separators=(',',':')).encode()).hexdigest()
    receipt = con.execute('SELECT digest,result FROM device_transfers WHERE id=?', (transfer_id,)).fetchone()
    if receipt:
        if receipt['digest'] != digest:
            raise error(409, 'This transfer was already imported with different options.')
        handler.send_json(200, json.loads(receipt['result']))
        return True
    names = set()
    for row in users:
        if not isinstance(row, dict):
            raise error(400, 'Invalid account transfer.')
        name, salt, credential_digest = row.get('username'), row.get('salt'), row.get('hash')
        if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,32}', name) or name.lower() in names:
            raise error(400, 'Every transferred account needs a unique valid username.')
        if not isinstance(salt, str) or not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,128}', salt) or not isinstance(credential_digest, str) or not re.fullmatch(r'[0-9a-f]{64}', credential_digest):
            raise error(400, 'A transferred account has invalid password information.')
        if row.get('role') not in ('user', 'admin'):
            raise error(400, 'Invalid transferred account role.')
        names.add(name.lower())
    handler.server.backup()
    if states:
        archive = handler.server.database.parent/'backups'/'device-transfers'
        archive.mkdir(parents=True,exist_ok=True)
        (archive/(transfer_id+'.json')).write_text(json.dumps({'format':'fitzgerald-device-financial-archive','states':states}),encoding='utf-8')
    imported, skipped = [], []
    for row in users:
        if con.execute('SELECT 1 FROM accounts WHERE username=?', (row['username'],)).fetchone():
            skipped.append(row['username'])
            continue
        identifier, salt = secrets.token_hex(16), secrets.token_hex(16)
        # Wrap the legacy verifier with scrypt immediately. Upgrade to the normal
        # server verifier after the first successful password authentication.
        con.execute('INSERT INTO accounts VALUES (?,?,?,?,?,?)', (identifier, row['username'], salt, password_hash(row['hash'], salt), row['role'], int(time.time())))
        con.execute('INSERT INTO legacy_account_auth VALUES (?,?)', (identifier, row['salt']))
        imported.append(row['username'])
    added, conflicts = {}, 0
    if body.get('mergeFinancial') and states:
        current = handler.state(con)
        data = current['data']
        for field in ('budgets','transactions','incomes','bills','monthlyArchives','categories'):
            target = data.setdefault(field,[])
            key = lambda row: row.get('id') or row.get('key') or row.get('name')
            indexed = {key(row):row for row in target}
            added[field] = 0
            for source in states:
                for row in source.get(field,[]):
                    identifier = key(row)
                    if identifier is None:
                        raise error(400,'A financial record has no identifier.')
                    if identifier in indexed:
                        if indexed[identifier] != row: conflicts += 1
                        continue
                    target.append(row);indexed[identifier]=row;added[field]+=1
        data = validate_data(data)
        con.execute('UPDATE household SET revision=?,data=?,updated_by=?,updated_at=? WHERE id=1',(current['revision']+1,json.dumps(data,allow_nan=False),actor['id'],int(time.time())))
    result = {'imported': imported, 'skipped': skipped, 'added': added, 'conflicts': conflicts, 'archivedStates':len(states), 'transferId':transfer_id}
    con.execute('INSERT INTO device_transfers VALUES (?,?,?,?,?)',(transfer_id,digest,json.dumps(result),actor['id'],int(time.time())))
    con.commit()
    handler.send_json(200, result)
    return True
