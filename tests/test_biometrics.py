import base64
from contextlib import closing
import hashlib
import json
import sqlite3
import unittest
import test_server as fixtures
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from fido2.cose import ES256
from fido2.webauthn import Aaguid,AttestedCredentialData,AuthenticatorData,AttestationObject,CollectedClientData

def b64(value):return base64.urlsafe_b64encode(bytes(value)).rstrip(b'=').decode()
class DeviceAuthTests(unittest.TestCase):
    setUp=fixtures.HouseholdServerTests.setUp
    tearDown=fixtures.HouseholdServerTests.tearDown
    member=fixtures.HouseholdServerTests.member
    def enroll_native(self):
        status,device=self.admin.call('/api/biometric/native/enroll','POST',{'password':fixtures.PASSWORD,'label':'Test phone'})
        self.assertEqual(status,201);return device
    def test_native_token_is_hashed_not_shared_and_can_be_revoked(self):
        self.assertEqual(self.admin.call('/api/biometric/native/enroll','POST',{'password':'wrong'})[0],403)
        device=self.enroll_native();client=fixtures.Client(self.url)
        self.assertEqual(client.call('/api/biometric/native/login','POST',device)[0],200)
        with closing(sqlite3.connect(self.path)) as con:
            saved=con.execute('SELECT token_hash,credential FROM device_credentials WHERE id=?',(device['deviceId'],)).fetchone()
            self.assertNotEqual(saved[0],device['token']);self.assertIsNone(saved[1])
        state=self.admin.call('/api/state')[1]['data'];self.assertFalse(state['biometric']['enabled']);self.assertNotIn(device['token'],json.dumps(state))
        self.assertEqual(client.call('/api/biometric/native/login','POST',dict(device,token='wrong'))[0],401)
        spouse=self.member();self.assertEqual(spouse.call('/api/biometric/revoke','POST',{'deviceId':device['deviceId']})[0],200)
        self.assertEqual(client.call('/api/biometric/native/login','POST',device)[0],200)
        self.assertEqual(self.admin.call('/api/biometric/revoke','POST',{'deviceId':device['deviceId']})[0],200)
        self.assertEqual(client.call('/api/biometric/native/login','POST',device)[0],401)
    def test_password_change_revokes_device_sign_in(self):
        device=self.enroll_native()
        self.assertEqual(self.admin.call('/api/password','POST',{'current':fixtures.PASSWORD,'password':'a-new-household-password'})[0],200)
        self.assertEqual(fixtures.Client(self.url).call('/api/biometric/native/login','POST',device)[0],401)
    def register_webauthn(self):
        status,begin=self.admin.call('/api/biometric/enroll/options','POST',{'password':fixtures.PASSWORD});self.assertEqual(status,200)
        private=ec.generate_private_key(ec.SECP256R1());credential_id=b'finance-test-device'
        credential=AttestedCredentialData.create(Aaguid.NONE,credential_id,ES256.from_cryptography_key(private.public_key()))
        rp=begin['publicKey']['rp']['id'];client=CollectedClientData.create('webauthn.create',begin['publicKey']['challenge'],self.url)
        auth=AuthenticatorData.create(hashlib.sha256(rp.encode()).digest(),AuthenticatorData.FLAG.UP|AuthenticatorData.FLAG.UV|AuthenticatorData.FLAG.AT,0,credential)
        response={'id':b64(credential_id),'rawId':b64(credential_id),'type':'public-key','response':{'clientDataJSON':b64(client),'attestationObject':b64(AttestationObject.create('none',auth,{}))},'clientExtensionResults':{}}
        status,result=self.admin.call('/api/biometric/enroll/complete','POST',{'challengeId':begin['challengeId'],'credential':response});self.assertEqual(status,201)
        return private,credential_id,rp,result
    def assertion(self,private,credential_id,rp,begin,counter=1,uv=True,origin=None):
        client=CollectedClientData.create('webauthn.get',begin['publicKey']['challenge'],origin or self.url)
        flags=AuthenticatorData.FLAG.UP|(AuthenticatorData.FLAG.UV if uv else 0)
        auth=AuthenticatorData.create(hashlib.sha256(rp.encode()).digest(),flags,counter)
        signature=private.sign(bytes(auth)+client.hash,ec.ECDSA(hashes.SHA256()))
        return {'id':b64(credential_id),'rawId':b64(credential_id),'type':'public-key','response':{'clientDataJSON':b64(client),'authenticatorData':b64(auth),'signature':b64(signature)},'clientExtensionResults':{}}
    def test_signed_webauthn_login_and_replay_rejection(self):
        private,credential_id,rp,result=self.register_webauthn();client=fixtures.Client(self.url)
        status,begin=client.call('/api/biometric/options','POST',{'username':'householdAdmin','credentialId':result['credentialId']});self.assertEqual(status,200)
        body={'challengeId':begin['challengeId'],'credential':self.assertion(private,credential_id,rp,begin)}
        status,session=client.call('/api/biometric/complete','POST',body);self.assertEqual(status,200);self.assertEqual(session['user']['username'],'householdAdmin')
        self.assertEqual(client.call('/api/biometric/complete','POST',body)[0],401)
        with closing(sqlite3.connect(self.path)) as con:self.assertEqual(con.execute("SELECT counter FROM device_credentials WHERE kind='webauthn'").fetchone()[0],1)
    def test_webauthn_requires_user_verification_origin_and_signature(self):
        private,credential_id,rp,result=self.register_webauthn();client=fixtures.Client(self.url)
        for kind in ('no-uv','wrong-origin','bad-signature'):
            status,begin=client.call('/api/biometric/options','POST',{'username':'householdAdmin','credentialId':result['credentialId']});self.assertEqual(status,200)
            credential=self.assertion(private,credential_id,rp,begin,uv=kind!='no-uv',origin='https://wrong.example' if kind=='wrong-origin' else None)
            if kind=='bad-signature':credential['response']['signature']=b64(b'invalid-signature')
            status,_=client.call('/api/biometric/complete','POST',{'challengeId':begin['challengeId'],'credential':credential});self.assertEqual(status,401,kind)

if __name__=='__main__':unittest.main()
