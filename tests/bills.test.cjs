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
 const setClock=(y,m,d)=>{context.Date=class extends Date {constructor(...args){super(...(args.length?args:[y,m-1,d,12]))}static now(){return new Date(y,m-1,d,12).getTime()}}};
 setClock(2026,11,7);
 assert.equal(run('budgets().length'),1);
 assert.equal(run("billAmount(bills()[0],'2026-11-30')"),85);
 assert.equal(run("billAmount(bills()[0],'2026-12-31')"),0);
 assert.equal(run("billDueItems(2026,10)[0].date"),'2026-11-30');
 run("markBillPaid('electric','2026-11-30');markBillPaid('electric','2026-11-30')");
 assert.equal(run('expenses().length'),1);
 assert.equal(run('expenses()[0].date'),'2026-11-07');
 assert.equal(run('expenses()[0].billDueDate'),'2026-11-30');
 assert.equal(run('coverage()[0].over'),0);
 assert.equal(run("limit(budgets()[0],'month',monthDate('2026-12'))"),0);
 setClock(2026,12,7);
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
 setClock(2027,2,3);
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
 setClock(2026,11,7);
 // A legacy bill linked to an existing plan reuses that line.
 run("user.data=seed();D().activeBudgetMonth='2026-11';var existing=budgets()[0];D().bills=[{id:'linked',name:'Linked bill',category:existing.category,budgetId:existing.id,amount:40,frequency:'yearly',month:11,day:15}];var count=budgets().length;syncBillBudgets()");
 assert.equal(run('budgets().length'),run('count'));
 assert.equal(run('billDueItems(2026,11).length'),0);
 assert.equal(run("billDueItems(2027,10)[0].amount"),0);

 // Budget horizons include shorter cadences, never longer ones (including $0 lines).
 run("user.data=seed();D().activeBudgetMonth='2026-11';D().bills=[];D().budgets=['weekly','monthly','annual'].map(function(c,i){return {id:c,name:c+' test line',category:'Groceries',group:'Food',cadence:c,amount:(i+1)*100,active:true,history:[{from:'2026-01-01',cadence:c,amount:(i+1)*100}]}});D().budgets.push({id:'zero',name:'Zero yearly line',category:'Groceries',group:'Food',cadence:'annual',amount:0,active:true});$('#budgetSearch').value='';$('#budgetCadence').value='all';$('#budgetStatus').value='all';summaryMonth='current'");
 for(const [horizon,expected] of [['week',['weekly']],['month',['weekly','monthly']],['year',['weekly','monthly','annual']]]){
  run(`bp='${horizon}';renderBudgets()`);
  const rows=nodes['#budgetRows'].innerHTML;
  for(const cadence of ['weekly','monthly','annual'])assert.equal(rows.includes(cadence+' test line'),expected.includes(cadence),horizon+': '+cadence);
  assert.equal(rows.includes('Zero yearly line'),horizon==='year');
 }
 assert.equal(run("limit(item('monthly'),'week',monthDate('2026-11'))"),0);
 assert.equal(run("limit(item('annual'),'week',monthDate('2026-11'))"),0);
 assert.equal(run("limit(item('annual'),'month',monthDate('2026-11'))"),0);
 assert.equal(run("limit(item('weekly'),'month',monthDate('2026-11'))"),500);
 assert.equal(run("limit(item('monthly'),'month',monthDate('2026-11'))"),200);
 assert.ok(Math.abs(run("limit(item('monthly'),'year',monthDate('2026-11'))")-2200)<0.001);
 assert.ok(Math.abs(run("limit(item('annual'),'year',monthDate('2026-11'))")-300)<0.001);
 assert.equal(run("budgetTotal('week')"),100);
 assert.equal(run("budgetTotal('month')"),700);


 // Cadence filter narrows the selected horizon and works with search/status.
 for(const cadence of ['all','weekly','monthly','annual']){
  run(`bp='year';$('#budgetCadence').value='${cadence}';renderBudgets()`);
  const rows=nodes['#budgetRows'].innerHTML;
  for(const candidate of ['weekly','monthly','annual'])assert.equal(rows.includes(candidate+' test line'),cadence==='all'||cadence===candidate);
 }
 run("bp='month';$('#budgetCadence').value='annual';renderBudgets()");
 assert.ok(nodes['#budgetRows'].innerHTML.includes('No matching budget lines'));
 run("$('#budgetCadence').value='monthly';filters()");
 assert.equal(nodes['#budgetCadence'].value,'monthly');
 run("bp='year';$('#budgetSearch').value='no match';renderBudgets()");
 assert.ok(nodes['#budgetRows'].innerHTML.includes('No matching budget lines'));
 run("$('#budgetSearch').value='';$('#budgetCadence').value='all'");
 // Calendar-only exception: due this week at full price; yearly is entered amounts YTD.
 context.Date=class extends Date {constructor(...args){super(...(args.length?args:[2026,10,4,12]))}static now(){return new Date(2026,10,4,12).getTime()}};
 run("user.data=seed();D().activeBudgetMonth='2026-11';D().budgets=[];D().bills=[{id:'variable',name:'Variable utility',category:'Electricity',frequency:'monthly',day:6,active:true,monthlyAmounts:{'2025-12':999,'2026-01':80.25,'2026-10':90.50,'2026-11':110.75,'2026-12':500,'2027-01':999}}];syncBillBudgets();var billLine=budgets()[0];bp='week';renderBudgets()");
 assert.ok(nodes['#budgetRows'].innerHTML.includes('Variable utility'));
 assert.ok(nodes['#budgetRows'].innerHTML.includes('$110.75'));
 assert.equal(run("limit(billLine,'week')"),110.75);
 assert.equal(run("limit(billLine,'month')"),110.75);
 assert.equal(run("limit(billLine,'year')"),281.50);
 assert.equal(run("budgetTotal('year')"),281.50);
 run("bp='month';renderBudgets()");
 assert.ok(nodes['#budgetRows'].innerHTML.includes('$110.75'));
 run("bp='year';renderBudgets()");
 assert.ok(nodes['#budgetRows'].innerHTML.includes('$281.50'));
 run("bills()[0].day=20;bp='week';renderBudgets()");
 assert.ok(!nodes['#budgetRows'].innerHTML.includes('Variable utility'));
 assert.equal(run("budgetTotal('week')"),0);
 // A week spanning months uses the due occurrence's month, including next year.
 run("bills()[0].day=1;billLine.billAmounts={'2026-11':12,'2026-12':22,'2027-01':33}");
 assert.equal(run("limit(billLine,'week',new Date(2026,10,30,12))"),22);
 assert.equal(run("limit(billLine,'week',new Date(2026,11,31,12))"),33);
 assert.equal(run("limit(billLine,'year',new Date(2027,0,2,12))"),33);
 // Due day 31 clamps to February's last day, preserving the full amount.
 run("bills()[0].day=31;billLine.billAmounts={'2028-02':47.25}");
 assert.equal(run("limit(billLine,'week',new Date(2028,1,29,12))"),47.25);
 // Unset due bills stay visible at $0; the yearly total does not invent amounts.
 run("bills()[0].day=6;bills()[0].monthlyAmounts={};syncBillBudgets();bp='week';renderBudgets()");
 assert.ok(nodes['#budgetRows'].innerHTML.includes('Variable utility'));
 assert.equal(run("limit(billLine,'week')"),0);
 assert.equal(run("limit(billLine,'year')"),0);

 // Sunday the first belongs to the current week, including its recorded payment.
 run("bills()[0].day=1;bills()[0].monthlyAmounts={'2026-11':125};syncBillBudgets();D().transactions=[{id:'sunday-payment',billId:'variable',budgetId:billLine.id,date:'2026-11-01',amount:125}];bp='week';renderBudgets()");
 assert.equal(run('weekBounds().start'),'2026-11-01');
 assert.equal(run('weekBounds().end'),'2026-11-07');
 assert.ok(nodes['#budgetRows'].innerHTML.includes('Variable utility'));
 assert.equal(run("limit(billLine,'week')"),125);
 assert.equal(run("totalLine(billLine.id,'week')"),125);
 assert.equal(run("inPeriod('2026-10-31','week')"),false);
 assert.equal(run("startKey('2026-11-01','weekly')"),'2026-11-01');
 assert.equal(run("startKey('2026-11-07','weekly')"),'2026-11-01');
 assert.equal(run("startKey('2026-11-08','weekly')"),'2026-11-08');
 assert.equal(run("limit(billLine,'week',new Date(2026,10,8,12))"),0);
 run('renderCalendar()');
 assert.ok(nodes['#billCalendar'].innerHTML.startsWith('<div class="calendar-head">Sun</div>'));

 // MTD cash uses the current calendar month through today, independent of weekly view/active budget.
 run("D().activeBudgetMonth='2026-10';D().transactions=[{id:'mtd1',date:'2026-11-01',amount:125},{id:'mtd2',date:'2026-11-04',amount:75},{id:'old',date:'2026-10-31',amount:999},{id:'future',date:'2026-11-05',amount:888}];D().incomes=[{id:'pay',source:'Pay',date:'2026-11-02',amount:1000},{id:'oldpay',date:'2026-10-31',amount:777},{id:'futurepay',date:'2026-11-05',amount:666}];period='week';renderOverview()");
 assert.equal(run('monthToDateTotal(expenses())'),200);
 assert.equal(run('monthToDateTotal(income())'),1000);
 assert.ok(nodes['#overviewStats'].innerHTML.includes('MTD Net Cash'));
 assert.ok(nodes['#overviewStats'].innerHTML.includes('<strong>$577.00</strong>'));
 assert.ok(!nodes['#overviewStats'].innerHTML.includes(' spending = '));
 run("D().incomes=[];renderOverview()");
 assert.ok(nodes['#overviewStats'].innerHTML.includes('<strong>-$200.00</strong>'));


 // Last month's income funds this month; YTD aligns Dec-Oct funding with Jan-Nov spending.
 run("D().incomes=[{date:'2025-11-30',amount:9000},{date:'2025-12-31',amount:1000},{date:'2026-01-31',amount:800},{date:'2026-10-01',amount:600},{date:'2026-10-31',amount:50},{date:'2026-11-01',amount:7000},{date:'2026-12-01',amount:8000}];D().transactions=[{date:'2025-12-31',amount:9999},{date:'2026-01-01',amount:700},{date:'2026-02-28',amount:750},{date:'2026-11-01',amount:200},{date:'2026-11-04',amount:25},{date:'2026-11-05',amount:999},{date:'2026-12-01',amount:999}];renderOverview();renderSlush()");
 assert.equal(run('cashTotals().monthIncome'),650);
 assert.equal(run('cashTotals().monthSpending'),225);
 assert.equal(run('cashTotals().ytdIncome'),2450);
 assert.equal(run('cashTotals().ytdSpending'),1675);
 assert.ok(nodes['#overviewStats'].innerHTML.includes('<strong>$425.00</strong>'));
 assert.ok(nodes['#slushStats'].innerHTML.includes('YTD slush balance'));
 assert.ok(nodes['#slushStats'].innerHTML.includes('<strong>$775.00</strong>'));
 // January uses December income and no previous-year expenses or accumulated balance.
 assert.equal(run('cashTotals(new Date(2026,0,1,12)).monthIncome'),1000);
 assert.equal(run('cashTotals(new Date(2026,0,1,12)).ytdIncome'),1000);
 assert.equal(run('cashTotals(new Date(2026,0,1,12)).ytdSpending'),700);
 // Missing income and deficits stay visible; no double deduction for coverage.
 run("D().incomes=[];renderSlush()");
 assert.ok(nodes['#slushStats'].innerHTML.includes('<strong>-$1,675.00</strong>'));
 run("D().transactions=[];renderSlush()");
 assert.ok(nodes['#slushStats'].innerHTML.includes('<strong>$0.00</strong>'));
 // YTD allocations follow historical changes, with no future periods or backfilled creation dates.
 run("D().bills=[];D().budgets=[{id:'changingWeekly',name:'Weekly groceries',cadence:'weekly',amount:200,history:[{from:'2026-01-01',cadence:'weekly',amount:100},{from:'2026-01-11',cadence:'weekly',amount:150},{from:'2026-02-01',cadence:'weekly',amount:200}]},{id:'changingMonthly',name:'Monthly gas',cadence:'monthly',amount:90,history:[{from:'2026-01-01',cadence:'monthly',amount:40},{from:'2026-02-01',cadence:'monthly',amount:60},{from:'2026-12-01',cadence:'monthly',amount:90}]},{id:'newMonthly',name:'New monthly',cadence:'monthly',amount:25,history:[{from:'2026-11-01',cadence:'monthly',amount:25}]}]");
 assert.equal(run("limit(item('changingWeekly'),'year',new Date(2026,0,12,12))"),350);
 assert.equal(run("limit(item('changingMonthly'),'year',new Date(2026,1,15,12))"),100);
 assert.equal(run("limit(item('changingMonthly'),'year')"),640);
 assert.equal(run("limit(item('newMonthly'),'year')"),25);
 assert.equal(run("limit(item('newMonthly'),'year',new Date(2026,9,31,12))"),0);
 // Annual overview includes all annual lines and only YTD spending, with the same status bars.
 run("D().budgets=D().budgets.concat(Array.from({length:10},function(_,i){return {id:'annual'+i,name:'Annual item '+i,cadence:'annual',amount:100,history:[{from:'2026-01-01',cadence:'annual',amount:100}]}}));D().transactions=[{id:'annualspent',title:'Annual spend',date:'2026-11-01',budgetId:'annual0',amount:120},{id:'futurespent',date:'2026-12-01',budgetId:'annual1',amount:55},{id:'oldspent',date:'2025-12-01',budgetId:'annual1',amount:66}];period='year';renderOverview()");
 assert.ok(!nodes['#pulse'].innerHTML.includes('Weekly groceries'));
 assert.ok(!nodes['#pulse'].innerHTML.includes('Monthly gas'));
 assert.ok(nodes['#pulse'].innerHTML.includes('Annual item 9'));
 assert.ok(nodes['#pulse'].innerHTML.includes('Over $20.00'));
 assert.ok(!html.includes('annualStats'));
 assert.ok(!html.includes('annualPulse'));
 assert.ok(html.indexOf('<h3>Quick actions</h3>')<html.indexOf('id="recent"'));
 run("D().budgets=[];renderOverview()");
 assert.ok(nodes['#pulse'].innerHTML.includes('No annual budget items yet'));

 // Summary remaining cards use their own current horizons, and coverage is always YTD.
 run("user.data=seed();D().activeBudgetMonth='2026-10';D().budgets=[{id:'w',name:'Weekly',cadence:'weekly',amount:100,history:[{from:'2026-01-01',cadence:'weekly',amount:100}]},{id:'m',name:'Monthly',cadence:'monthly',amount:200,history:[{from:'2026-01-01',cadence:'monthly',amount:200}]}];D().bills=[{id:'due',name:'Due bill',category:'Electricity',frequency:'monthly',day:6,monthlyAmounts:{'2026-11':100},active:true}];syncBillBudgets();D().transactions=[{id:'priorYear',date:'2025-12-31',amount:20},{id:'priorWeek',date:'2026-01-03',amount:30},{id:'current',date:'2026-11-02',amount:60},{id:'future',date:'2026-11-05',amount:1000}];period='week';renderOverview()");
 assert.ok(nodes['#overviewStats'].innerHTML.includes('<label>Weekly Spend Remaining</label><strong>$140.00</strong>'));
 assert.ok(nodes['#overviewStats'].innerHTML.includes('<label>Monthly Spend Remaining</label><strong>$740.00</strong>'));
 assert.ok(nodes['#overviewStats'].innerHTML.includes('<label>Slush Coverage</label><strong>$90.00</strong>'));
 const summaryCards=nodes['#overviewStats'].innerHTML;
 run("period='year';renderOverview()");
 assert.equal(nodes['#overviewStats'].innerHTML,summaryCards);
 run("D().transactions.push({id:'overspend',date:'2026-11-03',amount:1000});renderOverview()");
 assert.ok(nodes['#overviewStats'].innerHTML.includes('<label>Weekly Spend Remaining</label><strong>$0.00</strong>'));
 assert.ok(nodes['#overviewStats'].innerHTML.includes('<label>Monthly Spend Remaining</label><strong>$0.00</strong>'));
 assert.ok(nodes['#overviewStats'].innerHTML.includes('Over plan by $860.00'));
 assert.ok(nodes['#overviewStats'].innerHTML.includes('Over plan by $260.00'));

 // Coming up includes tomorrow through day seven, never today, past dates or day eight.
 run("D().bills=[3,4,5,11,12].map(function(day){return {id:'day'+day,name:'Due day '+day,day:day,frequency:'monthly',active:true,monthlyAmounts:{'2026-11':10}}});renderWeekBills()");
 assert.equal(run('upcomingBillItems().map(function(x){return x.date}).join(",")'),'2026-11-05,2026-11-11');
 assert.ok(nodes['#weekBills'].innerHTML.includes('Due day 5'));
 assert.ok(nodes['#weekBills'].innerHTML.includes('Due day 11'));
 assert.ok(!nodes['#weekBills'].innerHTML.includes('Due day 4'));
 assert.ok(!nodes['#weekBills'].innerHTML.includes('Due day 3'));
 assert.ok(!nodes['#weekBills'].innerHTML.includes('Due day 12'));
 run("D().bills=[{id:'dec',name:'December',day:31,frequency:'monthly',active:true},{id:'jan',name:'January',day:4,month:1,frequency:'yearly',active:true},{id:'late',name:'Too late',day:5,month:1,frequency:'yearly',active:true}]");
 assert.equal(run('upcomingBillItems(new Date(2026,11,28,12)).map(function(x){return x.date}).join(",")'),'2026-12-31,2027-01-04');
 run('D().bills=[];renderWeekBills()');
 assert.ok(nodes['#weekBills'].innerHTML.includes('No bills due in the next 7 days.'));

 // Focus toggle strictly matches the native cadence and never rolls up calendar bills.
 run("D().budgets=[{id:'fw',name:'Weekly only',cadence:'weekly',amount:100,history:[{from:'2026-01-01',cadence:'weekly',amount:100}]},{id:'fm',name:'Monthly only',cadence:'monthly',amount:200,history:[{from:'2026-01-01',cadence:'monthly',amount:200}]},{id:'fa',name:'Annual only',cadence:'annual',amount:300,history:[{from:'2026-01-01',cadence:'annual',amount:300}]}];D().bills=[{id:'fc',name:'Calendar monthly',category:'Electricity',frequency:'monthly',day:6,monthlyAmounts:{'2026-01':80,'2026-11':120},active:true}];D().transactions=[];syncBillBudgets()");
 const labels={week:'Weekly only',month:'Monthly only',year:'Annual only'};
 for(const selected of ['week','month','year']){
  run(`$('#focusPeriods').onclick({target:{closest(){return {dataset:{period:'${selected}'}}}}})`);
  assert.equal(nodes['#overviewHeading'].textContent,'Your '+selected+', in focus');
  for(const [key,label] of Object.entries(labels))assert.equal(nodes['#pulse'].innerHTML.includes(label),key===selected);
  assert.equal(nodes['#pulse'].innerHTML.includes('Calendar monthly'),selected==='month');
  assert.ok(nodes['#pulse'].innerHTML.includes({week:'$100.00',month:'$200.00',year:'$300.00'}[selected]));
  if(selected==='month')assert.ok(nodes['#pulse'].innerHTML.includes('$120.00'));
 }

 // Paid-early calendar transactions use scheduled due dates, but are already spent.
 run("D().budgets=[];D().bills=[{id:'electricPaid',name:'Electric paid early',category:'Electricity',frequency:'monthly',day:20,active:true,monthlyAmounts:{'2026-11':85},paid:{'2026-11-20':true}},{id:'internetPaid',name:'Internet paid early',category:'Internet',frequency:'monthly',day:25,active:true,monthlyAmounts:{'2026-11':75},paid:{'2026-11-25':true}}];D().transactions=[{id:'pe',billId:'electricPaid',date:'2026-11-20',amount:85},{id:'pi',billId:'internetPaid',date:'2026-11-25',amount:75}];syncBillBudgets();period='month';renderOverview()");
 assert.equal(run("focusSpending(budgets().find(function(b){return b.billId==='electricPaid'}),'month')"),85);
 assert.equal(run("focusSpending(budgets().find(function(b){return b.billId==='internetPaid'}),'month')"),75);
 assert.ok(nodes['#pulse'].innerHTML.includes('$85.00 <small>/ $85.00</small>'));
 assert.ok(nodes['#pulse'].innerHTML.includes('$75.00 <small>/ $75.00</small>'));
 assert.ok(nodes['#pulse'].innerHTML.includes('100% used'));
 // Linked transaction and bill IDs identify one expense, never two copies.
 run("syncBillBudgets();renderOverview()");
 assert.equal(run("focusSpending(budgets()[0],'month')"),85);
 run("bills()[0].paid={};renderOverview()");
 assert.equal(run("focusSpending(budgets()[0],'month')"),0);
 run("D().transactions[0].date='2026-10-20';bills()[0].paid={'2026-10-20':true};renderOverview()");
 assert.equal(run("focusSpending(budgets()[0],'month')"),0);

 // Payment dates are the day of marking paid, for early and late bills and next-year dues.
 run("user.data=seed();D().budgets=[];D().bills=[{id:'early',name:'Early bill',category:'Electricity',frequency:'monthly',day:20,monthlyAmounts:{'2026-11':85}},{id:'late',name:'Late bill',category:'Internet',frequency:'monthly',day:1,monthlyAmounts:{'2026-11':75}},{id:'nextYear',name:'Next year bill',category:'Electricity',frequency:'yearly',month:1,day:1,monthlyAmounts:{'2027-01':25}}];markBillPaid('early','2026-11-20');markBillPaid('late','2026-11-01');markBillPaid('nextYear','2027-01-01')");
 assert.equal(run('expenses().map(function(t){return t.date}).join(",")'),'2026-11-04,2026-11-04,2026-11-04');
 assert.equal(run('expenses().map(function(t){return t.billDueDate}).join(",")'),'2026-11-20,2026-11-01,2027-01-01');
 assert.equal(run("sum(expenses(),'year')"),185);
 assert.equal(run("sum(expenses(),'all')"),185);
 run("markBillPaid('early','2026-11-20');markBillPaid('early','2026-11-21');markBillPaid('nextYear','2027-01-01')");
 assert.equal(run('expenses().length'),3);
 assert.equal(run("bills()[0].paid['2026-11-20']"),true);
 run("lp='year';renderLedger()");
 assert.ok(nodes['#ledgerRows'].innerHTML.includes('2026-11-04'));
 assert.ok(!nodes['#ledgerRows'].innerHTML.includes('<td>2027-01-01</td>'));
 const yearStats=nodes['#ledgerStats'].innerHTML.replaceAll('This Year','PERIOD');
 run("lp='all';renderLedger()");
 assert.equal(nodes['#ledgerStats'].innerHTML.replaceAll('All time','PERIOD'),yearStats);

 // Ledger This Year includes future dates within the year, with matching rows and coverage.
 run("D().transactions=[{id:'jan',title:'January',date:'2026-01-01',amount:10},{id:'dec',title:'December',date:'2026-12-31',amount:20}];D().incomes=[{id:'pay',source:'Future pay',date:'2026-12-31',amount:100}];$('#ledgerType').value='all';lp='year';renderLedger()");
 assert.ok(nodes['#ledgerRows'].innerHTML.includes('December'));
 assert.ok(nodes['#ledgerRows'].innerHTML.includes('Future pay'));
 assert.ok(nodes['#ledgerStats'].innerHTML.includes('<strong>$30.00</strong>'));
 assert.ok(nodes['#ledgerStats'].innerHTML.includes('<strong>$100.00</strong>'));
 assert.equal(nodes['#ledgerChartPeriod'].textContent,'This Year');
 assert.equal((nodes['#ledgerBars'].innerHTML.match(/class="barcol"/g)||[]).length,12);
 const thisYearCards=nodes['#ledgerStats'].innerHTML.replaceAll('This Year','PERIOD');
 run("lp='all';renderLedger()");
 assert.equal(nodes['#ledgerStats'].innerHTML.replaceAll('All time','PERIOD'),thisYearCards);
 run("D().transactions.push({id:'old',title:'Previous year',date:'2025-12-31',amount:999},{id:'next',title:'Next year',date:'2027-01-01',amount:888});lp='year';renderLedger()");
 assert.ok(!nodes['#ledgerRows'].innerHTML.includes('Previous year'));
 assert.ok(!nodes['#ledgerRows'].innerHTML.includes('Next year'));
 // Summary/Slush YTD still stop at today.
 assert.equal(run("sum(expenses(),'year')"),10);
 assert.equal(run('cashTotals().ytdSpending'),10);
 console.log(file+': bill, payment, rollover and budget horizon checks passed');
}

