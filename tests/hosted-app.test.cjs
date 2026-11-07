// Runs against the disposable household server created by test_server.py.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const endpoint=process.argv[2];
if(!endpoint)throw Error('This check requires the disposable server URL from test_server.py.');
async function browser(file){
 const nodes=new Map(),storage=new Map();let cookie='';
 function node(){return {value:'all',innerHTML:'',textContent:'',disabled:false,style:{},dataset:{},options:[],childNodes:[],classList:{add(){},remove(){},toggle(){}},setAttribute(){},addEventListener(){},querySelector(){return node()},querySelectorAll(){return []}}}
 const context=vm.createContext({console,Date,Intl,Math,JSON,Number,String,Array,Object,Promise,Set,Map,Symbol,Uint8Array,TextEncoder,Error,localStorage:{setItem(k,v){storage.set(k,v)},getItem(k){return storage.get(k)||null},removeItem(k){storage.delete(k)}},document:{querySelector(s){if(!nodes.has(s))nodes.set(s,node());return nodes.get(s)},querySelectorAll(){return []},documentElement:node(),createElement:node},window:{FITZGERALD_SHARED:true,addEventListener(){},location:{reload(){}}},navigator:{},setInterval(){return 1},clearInterval(){},confirm:()=>true,alert(){},setTimeout,
 fetch:async(path,options={})=>{const response=await fetch(endpoint+path,{...options,headers:{...options.headers,...(cookie?{Cookie:cookie}:{})}});const fresh=response.headers.get('set-cookie');if(fresh)cookie=fresh.split(';')[0];return response;}});
 vm.runInContext(fs.readFileSync('shared-client.js','utf8'),context);context.FinanceServer=context.window.FinanceServer;
 const script=fs.readFileSync(file,'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
 vm.runInContext(script.slice(script.indexOf("'use strict';"),script.lastIndexOf('load().then')),context);
 const run=s=>vm.runInContext(s,context);
 await run('load()');assert.equal(run('sharedMode'),true);assert.equal(run('db.users.length'),0);assert.equal(run('user'),null);
 run("$('#username').value='householdAdmin';$('#password').value='test-household-password'");await run('sharedLogin()');
 assert.equal(run('user.username'),'householdAdmin');assert.equal(run('user.salt'),undefined);
 assert.equal(storage.has('fitzgeraldFinance.v1'),false);
 return {run,nodes,context};
}
async function idle(app){for(let i=0;i<200&&app.run('sharedClient.saving');i++)await new Promise(r=>setTimeout(r,10));assert.equal(app.run('sharedClient.blocked'),false);assert.equal(app.run('sharedClient.saving'),false);}
(async()=>{
 for(const file of ['index.html','app/src/main/assets/www/index.html']){
  const a=await browser(file),b=await browser(file),tag=file.startsWith('app/')?'android':'web';
  a.run(`D().incomes.push({id:'${tag}-a',source:'Shared test A',date:iso(),amount:10});saveUser()`);await idle(a);
  await b.run('sharedClient.poll()');assert.ok(b.run(`income().some(x=>x.id==='${tag}-a')`));
  a.run(`D().incomes.push({id:'${tag}-b',source:'Shared test B',date:iso(),amount:20});saveUser()`);
  b.run(`D().incomes.push({id:'${tag}-c',source:'Shared test C',date:iso(),amount:30});saveUser()`);
  await idle(a);await idle(b);await a.run('sharedClient.poll()');
  for(const suffix of ['a','b','c'])assert.ok(a.run(`income().some(x=>x.id==='${tag}-${suffix}')`));
  assert.equal(a.nodes.get('#sharedMessage').textContent,'Saved to household server');
  assert.equal(a.run('income().filter(x=>x.id.startsWith("'+tag+'-")).length'),3);
  console.log(file+': hosted sign-in, shared saves, polling and simultaneous additions passed');
 }
})().catch(error=>{console.error(error);process.exitCode=1});
