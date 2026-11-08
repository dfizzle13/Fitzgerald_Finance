/* Device-local connection preferences; never part of household data. */
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
function finish(id,error,payload){const item=pending.get(id);if(!item)return;pending.delete(id);clearTimeout(item.timer);if(error)item.reject(Error(error));else{try{item.resolve(JSON.parse(payload))}catch{item.reject(Error('The server returned an unexpected response.'))}}}
function native(method,url){return new Promise((resolve,reject)=>{const id='connection-'+(++counter),timer=setTimeout(()=>finish(id,'The connection check timed out.'),20000);pending.set(id,{resolve,reject,timer});try{root.FitzgeraldAndroid[method](url,id)}catch(error){finish(id,error.message||'The device connection check could not start.')}})}
root.FinanceConnectionCallbacks={success(id,payload){finish(id,null,payload)},error(id,message){finish(id,message)}};
async function test(value){
 const url=normalize(value);if(root.FitzgeraldAndroid&&root.FitzgeraldAndroid.testServer)return native('testServer',url);
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
 try{
  const response=await fetch(url+'api/status',{credentials:'omit',cache:'no-store',headers:{'ngrok-skip-browser-warning':'1'},signal:controller.signal});let result;
  try{result=await response.json()}catch{throw Error('This address did not return Finance. Include /finance/ in the shared ngrok address.')}
  if(!response.ok||result.application!=='fitzgerald-finance'||result.shared!==true)throw Error('This is not a Fitzgerald Finance server. Check the address and app path.');return result;
 }catch(error){if(error.name==='AbortError')throw Error('The server took too long to respond. Check its address and try again.');if(error instanceof TypeError)throw Error('Could not reach the household server. Check your connection and server address.');throw error}
 finally{clearTimeout(timer)}
}
async function connect(value){const url=normalize(value);await test(url);localStorage.setItem(KEY,JSON.stringify({url}));if(root.FitzgeraldAndroid&&root.FitzgeraldAndroid.connectServer){await native('connectServer',url);return}root.location.assign(url)}
function clear(){localStorage.removeItem(KEY);if(root.FitzgeraldAndroid&&root.FitzgeraldAndroid.disconnectServer)root.FitzgeraldAndroid.disconnectServer();}
function open(){
 const existing=document.querySelector('#connectionDialog');if(existing){existing.querySelector('#connectionClose').focus();return existing}
 const container=document.createElement('div');container.id='connectionDialog';container.className='dlgback';
 container.innerHTML='<div class="dlg connection-dialog" role="dialog" aria-modal="true" aria-labelledby="connectionTitle"><div class="dlghead"><div><div class="eyebrow">Fitzgerald Finance</div><h2 id="connectionTitle">Household server</h2></div><button type="button" class="x" id="connectionClose" aria-label="Close server settings">×</button></div><p class="connection-intro muted">Connect this device to your shared household.</p><form id="connectionForm"><div class="field"><label for="connectionAddress">Server address</label><input id="connectionAddress" type="text" inputmode="url" autocapitalize="off" autocomplete="url" spellcheck="false" placeholder="your-domain.ngrok-free.dev/finance/" required></div><p class="connection-help muted">Use your ngrok address with <b>/finance/</b>. Your accounts and budget stay on the server.</p><div id="connectionResult" role="status" aria-live="polite" class="notice hide"></div><div class="dlgactions"><button class="btn secondary" type="button" id="connectionTest">Test connection</button><button class="btn primary" type="submit" id="connectionSave">Save & connect</button></div><button class="btn quiet small connection-clear" id="connectionClear" type="button">Clear saved address</button></form></div>';
 document.body.appendChild(container);const address=container.querySelector('#connectionAddress'),result=container.querySelector('#connectionResult');
 address.value=saved()||((root.FITZGERALD_SHARED&&root.location)?new URL('./',root.location.href).href:'');
 container.querySelector('#connectionClose').onclick=()=>container.remove();
 function message(text,kind){result.textContent=text;result.classList.remove('hide');result.dataset.state=kind||'pending'}
 async function run(action){for(const button of container.querySelectorAll('#connectionForm button'))button.disabled=true;try{await action()}catch(error){message(error.message,'error')}finally{for(const button of container.querySelectorAll('#connectionForm button'))button.disabled=false}}
 container.querySelector('#connectionTest').onclick=()=>run(async()=>{message('Checking server…');await test(address.value);address.value=normalize(address.value);message('Connected to Fitzgerald Finance.','success')});
 container.querySelector('#connectionForm').onsubmit=event=>{event.preventDefault();run(async()=>{message('Connecting…');await connect(address.value)})};
 container.querySelector('#connectionClear').onclick=()=>{clear();address.value='';message('Saved address cleared. Household data remains on the server.','success')};
 container.querySelector('#connectionClose').focus();return container;
}
root.FinanceConnection={normalize,saved,test,connect,open,clear,get recovery(){return !!(root.FitzgeraldAndroid&&saved()&&root.location&&root.location.protocol==='file:')}};
// Bind recovery controls independently of account loading and main-app initialization.
if(typeof document!=='undefined'&&document.addEventListener)document.addEventListener('click',event=>{
 const button=event.target&&event.target.closest&&event.target.closest('#loginConnection,#settingsConnection,#sharedConfigure');if(!button)return;
 event.preventDefault();event.stopImmediatePropagation();open();
},true);
if(typeof module!=='undefined')module.exports=root.FinanceConnection;
})(typeof window==='undefined'?globalThis:window);
