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
 console.log('Shared sync checks passed: merge, conflicts, deletions, offline recovery.');
})().catch(error=>{console.error(error);process.exitCode=1});
