/* Per-device authentication metadata. Fingerprints/face data/private keys stay with the OS. */
(function(root){
'use strict';
const pending=new Map();let sequence=0;
function scope(username){return new URL('./',root.location.href).href+'|'+String(username).trim().toLowerCase()}
function key(username){return 'fitzgeraldFinance.deviceAuth.'+scope(username)}
function read(username){try{return JSON.parse(localStorage.getItem(key(username))||'null')}catch{return null}}
function write(username,value){if(value)localStorage.setItem(key(username),JSON.stringify(value));else localStorage.removeItem(key(username))}
function nativeAvailable(){return !!(root.FitzgeraldAndroid&&root.FitzgeraldAndroid.storeBiometricCredential&&root.FitzgeraldAndroid.isBiometricAvailable())}
function bytes(value){return Uint8Array.from(atob(value.replace(/-/g,'+').replace(/_/g,'/')+'==='.slice((value.length+3)%4)),x=>x.charCodeAt(0))}
function b64(value){return btoa(String.fromCharCode(...new Uint8Array(value))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,'')}
function options(result){const request=result.publicKey;request.challenge=bytes(request.challenge);if(request.user)request.user.id=bytes(request.user.id);for(const name of ['allowCredentials','excludeCredentials'])if(request[name])request[name]=request[name].map(item=>({...item,id:bytes(item.id)}));return request}
function serialize(credential){if(credential.toJSON)return credential.toJSON();const response={clientDataJSON:b64(credential.response.clientDataJSON)};for(const field of ['attestationObject','authenticatorData','signature','userHandle'])if(credential.response[field])response[field]=b64(credential.response[field]);if(credential.response.getTransports)response.transports=credential.response.getTransports();return {id:credential.id,rawId:b64(credential.rawId),type:credential.type,response,clientExtensionResults:credential.getClientExtensionResults?credential.getClientExtensionResults():{}}}
function native(method,args,onFailed){return new Promise((resolve,reject)=>{const id='device-'+(++sequence);pending.set(id,{resolve,reject,onFailed});root.FitzgeraldAndroid[method](...args,id)})}
root.FinanceNativeVaultCallbacks={success(id,value){const item=pending.get(id);if(item){pending.delete(id);item.resolve(value)}},error(id,message){const item=pending.get(id);if(item){pending.delete(id);item.reject(Error(message))}},failed(id){const item=pending.get(id);if(item&&item.onFailed)item.onFailed()}};
async function enroll(client,username,password){
 let result;
 if(nativeAvailable()){
  result=await client.request('biometric/native/enroll','POST',{password,label:'This phone'});
  try{await native('storeBiometricCredential',[scope(username),JSON.stringify({deviceId:result.deviceId,token:result.token})]);}catch(error){await client.request('biometric/revoke','POST',{deviceId:result.deviceId}).catch(()=>{});throw error}
  write(username,{enabled:true,mode:'native',deviceId:result.deviceId,failures:0});
 }else{
  if(!root.PublicKeyCredential||!navigator.credentials||!root.isSecureContext)throw Error('Use the connected mobile app or an HTTPS browser with a device authenticator.');
  const begin=await client.request('biometric/enroll/options','POST',{password});
  const credential=await navigator.credentials.create({publicKey:options(begin)});
  if(!credential)throw Error('Device authentication was cancelled.');
  result=await client.request('biometric/enroll/complete','POST',{challengeId:begin.challengeId,credential:serialize(credential),label:'This device'});
  write(username,{enabled:true,mode:'webauthn',deviceId:result.deviceId,credentialId:result.credentialId,failures:0});
 }
 return read(username);
}
async function disable(client,username){const record=read(username);if(nativeAvailable())root.FitzgeraldAndroid.removeBiometricCredential(scope(username));write(username,null);if(record)await client.request('biometric/revoke','POST',{deviceId:record.deviceId});}
async function login(client,username){
 const record=read(username);if(!record||!record.enabled)throw Error('Sign in with your password and enable this device first.');
 function failed(){record.failures=(record.failures||0)+1;if(record.failures>=3){write(username,null);if(root.FitzgeraldAndroid&&root.FitzgeraldAndroid.cancelAuthentication)for(const id of pending.keys())root.FitzgeraldAndroid.cancelAuthentication(id)}else write(username,record)}
 try{
  let result;
  if(record.mode==='native'){
   const payload=JSON.parse(await native('unlockBiometricCredential',[scope(username)],failed));
   result=await client.request('biometric/native/login','POST',payload);
  }else{
   const begin=await client.request('biometric/options','POST',{username,credentialId:record.credentialId});
   const credential=await navigator.credentials.get({publicKey:options(begin)});
   if(!credential)throw Error('Device authentication was cancelled.');
   result=await client.request('biometric/complete','POST',{challengeId:begin.challengeId,credential:serialize(credential)});
  }
  record.failures=0;write(username,record);return result;
 }catch(error){if(error.status===401)write(username,null);throw error}
}
root.FinanceDeviceAuth={scope,read,write,nativeAvailable,enroll,disable,login};
if(typeof module!=='undefined')module.exports=root.FinanceDeviceAuth;
})(typeof window==='undefined'?globalThis:window);
