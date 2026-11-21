/* Core: RPC, rendering helpers, charts, nav. */
var S = {screen:'overview', data:{}, busy:false, nonce:0, floors:[], requested:{}, report:null, tab:{}};

var SCREENS = [
  ['overview','Building overview'],
  ['f00','Floor 00 · Central Command'],
  ['f01','Floor 01 · Market Scanner'],
  ['f02','Floor 02 · AI Analyst'],
  ['f03','Floor 03 · Risk Manager'],
  ['f04','Floor 04 · Paper Executor'],
  ['f05','Floor 05 · Monitor & Alerts'],
  ['f06','Floor 06 · Portfolio Manager'],
  ['f07','Floor 07 · Final Decision Engine']
];
var ACTION_SCREEN = {overview:'overview', f00:'f00', run_pipeline:'f00', save_settings:'f00', backup_db:'f00', run_automation:'f00',
  f01:'f01', download_nse:'f01', upload_csv:'f01', scan_batch:'f01', watchlist_add:'f01',
  research:'f02', make_report:'f02', f03:'f03', assess:'f03',
  f04:'f04', place_order:'f04', check_exits:'f04', f05:'f05', ack_alert:'f05', add_price_rule:'f05', check_price_rules:'f05',
  f06:'f06', snapshot:'f06', f07:'f07', report_files:'f07'};
var SCREEN_ACTION = {overview:'overview', f00:'f00', f01:'f01', f03:'f03', f04:'f04', f05:'f05', f06:'f06', f07:'f07'};

function esc(x){ return String(x==null?'':x).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function fmt(v, pct){
  if(v===null||v===undefined) return 'n/a';
  if(typeof v==='boolean') return String(v);
  if(typeof v==='number'){
    if(pct) return (v*100).toFixed(1)+'%';
    return Math.abs(v)>=1000 ? v.toLocaleString('en-IN',{maximumFractionDigits:2}) : (Math.round(v*100)/100).toLocaleString('en-IN');
  }
  return esc(v);
}
var PCT_HINTS=['growth','cagr','roe','roce','margin','conversion','holding','yield','pct'];
function isPct(k){ k=k.toLowerCase(); return PCT_HINTS.some(function(h){return k.indexOf(h)>=0;}); }

function rpc(action, params){
  S.nonce++;
  S.busy = true;
  document.getElementById('busy').classList.add('on');
  Streamlit.setComponentValue(Object.assign({action:action, nonce:S.nonce, vid:S.vid||null}, params||{}));
}

function kv(obj, skipLists){
  if(!obj) return '<p class="dim small">Unavailable</p>';
  var rows = Object.keys(obj).filter(function(k){ return !skipLists || (typeof obj[k]!=='object'); })
    .map(function(k){ return '<tr><td>'+esc(k)+'</td><td>'+fmt(obj[k], isPct(k))+'</td></tr>'; }).join('');
  return rows ? '<table class="t"><tbody>'+rows+'</tbody></table>' : '<p class="dim small">Nothing recorded.</p>';
}
function table(rows, cols){
  if(!rows || !rows.length) return '<p class="dim small">Nothing recorded yet.</p>';
  cols = cols || Object.keys(rows[0]);
  var head = '<tr>'+cols.map(function(c){return '<th>'+esc(c)+'</th>';}).join('')+'</tr>';
  var body = rows.map(function(r){
    return '<tr>'+cols.map(function(c){
      var v = r[c];
      if(v && typeof v==='object') v = JSON.stringify(v);
      return '<td>'+(v==null?'':esc(v))+'</td>';
    }).join('')+'</tr>';
  }).join('');
  return '<table class="t"><thead>'+head+'</thead><tbody>'+body+'</tbody></table>';
}
function banner(text, kind){ return '<div class="banner '+(kind||'warn')+'">'+text+'</div>'; }
function card(lab, val){ return '<div class="card"><div class="lab">'+esc(lab)+'</div><div class="val">'+(val==null?'n/a':val)+'</div></div>'; }
function inp(id, label, type, val, step){
  return '<div><label for="'+id+'">'+esc(label)+'</label><input id="'+id+'" type="'+(type||'text')+'" value="'+esc(val==null?'':val)+'"'+(step?' step="'+step+'"':'')+'></div>';
}
function sel(id, label, opts, val){
  return '<div><label for="'+id+'">'+esc(label)+'</label><select id="'+id+'">'+opts.map(function(o){
    return '<option value="'+esc(o)+'"'+(o===val?' selected':'')+'>'+esc(o)+'</option>';}).join('')+'</select></div>';
}
function val(id){ var el=document.getElementById(id); return el?el.value:''; }
function num(id){ var v=parseFloat(val(id)); return isNaN(v)?0:v; }
function chk(id){ var el=document.getElementById(id); return el?el.checked:false; }
function errBox(d){ return d && d.error ? banner(esc(d.error),'crit') : ''; }
function provDesc(prov){
  if(!prov) return 'unknown source';
  if(prov.is_synthetic) return 'synthetic test data (provider '+esc(prov.name||'SYNTHETIC_TEST')+') - not real market data';
  return esc(prov.name||'unknown')+' via yfinance (unofficial, end-of-day / delayed)';
}

/* ------------------------------------------------ charts */
function setupCanvas(cv, h){
  var dpr = window.devicePixelRatio||1, w = cv.clientWidth||600;
  cv.width = w*dpr; cv.height = h*dpr; cv.style.height = h+'px';
  var ctx = cv.getContext('2d'); ctx.scale(dpr,dpr);
  return [ctx, w, h];
}
function candleChart(cv, d){
  var ctx,w,h; try{ [ctx,w,h]=setupCanvas(cv,380); }catch(e){ return; }
  var n=d.dates.length; if(!n) return;
  var padL=8,padR=56,padT=10,padB=22, iw=w-padL-padR, ih=h-padT-padB;
  var lo=Infinity, hi=-Infinity, i,j;
  for(i=0;i<n;i++){ lo=Math.min(lo,d.l[i]); hi=Math.max(hi,d.h[i]); }
  [20,50,200].forEach(function(k){ var e=d.ema[String(k)]; for(j=0;j<n;j++){ if(e[j]!=null){ lo=Math.min(lo,e[j]); hi=Math.max(hi,e[j]); } } });
  var rng=(hi-lo)||1; lo-=rng*0.04; hi+=rng*0.04; rng=hi-lo;
  function X(i){ return padL + (i+0.5)*iw/n; }
  function Y(v){ return padT + (hi-v)/rng*ih; }
  ctx.strokeStyle='#1d2d50'; ctx.fillStyle='#8fa3c7'; ctx.font='11px system-ui'; ctx.textAlign='left';
  for(i=0;i<=4;i++){ var p=hi-rng*i/4, y=Y(p);
    ctx.beginPath(); ctx.moveTo(padL,y); ctx.lineTo(w-padR,y); ctx.stroke();
    ctx.fillText(p.toLocaleString('en-IN',{maximumFractionDigits:0}), w-padR+6, y+4); }
  ctx.textAlign='center';
  for(i=0;i<6;i++){ var di=Math.floor(i*(n-1)/5); ctx.fillText(d.dates[di].slice(2), X(di), h-6); }
  var bw=Math.max(1.5, iw/n*0.62);
  for(i=0;i<n;i++){
    var up=d.c[i]>=d.o[i], col=up?'#2dd4a0':'#ff6b6b';
    ctx.strokeStyle=col; ctx.fillStyle=col;
    ctx.beginPath(); ctx.moveTo(X(i),Y(d.h[i])); ctx.lineTo(X(i),Y(d.l[i])); ctx.stroke();
    var y1=Y(Math.max(d.o[i],d.c[i])), y2=Y(Math.min(d.o[i],d.c[i]));
    ctx.fillRect(X(i)-bw/2, y1, bw, Math.max(1,y2-y1));
  }
  [['20','#f5c542'],['50','#6ea8ff'],['200','#c792ea']].forEach(function(pair){
    var e=d.ema[pair[0]]; ctx.strokeStyle=pair[1]; ctx.lineWidth=1.2; ctx.beginPath(); var started=false;
    for(var i=0;i<n;i++){ if(e[i]==null) continue; var x=X(i),y=Y(e[i]);
      if(!started){ ctx.moveTo(x,y); started=true; } else ctx.lineTo(x,y); }
    ctx.stroke(); ctx.lineWidth=1;
    ctx.fillStyle=pair[1]; ctx.textAlign='left'; ctx.fillText('EMA'+pair[0], padL+6+(''+pair[0]).length*0+ (pair[0]==='20'?0:pair[0]==='50'?52:104), padT+12);
  });
}
function barChartCv(cv, labels, values){
  var ctx,w,h; try{ [ctx,w,h]=setupCanvas(cv,260); }catch(e){ return; }
  if(!labels.length) return;
  var max=Math.max.apply(null,values)||1, padL=8,padR=8,padT=16,padB=40, iw=w-padL-padR, ih=h-padT-padB;
  var bw=iw/labels.length;
  ctx.font='11px system-ui'; ctx.textAlign='center';
  labels.forEach(function(l,i){
    var v=values[i], bh=v/max*ih, x=padL+i*bw;
    ctx.fillStyle='#6ea8ff'; ctx.fillRect(x+bw*0.15, padT+ih-bh, bw*0.7, bh);
    ctx.fillStyle='#dbe4f3'; ctx.fillText(v.toFixed(1)+'%', x+bw/2, padT+ih-bh-4);
    ctx.fillStyle='#8fa3c7';
    var lab=l.length>12?l.slice(0,11)+'…':l;
    ctx.save(); ctx.translate(x+bw/2, padT+ih+6); ctx.rotate(labels.length>6?0.5:0); ctx.fillText(lab, 0, 10); ctx.restore();
  });
}
function lineChartCv(cv, points){
  var ctx,w,h; try{ [ctx,w,h]=setupCanvas(cv,260); }catch(e){ return; }
  if(points.length<2) return;
  var padL=8,padR=64,padT=12,padB=22, iw=w-padL-padR, ih=h-padT-padB;
  var lo=Infinity,hi=-Infinity;
  points.forEach(function(p){ lo=Math.min(lo,p[1]); hi=Math.max(hi,p[1]); });
  var rng=(hi-lo)||1;
  function X(i){ return padL+i*iw/(points.length-1); }
  function Y(v){ return padT+(hi-v)/rng*ih; }
  ctx.strokeStyle='#1d2d50'; ctx.fillStyle='#8fa3c7'; ctx.font='11px system-ui'; ctx.textAlign='left';
  for(var i=0;i<=3;i++){ var p=hi-rng*i/3, y=Y(p);
    ctx.beginPath(); ctx.moveTo(padL,y); ctx.lineTo(w-padR,y); ctx.stroke();
    ctx.fillText(p.toLocaleString('en-IN',{maximumFractionDigits:0}), w-padR+6, y+4); }
  ctx.strokeStyle='#2dd4a0'; ctx.lineWidth=1.6; ctx.beginPath();
  points.forEach(function(p,i){ if(i) ctx.lineTo(X(i),Y(p[1])); else ctx.moveTo(X(0),Y(p[1])); });
  ctx.stroke(); ctx.lineWidth=1;
  ctx.fillStyle='#8fa3c7'; ctx.textAlign='center';
  ctx.fillText(String(points[0][0]).slice(0,10), X(0)+30, h-6);
  ctx.fillText(String(points[points.length-1][0]).slice(0,10), X(points.length-1)-30, h-6);
}

/* ------------------------------------------------ building SVG */
function buildingSVG(active, names){
  var ROW=46, h=ROW*8+10, rows='', links='';
  for(var i=0;i<8;i++){
    rows += '<rect x="10" y="'+(i*ROW+6)+'" width="250" height="36" rx="6" fill="#101e36" stroke="#22365a"/>'
      + '<text x="24" y="'+(i*ROW+29)+'" fill="#e6edf7" font-size="14" font-family="Segoe UI,sans-serif">'+('0'+i).slice(-2)+' · '+esc(names[i]||'')+'</text>';
  }
  (active||[]).forEach(function(pr){
    var a=pr[0], b=pr[1], ya=a*ROW+24, yb=b*ROW+24, bend=60+Math.abs(a-b)*18;
    links += '<path d="M260 '+ya+' C '+(260+bend)+' '+ya+', '+(260+bend)+' '+yb+', 260 '+yb+'" fill="none" stroke="#2dd4a0" stroke-width="2.5" stroke-dasharray="6 6">'
      + '<animate attributeName="stroke-dashoffset" from="24" to="0" dur="0.9s" repeatCount="indefinite"/></path>';
  });
  var label = (active&&active.length)?'':'<text x="290" y="30" fill="#8fa3c7" font-size="13" font-family="Segoe UI,sans-serif">No task is running: connections idle</text>';
  return '<svg viewBox="0 0 640 '+h+'" width="100%" style="max-width:640px" xmlns="http://www.w3.org/2000/svg">'+rows+links+label+'</svg>';
}

/* ------------------------------------------------ nav + render loop */
function go(screen){
  S.screen = screen; S.report = null; S.tab = {};
  if(SCREEN_ACTION[screen] && !S.data[screen] && !S.busy) rpc(SCREEN_ACTION[screen]);
  render();
}
function renderNav(){
  var rail=document.getElementById('rail'), mnav=document.getElementById('mnav');
  rail.innerHTML = SCREENS.map(function(s){
    return '<button class="'+(S.screen===s[0]?'on':'')+'" data-s="'+s[0]+'">'+esc(s[1])+'</button>'; }).join('');
  rail.querySelectorAll('button').forEach(function(b){ b.onclick=function(){ go(b.getAttribute('data-s')); }; });
  mnav.innerHTML = SCREENS.map(function(s){
    return '<option value="'+s[0]+'"'+(S.screen===s[0]?' selected':'')+'>'+esc(s[1])+'</option>'; }).join('');
  mnav.onchange=function(){ go(mnav.value); };
}
function render(){
  renderNav();
  var fn = SCREENS_BY_ID[S.screen] || screenOverview;
  document.getElementById('main').innerHTML = fn(S.data[S.screen]);
  var post = POST_RENDER[S.screen];
  if(post) post(S.data[S.screen]);
  Streamlit.setFrameHeight(document.body.scrollHeight+24);
}
function onRender(ev){
  var args = ev.detail.args || {};
  if(args.boot){ S.floors = args.boot.floors||[]; S.synthetic = !!args.boot.synthetic; S.vid = args.boot.vid||null; S.isolation = !!args.boot.isolation; }
  if(args.result && args.result.data){
    var act = args.result.action, scr = ACTION_SCREEN[act] || S.screen, key = MERGE_ACTIONS[act];
    if(key && S.data[scr]) S.data[scr][key] = args.result.data;
    else S.data[scr] = args.result.data;
    S.busy = false;
    document.getElementById('busy').classList.remove('on');
  }
  render();
}
Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
