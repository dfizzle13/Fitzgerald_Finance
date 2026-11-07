const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
for (const file of ['index.html', 'app/src/main/assets/www/index.html']) {
 const html=fs.readFileSync(file,'utf8');
 const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
 new vm.Script(script);
 const nodes={};
 const node=()=>({value:'all',options:[],innerHTML:'',style:{},dataset:{},classList:{add(){},remove(){},toggle(){}},addEventListener(){},querySelector(){return node()},querySelectorAll(){return []}});
 const context=vm.createContext({console,Date,Intl,Math,JSON,Number,String,Array,Object,Promise,Set,Uint8Array,TextEncoder,localStorage:{setItem(){},getItem(){return null}},document:{querySelector(s){return nodes[s]||(nodes[s]=node())},querySelectorAll(){return []},documentElement:node(),addEventListener(){}},window:{addEventListener(){}},navigator:{},confirm:()=>true,alert(){},setTimeout(){}});
 vm.runInContext(script.slice(script.indexOf("'use strict';"),script.lastIndexOf('load().then')),context);
 vm.runInContext(`
 user={data:seed()};db={users:[user]};D().activeBudgetMonth='2026-11';
 D().budgets=[];D().bills=[{id:'electric',name:'Electric',category:'Electricity',amount:85,frequency:'monthly',day:31,active:true}];
 syncBillBudgets();
 `,context);
 const run=s=>vm.runInContext(s,context);
 assert.equal(run('budgets().length'),1);
 assert.equal(run("billAmount(bills()[0],'2026-11-30')"),85);
 assert.equal(run("billAmount(bills()[0],'2026-12-31')"),0);
 assert.equal(run("billDueItems(2026,10)[0].date"),'2026-11-30');
 run("markBillPaid('electric','2026-11-30');markBillPaid('electric','2026-11-30')");
 assert.equal(run('expenses().length'),1);
 assert.equal(run('coverage()[0].over'),0);
 assert.equal(run("limit(budgets()[0],'month',monthDate('2026-12'))"),0);
 run("bills()[0].monthlyAmounts['2026-12']=112.34;syncBillBudgets();markBillPaid('electric','2026-12-31')");
 assert.equal(run('expenses()[1].amount'),112.34);
 assert.equal(run('coverage()[1].over'),0);
 assert.equal(run("limit(budgets()[0],'month',monthDate('2026-11'))"),85);
 run("archives().push(snapshotMonth('2026-11'))");
 const saved=run('JSON.stringify(archives()[0])');
 run("bills()[0].monthlyAmounts['2027-01']=50;syncBillBudgets()");
 assert.equal(run('JSON.stringify(archives()[0])'),saved);
 run("summaryMonth='2026-11';renderBudgets()");
 assert.match(nodes['#budgetMonthHeading'].textContent,/archived budget/);
 assert.ok(!nodes['#budgetRows'].innerHTML.includes('data-edit-budget'));
 run("summaryMonth='current';renderBudgets()");
 assert.match(nodes['#budgetMonthHeading'].textContent,/Budget for/);
 assert.ok(html.indexOf('id="summaryMonthSelect"')>html.indexOf('id="budgetRows"'));
 // A new month cannot silently record a zero-dollar payment.
 const before=run('expenses().length');
 run("markBillPaid('electric','2027-02-28')");
 assert.equal(run('expenses().length'),before);
 assert.match(nodes['#modal'].innerHTML,/Set Electric/);
 nodes['#monthlyBillAmount']={value:'99.25'};
 run("$('#modal form').onsubmit({preventDefault(){}})");
 assert.equal(run("billAmount(bills()[0],'2027-02-28')"),99.25);
 assert.equal(run("limit(budgets()[0],'month',monthDate('2027-02'))"),99.25);
 run("markBillPaid('electric','2027-02-28')");
 assert.equal(run('expenses().length'),before+1);
 assert.equal(run('coverage().slice(-1)[0].over'),0);
 // A legacy bill linked to an existing plan reuses that line.
 run("user.data=seed();D().activeBudgetMonth='2026-11';var existing=budgets()[0];D().bills=[{id:'linked',name:'Linked bill',category:existing.category,budgetId:existing.id,amount:40,frequency:'yearly',month:11,day:15}];var count=budgets().length;syncBillBudgets()");
 assert.equal(run('budgets().length'),run('count'));
 assert.equal(run('billDueItems(2026,11).length'),0);
 assert.equal(run("billDueItems(2027,10)[0].amount"),0);

 // Budget horizons include shorter cadences, never longer ones (including $0 lines).
 run("user.data=seed();D().activeBudgetMonth='2026-11';D().bills=[];D().budgets=['weekly','monthly','annual'].map(function(c,i){return {id:c,name:c+' test line',category:'Groceries',group:'Food',cadence:c,amount:(i+1)*100,active:true,history:[{from:'2026-01-01',cadence:c,amount:(i+1)*100}]}});D().budgets.push({id:'zero',name:'Zero yearly line',category:'Groceries',group:'Food',cadence:'annual',amount:0,active:true});$('#budgetSearch').value='';$('#budgetGroup').value='all';$('#budgetStatus').value='all';summaryMonth='current'");
 for(const [horizon,expected] of [['week',['weekly']],['month',['weekly','monthly']],['year',['weekly','monthly','annual']]]){
  run(`bp='${horizon}';renderBudgets()`);
  const rows=nodes['#budgetRows'].innerHTML;
  for(const cadence of ['weekly','monthly','annual'])assert.equal(rows.includes(cadence+' test line'),expected.includes(cadence),horizon+': '+cadence);
  assert.equal(rows.includes('Zero yearly line'),horizon==='year');
 }
 assert.equal(run("limit(item('monthly'),'week',monthDate('2026-11'))"),0);
 assert.equal(run("limit(item('annual'),'week',monthDate('2026-11'))"),0);
 assert.equal(run("limit(item('annual'),'month',monthDate('2026-11'))"),0);
 assert.equal(run("limit(item('weekly'),'month',monthDate('2026-11'))"),600);
 assert.equal(run("limit(item('monthly'),'month',monthDate('2026-11'))"),200);
 assert.ok(Math.abs(run("limit(item('monthly'),'year',monthDate('2026-11'))")-2400)<0.001);
 assert.ok(Math.abs(run("limit(item('annual'),'year',monthDate('2026-11'))")-300)<0.001);
 assert.equal(run("budgetTotal('week')"),100);
 assert.equal(run("budgetTotal('month')"),800);
 console.log(file+': bill, payment, rollover and budget horizon checks passed');
}

