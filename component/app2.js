/* Screens: overview, Floor 00, Floor 01, Floor 02. */

function screenOverview(d){
  var h = '<h2>Building overview</h2><div class="sub">Each card shows the floor\'s latest logged activity. Status is read from the activity log, never assumed.</div>';
  if(!d) return h + '<p class="dim">Loading…</p>';
  h += errBox(d);
  h += '<div class="cards">' + (d.floors||[]).map(function(f){
    var cls = f.state==='ACTIVE'?'ok':(f.state==='ERROR'?'bad':'dim');
    return '<div class="card"><b style="font-size:1.4rem">'+('0'+f.index).slice(-2)+'</b> '+esc(f.name)
      + '<br><span class="'+cls+'">'+esc(f.state)+'</span>'
      + '<br><span class="dim small">'+esc((f.last_event||'no events yet').slice(0,70))+'</span>'
      + '<br><span class="dim small">errors in 24 h: '+fmt(f.errors_24h)+'</span>'
      + '<br><button class="btn" style="margin-top:6px" data-nav="f0'+f.index+'">Open floor '+('0'+f.index).slice(-2)+'</button></div>';
  }).join('') + '</div>';
  h += '<div class="section">Task connections (last 60 seconds)</div>' + buildingSVG(d.links, S.floors);
  h += '<div class="sub" style="margin-top:14px">Research assistant for NSE/BSE stocks. Outputs are research hypotheses, never advice or guaranteed returns. No broker is connected; Floor 04 is simulated.<br>'
     + (S.synthetic ? 'Data: synthetic test data generator - nothing shown is real market data.'
                    : 'Data: Yahoo Finance via yfinance (unofficial, end-of-day or delayed) and public RSS headlines (unverified).')
     + (S.isolation ? '<br>Workspace: private to this browser session and separate from other visitors; it resets when this visit ends or the app restarts.' : '')
     + '</div>';
  return h;
}

function screen00(d){
  var h = '<h2>Floor 00 · Central Command</h2>';
  if(!d) return h + '<p class="dim">Loading…</p>';
  h += errBox(d);
  var last = d.last_run;
  h += '<div class="grid g3">'
    + card('Last run', last ? '<span class="'+(last.status==='complete'?'ok':'amber')+'">'+esc(String(last.status).toUpperCase())+'</span>' : 'NEVER')
    + card('Next scheduled run', d.next_run ? esc(String(d.next_run).slice(0,16).replace('T',' ')) : 'NOT SCHEDULED')
    + card('Coverage', d.coverage ? (fmt(d.coverage.deep_complete)+' of '+fmt(d.coverage.total)) : '0 of 0') + '</div>';
  if(d.coverage) h += '<p class="dim small">'+esc(d.coverage.text)+'</p>';
  h += banner('This is scheduled batch research from end-of-day data, not continuous monitoring. The scheduler only fires while this app and the computer running it are on. A sleeping free-hosted app cannot schedule itself: unattended runs need an external runner plus a durable database. Otherwise use manual runs.','warn');
  if(d.pipelineResult){
    var pr = d.pipelineResult.pipeline || d.pipelineResult;
    h += banner('Pipeline #'+esc(pr.run_id)+' finished: '+esc(String(pr.status).toUpperCase())+'. '+esc(pr.coverage||''), pr.status==='complete'?'okbox':'warn');
    (pr.errors||[]).forEach(function(e){ h += banner(esc(e),'crit'); });
  }
  h += '<div class="btnrow"><button class="btn primary" data-act="run_pipeline">Run pipeline now</button></div>'
     + '<p class="dim small">Runs the whole daily pipeline once. Can take a long time on a large universe.</p>';
  if(last && last.summary) h += '<details><summary>Last pipeline run: step results</summary><pre>'+esc(JSON.stringify(last.summary,null,2))+'</pre></details>';

  /* automation agent */
  h += '<div class="section">Automation agent <span class="floorid">rule-based, no LLM</span></div>'
     + '<p class="dim small">Checks the data provider, runs the daily pipeline, re-runs once if it fails, checks data freshness, writes a digest and notifies you.</p>'
     + '<p class="dim small">Notification channels configured: '+(d.channels && d.channels.length ? esc(d.channels.join(', ')) : 'none. Set NTFY_TOPIC, TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID, SMTP_* or WEBHOOK_URL.')+'</p>'
     + '<div class="btnrow"><button class="btn" data-act="run_automation" title="Same steps as the scheduled run. Can take a long time.">Run automation cycle now</button>'
     + '<button class="btn" disabled title="Sending test notifications is not enabled here.">Send test notification</button></div>'
     + '<p class="dim small">Test notifications stay disabled until recipients and message wording are approved.</p>';
  var auto = d.automation;
  if(!auto) h += '<p class="dim small">The automation agent has not run yet.</p>';
  else {
    var pl = auto.payload || {};
    h += banner('Last automation cycle ('+esc(auto.when)+' UTC): '+esc(String(pl.status).toUpperCase())+'. '+esc(pl.message||''), (pl.status==='complete'||pl.status==='ok')?'okbox':'crit');
    if(pl.probe) h += '<p class="dim small">Data-provider check: '+(pl.probe.ok?'answered':'DID NOT ANSWER')+' after '+fmt(pl.probe.attempts)+' attempt(s).'+(pl.probe.last_bar?' Latest bar '+esc(pl.probe.last_bar)+'.':'')+'</p>';
    if(d.digest_text || auto.digest_text) h += '<pre>'+esc(auto.digest_text||'')+'</pre>';
    if(pl.notifications) h += '<p class="dim small">Notifications: '+pl.notifications.map(function(n){return esc(n.channel)+' '+(n.ok?'sent':'FAILED');}).join(', ')+'</p>';
  }

  /* settings */
  var stg = d.settings || {};
  h += '<details><summary>Schedule and batch settings</summary><div class="grid g3" style="margin-top:8px">'
    + '<div><label>Scheduler enabled</label><select id="set-en"><option value="true"'+(stg.scheduler_enabled==='true'?' selected':'')+'>true</option><option value="false"'+(stg.scheduler_enabled!=='true'?' selected':'')+'>false</option></select></div>'
    + inp('set-time','Run time (IST, HH:MM, Mon-Fri). Restart the app to apply.','text',stg.schedule_time)
    + inp('set-batch','Batch size (stocks per batch)','number',stg.batch_size)
    + inp('set-budget','Time budget per run (minutes)','number',stg.time_budget_min)
    + inp('set-top','Deep-research top N','number',stg.deep_top_n)
    + '<div><label>Refresh NSE universe list at each run</label><select id="set-ref"><option value="true"'+(stg.refresh_universe==='true'?' selected':'')+'>true</option><option value="false"'+(stg.refresh_universe!=='true'?' selected':'')+'>false</option></select></div>'
    + '</div><div class="btnrow"><button class="btn" data-act="save_settings">Save settings</button></div>'
    + (d.saveResult && d.saveResult.saved ? '<span class="ok small">Saved.</span>' : (d.saveResult && d.saveResult.error ? banner(esc(d.saveResult.error),'crit') : ''))
    + '</details>';

  /* queue, health */
  h += '<div class="grid g2"><div><div class="section">Task queue (retries)</div><pre>'+esc(JSON.stringify((d.queue||{}).counts||{},null,2))+'</pre>'
    + table((d.queue||{}).recent)
    + '<div class="section">Data source health</div>' + table(d.source_health)
    + '</div><div><div class="section">Database health</div>';
  var dh = d.db_health || {};
  h += '<pre>'+esc(JSON.stringify({integrity:dh.integrity, ok:dh.ok, size_mb:dh.size_mb},null,2))+'</pre>'
    + table(Object.keys(dh.tables||{}).map(function(k){ return {table:k, rows:dh.tables[k]}; }), ['table','rows'])
    + '<div class="btnrow"><button class="btn" data-act="backup_db">Back up database now</button></div>'
    + (d.backupResult && d.backupResult.backup ? '<p class="ok small">Backup written: '+esc(d.backupResult.backup)+'</p>' : '')
    + (d.backupResult && d.backupResult.error ? banner(esc(d.backupResult.error),'crit') : '')
    + '</div></div>';

  if(d.workspace_note) h += banner(esc(d.workspace_note),'warn');
  h += '<div class="section">Agent communication and activity log</div>'
    + '<label style="display:inline-flex;gap:6px;align-items:center"><input type="checkbox" id="errs" style="width:auto"> Errors only</label>'
    + table(d.activity);
  if(d.log_tail) h += '<details><summary>Application log (last lines)</summary><pre>'+esc(d.log_tail.join('\n')||'empty')+'</pre></details>';
  return h;
}

function screen01(d){
  var h = '<h2>Floor 01 · Market Scanner</h2>';
  if(!d) return h + '<p class="dim">Loading…</p>';
  h += errBox(d);
  var cnt = d.counts || {NSE:0,BSE:0,to_scan:0};
  h += '<p>Universe: <b>'+fmt(cnt.NSE)+'</b> NSE and <b>'+fmt(cnt.BSE)+'</b> BSE listings imported; <b>'+fmt(cnt.to_scan)+'</b> will be scanned (BSE duplicates of NSE ISINs skipped).</p>';
  if((cnt.NSE+cnt.BSE)===0) h += banner('The universe is empty, so no market-wide scan can run. Download the NSE list below, or upload an official NSE/BSE listing CSV. Nothing is guessed.','warn');
  if(d.message){
    var mm = d.message;
    if (mm && typeof mm === 'object' && 'rows_read' in mm)
      mm = 'Imported ' + mm.rows_read + ' rows: ' + mm.inserted + ' new, ' + mm.updated + ' updated, ' + (mm.problems||[]).length + ' problems.' + ((mm.problems||[]).length ? ' ' + mm.problems.join('; ') : '');
    h += banner(esc(typeof mm==='object' ? JSON.stringify(mm) : String(mm)),'okbox');
  }
  h += '<div class="btnrow"><button class="btn" data-act="download_nse">Download NSE equity list</button></div>'
    + '<div class="grid g3" style="align-items:end"><div><label>Or upload an official NSE/BSE listing CSV</label><input type="file" id="up-file" accept=".csv"></div>'
    + sel('up-ex','Exchange of this file',['NSE','BSE'],'NSE')
    + '<div><button class="btn" data-act="upload_csv">Import file</button></div></div>';
  h += '<div class="section">Scan cycle (resumable batches)</div>'
    + '<p>'+esc(d.coverage ? d.coverage.text : 'No scan cycle has been started.')+'</p>'
    + '<div class="btnrow"><button class="btn" data-act="scan_batch"'+(cnt.to_scan===0?' disabled':'')+'>Run one scan batch now</button></div>'
    + (d.batch ? '<pre>'+esc(JSON.stringify(d.batch.batch||d.batch,null,2))+'</pre>' : '')
    + table(d.scan_items);
  h += '<div class="section">Watchlist <span class="floorid">always deep-researched when the universe is empty</span></div>'
    + '<div class="grid g3" style="align-items:end">'+inp('wl-sym','Symbol (NSE ticker or BSE scrip code)','text','')+sel('wl-ex','Exchange',['NSE','BSE'],'NSE')
    + '<div><button class="btn" data-act="watchlist_add">Add</button></div></div>'
    + table(d.watchlist);
  return h;
}

/* ---------------------------------------------------------------- Floor 02 */
function screen02(d){
  var h = '<h2>Floor 02 · AI Analyst</h2>';
  h += '<div class="grid g3" style="align-items:end">'+inp('f02-sym','Symbol (e.g. RELIANCE, TCS; BSE scrip code like 500325)','text',d&&d.symbol||'')+sel('f02-ex','Exchange',['NSE','BSE'],(d&&d.exchange)||'NSE')
    + '<div><button class="btn primary" data-act="research">Run research</button></div></div>';
  if(!d || !d.result){
    h += errBox(d);
    if(!(d&&d.result)) h += '<div class="banner info">Enter an NSE/BSE symbol and choose Run research. Research output is a hypothesis, never advice.</div>';
    return h;
  }
  h += errBox(d);
  var r = d.result;
  (r.warnings||[]).forEach(function(w){ h += banner(esc(w), /CRITICAL|FAILED|failed/.test(w)?'crit':'warn'); });
  h += '<div class="section">Agent execution</div>'
    + table(Object.keys(r.agents||{}).map(function(n){ var a=r.agents[n];
      return {agent:n, status:String(a.status).toUpperCase(), seconds:a.duration_s, 'missing items':(a.missing||[]).length, error:a.error||''}; }));
  if(!r.scores){ h += banner('No scores were produced (see warnings). Missing data stays missing.','crit'); return h; }
  var sc=r.scores, hz=r.horizon_scores||{};
  h += '<div class="cards">'
    + card('Fundamental /100', fmt((sc.fundamental||{}).score))
    + card('Technical /100', fmt((sc.technical||{}).score))
    + card('Data confidence /100', fmt((sc.data_confidence||{}).score))
    + card('Risk /100 (higher = riskier)', fmt((sc.risk||{}).score))
    + card('Long-term', fmt(hz.long_term)) + card('Short-term', fmt(hz.short_term)) + card('Balanced', fmt(hz.balanced)) + '</div>';
  h += '<p><b>Risk class:</b> '+esc((sc.risk||{})['class']||'n/a')+' &nbsp;|&nbsp; <b>Tags:</b> '
    + ((r.tags||[]).length ? r.tags.map(function(t){ return '<span class="tag'+(/risk/i.test(t.tag)?' risk':(/multibagger|quality|Attractive|trend/i.test(t.tag)?' hi':''))+'" title="'+esc(t.reason)+'">'+esc(t.tag)+'</span>'; }).join('') : 'none') + '</p>';
  var tabs = ['Chart','Fundamental','Technical','Business','Valuation','News','Score detail','Report'];
  var cur = S.tab.f02 || 'Chart';
  h += '<div class="tabs">'+tabs.map(function(t){ return '<button data-tabgroup="f02" data-tab="'+t+'" class="'+(cur===t?'on':'')+'">'+t+'</button>'; }).join('')+'</div>';
  h += '<div id="f02-panel">'+f02Panel(cur, d)+'</div>';
  return h;
}

function f02Panel(tab, d){
  var r=d.result, ag=r.agents||{}, A={};
  Object.keys(ag).forEach(function(n){ A[n]=ag[n].data||{}; });
  var h='';
  if(tab==='Chart'){
    if(!d.chart) h += banner('Price history could not be re-fetched for the chart.','warn');
    else {
      var prov = (r.provider||{});
      h += '<canvas class="chart" id="cv-price"></canvas>'
        + '<p class="dim small">Data: '+esc(provDesc(prov))+'. Last bar '+esc(d.chart.last_bar)+'.</p>';
      var t=A.technical||{};
      if((t.levels||{}).invalidation) h += '<p class="dim small">Invalidation level '+fmt(t.levels.invalidation)+' (ATR risk distance '+fmt(t.levels.atr_risk_pct,true)+'). '+esc(t.levels.note||'')+'</p>';
    }
  } else if(tab==='Fundamental'){
    var fu=A.fundamental||{};
    h += kv(fu.metrics||{}, true) + '<p>Red flags: '+esc((fu.red_flags||[]).join('; ')||'none detected')+'</p>'
      + '<details><summary>Missing / not computable</summary><pre>'+esc(JSON.stringify((ag.fundamental||{}).missing||[],null,2))+'</pre></details>';
  } else if(tab==='Technical'){
    var t=A.technical||{};
    h += kv({'as_of (completed candles)':t.as_of, 'trend daily':(t.trend||{}).daily, 'trend weekly':(t.trend||{}).weekly, 'trend monthly':(t.trend||{}).monthly, provisional_bar:t.provisional_bar}, true)
      + '<div class="section">Daily</div>'+kv(t.daily||{}, true)
      + '<div class="section">Signals</div>'+kv(t.signals||{}, true)
      + '<div class="section">Assessments</div><pre>'+esc(JSON.stringify({short_term:t.short_term, long_term:t.long_term, levels:t.levels, limitations:t.limitations},null,2))+'</pre>';
  } else if(tab==='Business'){
    var b=A.business||{};
    h += '<p><b>'+esc(b.classification||'n/a')+'</b>. '+esc(b.basis||'')+'. '+esc(b.moat||'')+'</p>'
      + table((b.checks||[]).map(function(c){ return {check:c.check, result:c.passed===true?'pass':c.passed===false?'fail':'not evaluable', evidence:c.evidence}; }))
      + '<details><summary>Evidence not collected</summary><pre>'+esc(JSON.stringify((ag.business||{}).missing||[],null,2))+'</pre></details>';
  } else if(tab==='Valuation'){
    var v=A.valuation||{};
    h += '<p><b>'+esc(v.assessment||'n/a')+'</b>. '+esc(v.method||'')+'</p>' + kv(v.ratios||{}, true)
      + '<div class="section">Assumptions (every one shown)</div>' + table(Object.keys(v.assumptions||{}).map(function(k){ return {assumption:k, value:String(v.assumptions[k])}; }))
      + (v.scenarios ? table(Object.keys(v.scenarios).map(function(k){ return Object.assign({scenario:k}, v.scenarios[k]); }))
                     : banner('No intrinsic value computed: '+esc(v.reason||''),'warn'))
      + '<p class="dim small">Illustrative output from stated assumptions. Not a price target.</p>';
  } else if(tab==='News'){
    var nw=A.news||{};
    h += table((nw.items||[]).map(function(i){ return {headline:i.headline, source:i.source||'', published_at:String(i.published_at||'').slice(0,10), sentiment:i.sentiment, verification:i.verification_status, url:i.url||''}; }))
      + ((ag.news||{}).warnings||[]).map(function(w){ return '<p class="dim small">'+esc(w)+'</p>'; }).join('')
      + ((ag.news||{}).status==='failed' ? banner(esc((ag.news||{}).error||''),'crit') : '');
  } else if(tab==='Score detail'){
    ['fundamental','technical','data_confidence'].forEach(function(k){
      var blk=(d.result.scores||{})[k];
      if(!blk) return;
      h += '<div class="section">'+k.replace(/_/g,' ')+': '+fmt(blk.score)+'/'+fmt(blk.max)+' <span class="floorid">assessable '+fmt(blk.assessable_points)+'/100; unassessed items earn 0 points</span></div>'
        + table((blk.components||[]).reduce(function(acc,c){ (c.parts||[]).forEach(function(p){ acc.push({component:c.name, item:p.name, points:p.points===null?'unassessed':p.points, max:p.max, evidence:p.note}); }); return acc; }, []));
    });
  } else if(tab==='Report'){
    h += '<div class="btnrow"><button class="btn" data-act="make_report">Generate report files (HTML, JSON, CSV)</button></div>';
    var rd = d.reportData;
    if(rd && rd.error) h += banner(esc(rd.error),'crit');
    if(rd && rd.contents){
      h += '<p class="dim small">Generated by the app\'s own report generator. Download buttons for the files appear below the app. View here:</p>'
        + reportViewer(['html','json','csv'].filter(function(f){return rd.contents[f];}).map(function(f){ return {fmt:f, name:(rd.paths&&rd.paths[f]||'').split('/').pop(), content:rd.contents[f]}; }), 'f02');
    }
  }
  return h;
}

/* Shared in-page report viewer. items: [{fmt,name,content}] */
function reportViewer(items, group){
  if(!items.length) return '<p class="dim small">No saved report files found.</p>';
  var cur = S.tab['rv-'+group] || items[0].fmt;
  var item = items.filter(function(i){return i.fmt===cur;})[0] || items[0];
  var h = '<div class="tabs">'+items.map(function(i){ return '<button data-tabgroup="rv-'+group+'" data-tab="'+i.fmt+'" class="'+(item.fmt===i.fmt?'on':'')+'">'+i.fmt.toUpperCase()+'</button>'; }).join('')
    + '<button class="btn" style="margin-left:auto" data-act="close_report">Close</button></div>';
  if(item.fmt==='html') h += '<iframe class="report" sandbox srcdoc="'+esc(item.content)+'"></iframe>';
  else {
    var txt = item.content;
    if(item.fmt==='json'){ try{ txt = JSON.stringify(JSON.parse(item.content),null,2); }catch(e){} }
    h += '<pre style="max-height:60vh">'+esc(txt)+'</pre>';
  }
  return h;
}
