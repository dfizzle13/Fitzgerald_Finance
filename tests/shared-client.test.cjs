const assert=require('node:assert/strict');
const FinanceServer=require('../shared-client.js');
const clone=x=>JSON.parse(JSON.stringify(x));
const merge=FinanceServer.merge;
const base={transactions:[{id:'one',amount:10}],bills:[{id:'bill',paid:{}}]};
assert.deepEqual(merge(base,{...base,transactions:[...base.transactions,{id:'two',amount:20}]},{...base,transactions:[...base.transactions,{id:'three',amount:30}]}).transactions.map(x=>x.id).sort(),['one','three','two']);
assert.throws(()=>merge(base,{...base,transactions:[{id:'one',amount:11}]},{...base,transactions:[{id:'one',amount:12}]}),/same item/);
assert.deepEqual(merge(base,{...base,bills:[{id:'bill',paid:{'2026-11-01':true}}]},{...base,bills:[{id:'bill',paid:{'2026-12-01':true}}]}).bills[0].paid,{'2026-11-01':true,'2026-12-01':true});
assert.deepEqual(merge(base,{...base,transactions:[]},base).transactions,[]);
assert.throws(()=>merge(base,{...base,transactions:[]},{...base,transactions:[{id:'one',amount:12}]}),/same item/);
global.localStorage={setItem(){throw Error('Financial writes to local storage are forbidden')},removeItem(){throw Error('Transport must not use financial local storage')}};
(async()=>{
 let server=clone(base),revision=1,states=[],messages=[];
 global.fetch=async(url,options)=>{
  const request=JSON.parse(options.body);
  if(request.revision!==revision)return {ok:false,status:409,json:async()=>({data:clone(server),revision})};
  server=clone(request.data);revision++;
  return {ok:true,json:async()=>({data:clone(server),revision})};
 };
 const hooks={state:data=>states.push(data),status:(message,error)=>messages.push({message,error}),idle:()=>true};
 const a=new FinanceServer(hooks),b=new FinanceServer(hooks);
 for(const client of [a,b])client.accept({user:{id:'test'},csrf:'csrf',data:clone(base),revision:1});
 a.stage({...clone(base),transactions:[...base.transactions,{id:'two',amount:20}]});
 while(a.saving)await new Promise(r=>setTimeout(r,1));
 b.stage({...clone(base),transactions:[...base.transactions,{id:'three',amount:30}]});
 while(b.saving)await new Promise(r=>setTimeout(r,1));
 assert.deepEqual(server.transactions.map(x=>x.id).sort(),['one','three','two']);
 // Stale same-item edits must remain unsaved, with the server unchanged.
 a.stage({...clone(base),transactions:[{id:'one',amount:11}]});
 while(a.saving)await new Promise(r=>setTimeout(r,1));
 const c=new FinanceServer(hooks);
 c.accept({user:{id:'test'},csrf:'csrf',data:clone(server),revision});
 server.transactions[0].amount=99;revision++;
 c.stage({...clone(c.base),transactions:c.base.transactions.map(x=>({...x,amount:x.id==='one'?22:x.amount}))});
 while(c.saving)await new Promise(r=>setTimeout(r,1));
 assert.equal(c.blocked,true);assert.ok(c.desired);assert.equal(server.transactions[0].amount,99);
 // Interrupted saves remain pending and can be retried.
 const d=new FinanceServer(hooks);d.accept({user:{id:'test'},csrf:'csrf',data:clone(server),revision});
 const originalFetch=global.fetch;global.fetch=async()=>{throw Error('offline')};
 d.stage({...clone(server),theme:'paper'});while(d.saving)await new Promise(r=>setTimeout(r,1));
 assert.equal(d.blocked,true);assert.ok(d.desired);
 global.fetch=originalFetch;await d.retry();assert.equal(d.blocked,false);assert.equal(server.theme,'paper');
 // A rejected validation keeps the draft but allows the next corrected edit to save.
 const validationClient=new FinanceServer(hooks);
 validationClient.accept({user:{id:'test'},csrf:'csrf',data:clone(server),revision});
 global.fetch=async(url,options)=>{
  const body=JSON.parse(options.body);
  if(body.data.theme==='invalid')return {ok:false,status:400,json:async()=>({error:'Choose a supported theme.'})};
  return originalFetch(url,options);
 };
 validationClient.stage({...clone(server),theme:'invalid'});
 while(validationClient.saving)await new Promise(r=>setTimeout(r,1));
 assert.equal(validationClient.blocked,false);assert.equal(validationClient.desired.theme,'invalid');
 assert.ok(messages.at(-1).message.includes('Choose a supported theme.'));
 assert.ok(!messages.at(-1).message.includes('Reconnect'));
 validationClient.stage({...clone(server),theme:'evergreen'});
 while(validationClient.saving)await new Promise(r=>setTimeout(r,1));
 assert.equal(validationClient.desired,null);assert.equal(server.theme,'evergreen');
 // A correction queued while the failed request is in flight must also save automatically.
 let rejectPending;
 const queued=new FinanceServer(hooks);queued.accept({user:{id:'test'},csrf:'csrf',data:clone(server),revision});
 global.fetch=(url,options)=>{
  const body=JSON.parse(options.body);
  if(body.data.theme==='invalid')return new Promise(resolve=>{rejectPending=()=>resolve({ok:false,status:400,json:async()=>({error:'Invalid edit.'})})});
  return originalFetch(url,options);
 };
 queued.stage({...clone(server),theme:'invalid'});
 queued.stage({...clone(server),theme:'midnight'});rejectPending();
 while(queued.saving)await new Promise(r=>setTimeout(r,1));
 assert.equal(queued.blocked,false);assert.equal(queued.desired,null);assert.equal(server.theme,'midnight');
 global.fetch=originalFetch;
 console.log('Shared sync checks passed: merge, conflicts, deletions, offline recovery.');
})().catch(error=>{console.error(error);process.exitCode=1});
