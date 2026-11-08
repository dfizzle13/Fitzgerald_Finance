/* Shared-server transport. Local standalone copies do not activate this client. */
(function(root){
'use strict';
const copy=value=>JSON.parse(JSON.stringify(value));
const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const missing=Symbol('missing');
function merge(base,local,remote,path='household'){
 if(equal(local,remote))return local;
 if(equal(local,base))return remote;
 if(equal(remote,base))return local;
 if([base,local,remote].every(x=>Array.isArray(x))){
  const key=x=>x&&typeof x==='object'&&(x.id||x.key||x.name);
  if([base,local,remote].every(a=>a.every(key)&&new Set(a.map(key)).size===a.length)){
   const maps=[base,local,remote].map(a=>new Map(a.map(x=>[key(x),x])));
   return [...new Set([...remote,...local,...base].map(key))].map(id=>merge(...maps.map(m=>m.has(id)?m.get(id):missing),path+'.'+id)).filter(x=>x!==missing);
  }
 }
 if([base,local,remote].every(x=>x!==missing&&x&&typeof x==='object'&&!Array.isArray(x))){
  const result={};
  for(const key of new Set([...Object.keys(base),...Object.keys(local),...Object.keys(remote)])){
   const value=merge(...[base,local,remote].map(x=>Object.hasOwn(x,key)?x[key]:missing),path+'.'+key);
   if(value!==missing)result[key]=value;
  }
  return result;
 }
 throw Error('Both devices changed the same item. Download your unsaved changes, then reload the shared budget.');
}
class FinanceServer {
 constructor(hooks){this.hooks=hooks;this.base=null;this.revision=0;this.desired=null;this.saving=false;this.blocked=false;this.csrf='';this.user=null;}
 async request(path,method='GET',body){
  const response=await fetch(((typeof document!=='undefined'&&document.baseURI)?new URL('./api/',document.baseURI).pathname:'/api/')+path,{method,credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-Finance-Request':'1','X-CSRF-Token':this.csrf,'ngrok-skip-browser-warning':'1'},body:body===undefined?undefined:JSON.stringify(body)});
  let result;try{result=await response.json()}catch{throw Error('The household server is unavailable. Your changes are not saved yet.')}
  if(!response.ok){const error=Error(result.error||'Server request failed.');error.status=response.status;error.result=result;throw error;}
  return result;
 }
 accept(result){this.user=result.user;this.csrf=result.csrf;this.base=copy(result.data);this.revision=result.revision;this.desired=null;this.blocked=false;this.hooks.status('Saved to household server');return Object.assign({},result.user,{data:copy(result.data)});}
 draftKey(){return 'fitzgeraldFinance.sharedDraft.'+(this.user?this.user.id:'pending')}
 stage(data){if(!this.user)return;if(this.base&&equal(data,this.base)&&!this.desired&&!this.blocked)return;this.desired=copy(data);this.hooks.status(this.blocked?'Changes waiting — resolve the save issue below':'Saving…',this.blocked);if(!this.saving&&!this.blocked)this.flush();}
 async flush(){
  if(this.saving||this.blocked||!this.desired)return;
  this.saving=true;
  try{
   let conflicts=0;
   while(this.desired){
    const local=this.desired;this.desired=null;
    try{
     const result=await this.request('state','PUT',{revision:this.revision,data:local});
     this.base=copy(result.data);this.revision=result.revision;
     if(this.desired)this.desired=copy(merge(local,this.desired,this.base));
     else this.hooks.state(copy(this.base));
    }catch(error){
     if(error.status===409&&conflicts++<5){
      const latest=this.desired||local;
      try{const merged=merge(this.base,latest,error.result.data);this.base=copy(error.result.data);this.revision=error.result.revision;this.desired=copy(merged);continue;}
      catch(conflict){this.desired=latest;throw conflict;}
     }
     this.desired=this.desired||local;throw error;
    }
   }
   this.hooks.status('Saved to household server');
  }catch(error){this.blocked=true;this.hooks.status((error.message||'Connection lost.')+' Unsaved changes remain only in this open window. Reconnect and retry before closing.',true);}
  finally{this.saving=false;}
 }
 async poll(){
  if(!this.user||this.saving||this.desired||this.blocked||!this.hooks.idle())return;
  try{const result=await this.request('state');if(this.saving||this.desired||this.blocked||!this.hooks.idle())return;if(result.revision!==this.revision){this.base=copy(result.data);this.revision=result.revision;this.hooks.state(copy(result.data));}this.hooks.status('Saved to household server');}
  catch(error){this.hooks.status(error.status===401?'Session expired. Reload and sign in.':'Server unavailable — reconnect to sync.',true);}
 }
 retry(){this.blocked=false;return this.desired?this.flush():this.poll();}
}
FinanceServer.merge=merge;
root.FinanceServer=FinanceServer;
if(typeof module!=='undefined')module.exports=FinanceServer;
})(typeof window==='undefined'?globalThis:window);
