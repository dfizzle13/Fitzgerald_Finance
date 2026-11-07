/* Device-local connection preferences; never part of household backups or shared data. */
(function(root){
'use strict';
const KEY='fitzgeraldFinance.connection.v1';let counter=0;const pending=new Map();
function normalize(value){
 let text=String(value||'').trim();if(!text)throw Error('Enter the Finance server HTTPS address.');if(!text.includes('://'))text='https://'+text;
 const url=new URL(text);if(url.username||url.password||url.search||url.hash)throw Error('Use a server address without credentials, query strings, or fragments.');
 if(url.protocol!=='https:'&&!(url.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(url.hostname)))throw Error('Use HTTPS for a remote server.');
 if((url.hostname.endsWith('.ngrok-free.dev')||url.hostname.endsWith('.ngrok-free.app')||url.hostname.endsWith('.ngrok.app'))&&url.pathname==='/')url.pathname='/finance/';
 if(!url.pathname.endsWith('/'))url.pathname+='/';return url.href;
}
function saved(){try{if(root.FitzgeraldAndroid&&root.FitzgeraldAndroid.getServerUrl)return root.FitzgeraldAndroid.getServerUrl()||'';return JSON.parse(localStorage.getItem(KEY)||'{}').url||''}catch{return ''}}
function native(method,url){return new Promise((resolve,reject)=>{const id='connection-'+(++counter);pending.set(id,{resolve,reject});root.FitzgeraldAndroid[method](url,id);setTimeout(()=>{if(pending.has(id)){pending.delete(id);reject(Error('The connection check timed out.'))}},20000)})}
root.FinanceConnectionCallbacks={success(id,payload){const item=pending.get(id);if(item){pending.delete(id);item.resolve(JSON.parse(payload))}},error(id,message){const item=pending.get(id);if(item){pending.delete(id);item.reject(Error(message))}}};
async function test(value){const url=normalize(value);if(root.FitzgeraldAndroid&&root.FitzgeraldAndroid.testServer)return native('testServer',url);const response=await fetch(url+'api/status',{credentials:'omit',cache:'no-store',headers:{'ngrok-skip-browser-warning':'1'},signal:AbortSignal.timeout(10000)});let result;try{result=await response.json()}catch{throw Error('This address did not return the Finance server. Include /finance/ for the shared ngrok gateway.')}if(!response.ok||result.application!=='fitzgerald-finance'||result.shared!==true)throw Error('This is not a Fitzgerald Finance server. Check the address and app path.');return result}
async function connect(value){const url=normalize(value);await test(url);localStorage.setItem(KEY,JSON.stringify({url}));if(root.FitzgeraldAndroid&&root.FitzgeraldAndroid.connectServer){await native('connectServer',url);return}root.location.assign(url)}
function clear(){localStorage.removeItem(KEY);if(root.FitzgeraldAndroid&&root.FitzgeraldAndroid.disconnectServer)root.FitzgeraldAndroid.disconnectServer();}
function open(){
 const container=document.createElement('div');container.className='dlgback';container.innerHTML='<div class="dlg" role="dialog" aria-modal="true"><div class="dlghead"><h2>Server connectivity</h2><button type="button" class="x" id="connectionClose">×</button></div><form id="connectionForm"><div class="field"><label for="connectionAddress">Finance server address</label><input id="connectionAddress" type="url" placeholder="https://your-domain.ngrok-free.dev/finance/" required></div><p class="muted">Use your shared ngrok address with /finance/. Sign in with your household account after connecting. The address is saved only on this device.</p><div id="connectionResult" role="status" class="notice"></div><div class="dlgactions"><button class="btn secondary" type="button" id="connectionTest">Test connection</button><button class="btn primary" id="connectionSave">Save & connect</button></div><button class="btn quiet small" id="connectionClear" type="button">Clear saved connection</button></form></div>';
 document.body.appendChild(container);const address=container.querySelector('#connectionAddress'),result=container.querySelector('#connectionResult');address.value=saved()||((root.FITZGERALD_SHARED&&root.location)?new URL('./',root.location.href).href:'');
 container.querySelector('#connectionClose').onclick=()=>container.remove();
 container.querySelector('#connectionTest').onclick=async()=>{result.textContent='Checking server…';try{await test(address.value);result.textContent='Connected to Fitzgerald Finance.'}catch(error){result.textContent=error.message}};
 container.querySelector('#connectionForm').onsubmit=async event=>{event.preventDefault();result.textContent='Connecting…';try{await connect(address.value)}catch(error){result.textContent=error.message}};
 container.querySelector('#connectionClear').onclick=()=>{clear();address.value='';result.textContent='Saved connection cleared. Household data has not been deleted.'};
}
root.FinanceConnection={normalize,saved,test,connect,open,clear,get recovery(){return !!(root.FitzgeraldAndroid&&saved()&&root.location&&root.location.protocol==='file:')}};
if(typeof module!=='undefined')module.exports=root.FinanceConnection;
})(typeof window==='undefined'?globalThis:window);
