from contextlib import closing
import hashlib,json,sqlite3
import unittest
import test_server as fixtures

class AccountTests(unittest.TestCase):
    setUp=fixtures.HouseholdServerTests.setUp
    tearDown=fixtures.HouseholdServerTests.tearDown
    member=fixtures.HouseholdServerTests.member
    def transfer(self):
        salt='phone-salt-123';password='original-phone-password'
        return {'format':'fitzgerald-account-transfer','version':1,'id':'a'*32,'users':[{'username':'phoneAdmin','role':'admin','salt':salt,'hash':hashlib.sha256((salt+':'+password).encode()).hexdigest()}],'financial':[{'data':dict(fixtures.DATA,transactions=[{'id':'phone-receipt','date':'2026-11-07','amount':13}])}]}
    def import_call(self,transfer,**changes):
        return self.admin.call('/api/users/import','POST',{'current':fixtures.PASSWORD,'transfer':transfer,'mergeFinancial':True,**changes})
    def test_transfer_preserves_passwords_roles_and_financial_records_across_devices(self):
        transfer=self.transfer();status,result=self.import_call(transfer)
        self.assertEqual(status,200);self.assertEqual(result['imported'],['phoneAdmin']);self.assertEqual(result['added']['transactions'],1)
        with closing(sqlite3.connect(self.path)) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM legacy_account_auth').fetchone()[0],1)
            saved=con.execute("SELECT password_hash FROM accounts WHERE username='phoneAdmin'").fetchone()[0]
            self.assertNotEqual(saved,transfer['users'][0]['hash'])
        second=fixtures.Client(self.url)
        self.assertEqual(second.call('/api/login','POST',{'username':'phoneAdmin','password':'original-phone-password'})[0],200)
        status,accounts=second.call('/api/users');self.assertEqual(status,200)
        self.assertNotIn('password_hash',json.dumps(accounts));self.assertNotIn('salt',json.dumps(accounts))
        self.assertEqual(second.call('/api/state')[1]['data']['transactions'][0]['amount'],13)
        with closing(sqlite3.connect(self.path)) as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM legacy_account_auth').fetchone()[0],0)
        self.assertEqual(self.import_call(transfer)[1],result)
        self.assertEqual(len(second.call('/api/state')[1]['data']['transactions']),1)
    def test_import_requires_admin_confirmation_and_never_overwrites_existing_records(self):
        transfer=self.transfer();member=self.member()
        self.assertEqual(member.call('/api/users/import','POST',{'current':fixtures.PASSWORD,'transfer':transfer})[0],403)
        self.assertEqual(self.import_call(transfer,current='wrong-password')[0],403)
        original={'id':'phone-receipt','date':'2026-11-07','amount':2}
        self.assertEqual(self.admin.call('/api/state','PUT',{'revision':1,'data':dict(fixtures.DATA,transactions=[original])})[0],200)
        transfer['users'][0]['username']='householdAdmin'
        status,result=self.import_call(transfer)
        self.assertEqual(status,200);self.assertEqual(result['skipped'],['householdAdmin']);self.assertEqual(result['conflicts'],1)
        self.assertEqual(self.admin.call('/api/state')[1]['data']['transactions'],[original])
        archive=self.path.parent/'backups/device-transfers'/('a'*32+'.json')
        self.assertEqual(json.loads(archive.read_text())['states'][0]['transactions'][0]['amount'],13)
        self.assertNotIn(transfer['users'][0]['hash'],archive.read_text())
        transfer['financial'][0]['data']['transactions'][0]['amount']=99
        self.assertEqual(self.import_call(transfer)[0],409)
    def test_password_reset_revokes_target_sessions_and_device_sign_in(self):
        member=self.member();target=next(u for u in self.admin.call('/api/users')[1]['users'] if u['username']=='spouse')
        status,device=member.call('/api/biometric/native/enroll','POST',{'password':fixtures.PASSWORD});self.assertEqual(status,201)
        body={'current':fixtures.PASSWORD,'id':target['id'],'password':'new-spouse-password'}
        self.assertEqual(member.call('/api/users/password','POST',body)[0],403)
        self.assertEqual(self.admin.call('/api/users/password','POST',{**body,'current':'wrong'})[0],403)
        self.assertEqual(self.admin.call('/api/users/password','POST',body)[0],200)
        self.assertEqual(member.call('/api/state')[0],401)
        another=fixtures.Client(self.url)
        self.assertEqual(another.call('/api/biometric/native/login','POST',device)[0],401)
        self.assertEqual(another.call('/api/login','POST',{'username':'spouse','password':fixtures.PASSWORD})[0],401)
        self.assertEqual(another.call('/api/login','POST',{'username':'spouse','password':'new-spouse-password'})[0],200)
        self.assertEqual(self.admin.call('/api/users')[0],200)
    def test_malformed_transfer_is_atomic(self):
        transfer=self.transfer();transfer['users'].append({'username':'broken'})
        self.assertEqual(self.import_call(transfer)[0],400)
        self.assertEqual(len(self.admin.call('/api/users')[1]['users']),1)
        self.assertEqual(self.admin.call('/api/state')[1]['data']['transactions'],[])

if __name__=='__main__':unittest.main()
