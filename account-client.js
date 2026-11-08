/* Account transfers are explicit and temporary; financial state is never cached here. */
(function(root){
'use strict';
const KEY='fitzgeraldFinance.v1',PENDING='fitzgeraldFinance.transferPending';
function legacy(){
 let saved;try{saved=JSON.parse(localStorage.getItem(KEY)||'null')}catch{}
 const users=(saved&&Array.isArray(saved.users)?saved.users:[]).filter(u=>u&&u.username&&u.salt&&u.hash);
 const financial=users.filter(u=>u.data).map(u=>({source:u.username,data:{...u.data,biometric:{enabled:false,id:null,failures:0}}}));
 for(let i=0;i<localStorage.length;i++){const key=localStorage.key(i);if(key&&key.startsWith('fitzgeraldFinance.sharedDraft.')){try{const data=JSON.parse(localStorage.getItem(key));if(data)financial.push({source:'Unsaved changes',data})}catch{}}}
 return {users,financial};
}
function hasLegacy(){if(localStorage.getItem(KEY))return true;for(let i=0;i<localStorage.length;i++){if((localStorage.key(i)||'').startsWith('fitzgeraldFinance.sharedDraft.'))return true}return false}
function dialog(title,html){
 const layer=document.createElement('div');layer.className='dlgback';
 layer.innerHTML='<div class="dlg" role="dialog" aria-modal="true"><div class="dlghead"><h2></h2><button type="button" class="x" aria-label="Close">×</button></div>'+html+'</div>';
 layer.querySelector('h2').textContent=title;layer.querySelector('.x').onclick=()=>layer.remove();document.body.appendChild(layer);return layer;
}
function cleanup(){
 localStorage.removeItem(KEY);
 for(let i=localStorage.length-1;i>=0;i--){const key=localStorage.key(i);if(key&&key.startsWith('fitzgeraldFinance.sharedDraft.'))localStorage.removeItem(key)}
 localStorage.removeItem(PENDING);
}
function exportDevice(){
 const data=legacy();if(!data.users.length&&!data.financial.length){alert('No phone-only accounts or financial records were found.');return}
 const id=Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');
 const transfer={format:'fitzgerald-account-transfer',version:1,id,users:data.users.map(u=>({username:u.username,salt:u.salt,hash:u.hash,role:u.role==='admin'?'admin':'user'})),financial:data.financial};
 localStorage.setItem(PENDING,id);
 if(root.FitzgeraldAndroid&&root.FitzgeraldAndroid.setPhoneTransferId)root.FitzgeraldAndroid.setPhoneTransferId(id);
 const layer=dialog('Transfer existing device data','<p>Copy this transfer, connect to the household server, then sign in as a server administrator and open <b>Admin → Import device data</b>. Keep this code private; it contains account password information and financial records.</p><div class="notice" id="transferSummary"></div><div class="field"><label>Private transfer code</label><textarea id="transferCode" rows="5" readonly></textarea></div><div role="status" id="transferStatus" class="muted"></div><div class="dlgactions"><button type="button" class="btn secondary" id="copyTransfer">Copy transfer</button><button type="button" class="btn primary" id="transferConnect">Connect to server</button></div>');
 layer.querySelector('#transferSummary').textContent=data.users.length+' accounts and '+data.financial.length+' financial snapshots. Originals stay on this device until the server confirms a successful transfer.';
 layer.querySelector('#transferCode').value=JSON.stringify(transfer);
 layer.querySelector('#copyTransfer').onclick=async()=>{
  const field=layer.querySelector('#transferCode');
  try{if(navigator.clipboard&&root.isSecureContext)await navigator.clipboard.writeText(field.value);else{field.select();if(!document.execCommand('copy'))throw Error('Select the transfer code and copy it manually.')};layer.querySelector('#transferStatus').textContent='Copied. Paste this into Import device data after signing in to the server.'}catch(e){layer.querySelector('#transferStatus').textContent=e.message}
 };
 layer.querySelector('#transferConnect').onclick=()=>{layer.remove();root.FinanceConnection.open()};
}
function gate(){
 document.querySelector('#loginTitle').textContent='Connect to your household';
 const sub=document.querySelector('#loginSub');sub.classList.remove('hide');sub.textContent='Accounts and financial records are stored on your PC server and shared across your devices.';
 for(const selector of ['#username','#passwordWrap','#signIn','#bioSignIn','.bio-login-setting','#register']){
  const node=document.querySelector(selector);(selector==='#username'?node.closest('.field'):node).classList.add('hide');
 }
 document.querySelector('#signIn').disabled=true;
 const connect=document.querySelector('#loginConnection');connect.textContent='Connect to household server';connect.className='btn primary';
 if(hasLegacy()){
  const button=document.createElement('button');button.type='button';button.className='btn secondary';button.style.marginTop='12px';button.textContent='Transfer existing device accounts and data';button.onclick=exportDevice;connect.after(button);
 }
}
function importDialog(client,updated){
 const layer=dialog('Import device data','<p>Paste the private transfer code from the old device. Existing server usernames and records are kept. Conflicting phone records are archived on the PC for review.</p><form><div class="field"><label>Private transfer code</label><textarea id="importCode" rows="5" required></textarea></div><p id="importPreview" class="muted"></p><label class="importOption"><input id="mergeDeviceFinances" type="checkbox" checked> Add missing financial records to the shared household</label><div class="field"><label>Your server administrator password</label><input id="importPassword" type="password" autocomplete="current-password" required></div><div class="err hide" id="importError" role="alert"></div><div class="dlgactions"><button class="btn secondary" id="cancelImport" type="button">Cancel</button><button class="btn primary" type="submit">Import to server</button></div></form>');
 layer.querySelector('#cancelImport').onclick=()=>layer.remove();
 layer.querySelector('#importCode').oninput=()=>{try{const data=JSON.parse(layer.querySelector('#importCode').value);layer.querySelector('#importPreview').textContent=(data.users||[]).map(u=>u.username+' ('+u.role+')').join(', ')+' · '+(data.financial||[]).length+' financial snapshots'}catch{layer.querySelector('#importPreview').textContent='Paste the full transfer code.'}};
 layer.querySelector('form').onsubmit=async event=>{
  event.preventDefault();const error=layer.querySelector('#importError'),submit=layer.querySelector('button[type=submit]');submit.disabled=true;
  try{
   const transfer=JSON.parse(layer.querySelector('#importCode').value);
   const result=await client.request('users/import','POST',{transfer,current:layer.querySelector('#importPassword').value,mergeFinancial:layer.querySelector('#mergeDeviceFinances').checked});
   layer.querySelector('#importCode').value='';layer.querySelector('#importPassword').value='';
   alert('Transferred '+result.imported.length+' accounts. Kept '+result.skipped.length+' existing usernames. Added '+Object.values(result.added||{}).reduce((a,b)=>a+b,0)+' financial records. '+result.conflicts+' conflicting records were kept in the private server archive.');
   if(localStorage.getItem(PENDING)===result.transferId)cleanup();
   layer.remove();await client.poll();if(updated)updated();
   if(root.FitzgeraldAndroid&&root.FitzgeraldAndroid.finishPhoneTransfer)root.FitzgeraldAndroid.finishPhoneTransfer(result.transferId);
  }catch(e){error.textContent=e.message;error.classList.remove('hide');submit.disabled=false}
 };
}
function resetDialog(client,account,updated){
 const layer=dialog('Reset password for '+account.username,'<p>The account will be signed out on its other devices and must enable biometric sign-in again.</p><form><div class="field"><label>Your administrator password</label><input id="adminPassword" type="password" autocomplete="current-password" required></div><div class="field"><label>New account password</label><input id="resetPassword" type="password" autocomplete="new-password" minlength="12" required></div><div class="field"><label>Confirm new password</label><input id="resetConfirm" type="password" autocomplete="new-password" minlength="12" required></div><div class="err hide" id="resetError" role="alert"></div><div class="dlgactions"><button type="button" class="btn secondary" id="cancelReset">Cancel</button><button class="btn primary" type="submit">Reset password</button></div></form>');
 layer.querySelector('#cancelReset').onclick=()=>layer.remove();
 layer.querySelector('form').onsubmit=async event=>{event.preventDefault();try{
  const password=layer.querySelector('#resetPassword').value;if(password!==layer.querySelector('#resetConfirm').value)throw Error('New passwords must match.');
  await client.request('users/password','POST',{id:account.id,current:layer.querySelector('#adminPassword').value,password});layer.remove();if(updated)updated();alert('Password updated on the household server.');
 }catch(e){const error=layer.querySelector('#resetError');error.textContent=e.message;error.classList.remove('hide')}};
}
root.FinanceAccounts={gate,hasLegacy,exportDevice,cleanup,importDialog,resetDialog};
})(window);
