/* Screens: Floors 03-07, action delegation, init. */

function screen03(d){
  var h = '<h2>Floor 03 · Risk Manager</h2>'
    + banner('RESEARCH ONLY: sizing and risk/reward below are illustrations from end-of-day data, not instructions.','sim');
  if(!d) return h + '<p class="dim">Loading…</p>';
  h += errBox(d);
  var cur = d.current;
  if(!cur){
    h += '<div class="banner info">Run a research on Floor 02 first. Recent stored findings are shown below.</div>' + table(d.findings);
    return h;
  }
  var rk = cur.risk || {}, sev = rk.risk_class;
  h += banner('Risk class: <b>'+esc(sev)+'</b> (score '+fmt(rk.risk_score)+'/100, higher = more risk)', sev==='CRITICAL'||sev==='HIGH'?'crit':sev==='MODERATE'||sev==='UNASSESSED'?'warn':'sim');
  if(sev==='CRITICAL') h += banner('A critical risk is present. No score can override it.','crit');
  h += table(rk.findings)
    + '<details><summary>Checks not performed (unknown is not the same as passed)</summary>'
    + table(Object.keys(rk.unassessed_checks||{}).map(function(k){ return {check:k, reason:rk.unassessed_checks[k]}; })) + '</details>';
  var df = d.defaults || {};
  h += '<div class="section">Trade setup assessment (illustrative)</div>'
    + '<div class="grid g4">'
    + inp('as-cap','Simulated capital (INR)','number',df.paper_capital)
    + inp('as-rp','Risk per trade %','number',df.risk_per_trade_pct,'0.1')
    + inp('as-mp','Max position %','number',df.max_position_pct)
    + inp('as-ms','Max sector %','number',df.max_sector_pct)
    + '</div><div class="btnrow"><button class="btn" data-act="assess">Assess trade setup</button></div>';
  var a = d.assessResult || cur.assessment;
  if(a){
    h += '<p><b>Verdict: '+esc(a.verdict)+'</b> ('+esc(a.label)+')</p>'
      + kv({entry:a.entry, stop:a.stop, target:a.target, target_basis:a.target_basis, risk_reward:a.risk_reward, qty:a.qty,
            position_value:a.position_value, risk_amount:a.risk_amount, risk_per_share:a.risk_per_share})
      + table(a.checks);
  }
  return h;
}

function screen04(d){
  var h = '<h2>Floor 04 · Paper Executor</h2>'
    + banner('SIMULATED. No broker is connected and no real order is ever placed. Fills use the last known end-of-day close plus slippage.','sim');
  if(!d) return h + '<p class="dim">Loading…</p>';
  h += errBox(d);
  var df = d.defaults || {};
  h += '<div class="grid g5" style="align-items:end">'
    + inp('po-sym','Symbol','text',df.symbol)
    + sel('po-ex','Exchange',['NSE','BSE'],df.exchange||'NSE')
    + sel('po-side','Side',['BUY','SELL'],'BUY')
    + inp('po-qty','Quantity','number',df.qty)
    + inp('po-px','Reference price (last close)','number',df.price,'0.01')
    + '</div><div class="grid g2" style="max-width:520px">'
    + inp('po-stop','Stop-loss (0 = none)','number',df.stop,'0.01')
    + inp('po-tgt','Target (0 = none)','number',df.target,'0.01')
    + '</div><div class="btnrow"><button class="btn primary" data-act="place_order">Place SIMULATED order</button>'
    + '<button class="btn" data-act="check_exits">Check stop-loss / target exits now</button></div>';
  if(d.placed) h += banner('Order processed. See history below (rejections are recorded with their reason).','okbox');
  if(d.exits) h += '<p>'+esc(d.exits.length ? JSON.stringify(d.exits) : 'No simulated exits triggered.')+'</p>';
  h += '<div class="section">Open simulated positions</div>' + table(d.open)
    + '<div class="section">Order history (SIMULATED)</div>' + table(d.orders)
    + '<div class="section">Closed trades (SIMULATED)</div>' + table(d.closed);
  return h;
}

function screen05(d){
  var h = '<h2>Floor 05 · Monitor & Alerts</h2>'
    + banner('Checks run on end-of-day (delayed) data when the pipeline runs, not live. Exchange announcement monitoring is not built yet; news alerts come from unverified headlines.','warn');
  if(!d) return h + '<p class="dim">Loading…</p>';
  h += errBox(d);
  if(d.fired !== undefined) h += banner(esc(d.fired)+' rule(s) fired.','info');
  h += '<div class="section">Open alerts</div>' + table(d.alerts);
  if(d.alerts && d.alerts.length){
    h += '<div class="btnrow">'+sel('ack-pick','Acknowledge alert', d.alerts.map(function(a){return String(a.id);}), String(d.alerts[0].id))
      + '<div><button class="btn" data-act="ack_alert">Acknowledge</button></div></div>';
  }
  h += '<div class="section">Price rules <span class="floorid">checked against the last daily close</span></div>'
    + '<div class="grid g5" style="align-items:end">'
    + inp('pr-sym','Symbol','text','') + sel('pr-ex','Exchange',['NSE','BSE'],'NSE') + sel('pr-dir','Direction',['above','below'],'above')
    + inp('pr-px','Price','number','','0.01')
    + '<div><button class="btn" data-act="add_price_rule">Add rule</button></div></div>'
    + '<div class="btnrow"><button class="btn" data-act="check_price_rules">Check price rules now</button></div>'
    + table(d.rules)
    + '<div class="section">Watchlist</div>' + table(d.watchlist);
  return h;
}

function screen06(d){
  var h = '<h2>Floor 06 · Portfolio Manager</h2>'
    + banner('SIMULATED paper portfolio. Not connected to any broker or real account.','sim');
  if(!d) return h + '<p class="dim">Loading…</p>';
  h += errBox(d);
  var sm = d.summary || {};
  h += '<div class="btnrow"><button class="btn" data-act="f06_refresh">Refresh prices from provider</button>'
    + '<button class="btn" data-act="snapshot">Take portfolio snapshot now</button></div>'
    + '<div class="cards">'
    + card('Equity', fmt(sm.equity)) + card('Cash', fmt(sm.cash)) + card('Total return', fmt(sm.total_return, true))
    + card('Realized P&L', fmt(sm.realized_pnl)) + card('Unrealized P&L', fmt(sm.unrealized_pnl)) + '</div>'
    + table(sm.holdings);
  var se = sm.sector_exposure_pct || {};
  if(Object.keys(se).length){
    h += '<div class="section">Sector exposure</div><canvas class="chart" id="cv-sector"></canvas>'
      + '<p class="dim small">Largest single position: '+fmt((sm.largest_position_pct||0)/100, true)+' of equity.</p>';
  }
  var perf = d.performance || {};
  if((perf.points||[]).length >= 2){
    h += '<div class="section">Equity curve (snapshots)</div><canvas class="chart" id="cv-equity"></canvas>'
      + '<p>Max drawdown: '+fmt(perf.max_drawdown, true)+'</p>';
  } else h += '<p class="dim small">'+esc(perf.note||'No snapshots yet.')+'</p>';
  return h;
}

function screen07(d){
  var h = '<h2>Floor 07 · Final Decision Engine</h2>'
    + '<p class="dim small">APPROVE only means worth paper-trading or deeper study. Thresholds: '
    + (d && d.thresholds ? Object.keys(d.thresholds).map(function(k){return k+'='+d.thresholds[k];}).join(', ') : '') + '</p>';
  if(!d) return h + '<p class="dim">Loading…</p>';
  h += errBox(d);
  var rows = d.rows || [];
  if(!rows.length) return h + '<div class="banner info">No decisions yet. Run research on Floor 02 or run the pipeline on Floor 00.</div>';
  h += table(rows, ['rank','symbol','exchange','verdict','balanced','fundamental','technical','data_confidence','risk','risk_class','critical_flag'])
    + '<p class="dim small">Ranking uses the balanced score = 50% long-term (70% fundamental + 30% technical) + 50% short-term (70% technical + 30% fundamental). Critical risk stays flagged whatever the score.</p>';
  var pick = S.tab.f07pick || (rows[0].exchange+':'+rows[0].symbol);
  h += '<div class="btnrow">'+sel('f07-pick','Explain a decision', rows.map(function(x){return x.exchange+':'+x.symbol;}), pick)+'</div>';
  var x = rows.filter(function(r){ return r.exchange+':'+r.symbol===pick; })[0] || rows[0];
  h += banner('<b>'+esc(x.verdict)+'</b>: '+esc((x.reasons||[]).join(' | ')), x.verdict==='REJECT'?'crit':x.verdict==='WATCHLIST'?'warn':'sim')
    + '<details><summary>Risk Manager assessment behind this decision</summary><pre>'+esc(JSON.stringify(x.risk_assessment||{},null,2))+'</pre></details>'
    + '<div class="btnrow"><button class="btn" data-act="report_files" data-sym="'+esc(x.symbol)+'" data-ex="'+esc(x.exchange)+'">View saved reports for '+esc(x.symbol)+'</button></div>';
  if(d.reportData){
    if(d.reportData.error) h += banner(esc(d.reportData.error),'crit');
    else h += '<p class="dim small">Download buttons for these files appear below the app.</p>' + reportViewer(d.reportData.reports||[], 'f07');
  }
  return h;
}

/* ------------------------------------------------ maps + delegation + init */
var SCREENS_BY_ID = {overview:screenOverview, f00:screen00, f01:screen01, f02:screen02, f03:screen03, f04:screen04, f05:screen05, f06:screen06, f07:screen07};
var MERGE_ACTIONS = {make_report:'reportData', report_files:'reportData', run_pipeline:'pipelineResult', save_settings:'saveResult',
  backup_db:'backupResult', run_automation:'automationRan', assess:'assessResult', scan_batch:'batch'};
var POST_RENDER = {
  f02: function(d){
    if(d && d.chart && (S.tab.f02||'Chart')==='Chart'){ var cv=document.getElementById('cv-price'); if(cv) candleChart(cv, d.chart); }
  },
  f06: function(d){
    if(!d) return;
    var sm=d.summary||{}, se=sm.sector_exposure_pct||{};
    var cv=document.getElementById('cv-sector');
    if(cv) barChartCv(cv, Object.keys(se), Object.keys(se).map(function(k){return se[k];}));
    var cv2=document.getElementById('cv-equity');
    if(cv2 && d.performance) lineChartCv(cv2, d.performance.points||[]);
  }
};
var PARAMS = {
  save_settings: function(){ return {scheduler_enabled: val('set-en')==='true', schedule_time: val('set-time'), batch_size: num('set-batch'),
    time_budget_min: num('set-budget'), deep_top_n: num('set-top'), refresh_universe: val('set-ref')==='true'}; },
  watchlist_add: function(){ return {symbol: val('wl-sym'), exchange: val('wl-ex')}; },
  research: function(){ return {symbol: val('f02-sym'), exchange: val('f02-ex')}; },
  assess: function(){ return {capital: num('as-cap'), risk_pct: num('as-rp'), max_position_pct: num('as-mp'), max_sector_pct: num('as-ms')}; },
  place_order: function(){ return {symbol: val('po-sym'), exchange: val('po-ex'), side: val('po-side'), qty: num('po-qty'),
    price: num('po-px'), stop: num('po-stop'), target: num('po-tgt')}; },
  ack_alert: function(){ return {id: val('ack-pick')}; },
  add_price_rule: function(){ return {symbol: val('pr-sym'), exchange: val('pr-ex'), direction: val('pr-dir'), price: num('pr-px')}; },
  f06_refresh: function(){ return {refresh: true}; },
  report_files: function(el){ return {symbol: el.getAttribute('data-sym'), exchange: el.getAttribute('data-ex')}; }
};
var ACTION_ALIAS = {f06_refresh: 'f06'};

document.body.addEventListener('click', function(ev){
  var nav = ev.target.closest('[data-nav]');
  if(nav){ go(nav.getAttribute('data-nav')); return; }
  var t = ev.target.closest('[data-tab]');
  if(t){ S.tab[t.getAttribute('data-tabgroup')] = t.getAttribute('data-tab'); render(); return; }
  var b = ev.target.closest('[data-act]');
  if(!b || b.disabled) return;
  var act = b.getAttribute('data-act');
  if(act === 'close_report'){ if(S.data[S.screen]) S.data[S.screen].reportData = null; render(); return; }
  if(act === 'upload_csv'){
    var f = document.getElementById('up-file');
    if(!f || !f.files || !f.files[0]){
      f.insertAdjacentHTML('afterend','<div class="banner warn" style="margin-top:6px">Choose a CSV file first.</div>');
      return;
    }
    var rd = new FileReader();
    rd.onload = function(){
      var bin = rd.result, b64 = btoa(bin);
      rpc('upload_csv', {content_b64: b64, exchange: val('up-ex'), name: f.files[0].name});
    };
    rd.readAsBinaryString(f.files[0]);
    return;
  }
  var p = PARAMS[act] ? PARAMS[act](b) : {};
  rpc(ACTION_ALIAS[act] || act, p);
});
document.body.addEventListener('change', function(ev){
  if(ev.target.id === 'errs'){ rpc('f00', {errors_only: ev.target.checked}); }
  if(ev.target.id === 'f07-pick'){ S.tab.f07pick = ev.target.value; render(); }
});

/* MERGE_ACTIONS is applied inside onRender (app1.js). */

Streamlit.setComponentReady();
render();
rpc('overview');
