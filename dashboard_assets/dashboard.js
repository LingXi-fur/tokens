const WIRE = __DATA__;
function decodeWire(wire){
  if(!wire||wire.v!==1)throw new Error('Unsupported dashboard data version');
  const table=wire.s||[],mark='§';
  const decode=value=>{
    if(typeof value==='string'){
      if(!value.startsWith(mark))return value;
      if(value.startsWith(mark+mark))return value.slice(1);
      return table[parseInt(value.slice(1),36)];
    }
    if(Array.isArray(value))return value.map(decode);
    if(value&&typeof value==='object'){const out={};Object.entries(value).forEach(([key,item])=>out[decode(key)]=decode(item));return out;}
    return value;
  };
  return decode(wire.d);
}
const DATA = decodeWire(WIRE);
const state = { gran: 'month', models: new Set(DATA.models), focusPeriod:null, compare:false, numberMode:0 };
let lastTotal = 0;
let stateRevision=0,derivedRevision=-1,derivedCache={};
function invalidateDerived(){stateRevision++;derivedCache={};derivedRevision=stateRevision;}
function memoDerived(key,build){if(derivedRevision!==stateRevision){derivedCache={};derivedRevision=stateRevision;}if(!Object.prototype.hasOwnProperty.call(derivedCache,key))derivedCache[key]=build();return derivedCache[key];}
function stateKey(){return state.gran+'|'+[...state.models].sort().join(',')+'|'+(state.focusPeriod||'');}
const LABEL = {day:'日期', week:'周(始)', month:'月份'};

const fmt = n => Number(n||0).toLocaleString('en-US');
function human(n){ if(n>=1e8) return (n/1e8).toFixed(1)+'亿'; if(n>=1e4) return (n/1e4).toFixed(1)+'万'; return String(Math.round(n)); }
function metric(n){ if(n>=1e9)return (n/1e9).toFixed(2)+'B'; if(n>=1e6)return (n/1e6).toFixed(2)+'M'; if(n>=1e3)return (n/1e3).toFixed(1)+'K'; return String(Math.round(n)); }
function displayNumber(n){ return state.numberMode===1?human(n):state.numberMode===2?metric(n):fmt(n); }
const pretty = m => DATA.pretty[m] || m;
const pct = (a,b) => b? ((a/b*100).toFixed(1)+'%') : '0%';
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function periodDays(period, gran){
  if(gran==='day') return [period];
  const start=new Date(period+'T00:00:00'), out=[];
  if(Number.isNaN(start.getTime())) return out;
  if(gran==='week'){ for(let i=0;i<7;i++){const d=new Date(start);d.setDate(start.getDate()+i);out.push(localISO(d));} }
  else { const y=start.getFullYear(),m=start.getMonth(); for(let d=1;d<=new Date(y,m+1,0).getDate();d++) out.push(localISO(new Date(y,m,d))); }
  return out;
}
function localISO(d){ return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'); }
function focusDays(){ return state.focusPeriod?new Set(periodDays(state.focusPeriod,state.gran)):null; }
function filteredHourly(){
  const fd=focusDays(), out=Array(24).fill(0);
  Object.entries(DATA.day_details||{}).forEach(([day,det])=>{
    if(fd&&!fd.has(day))return;
    Object.entries(det.hourly_models||{}).forEach(([m,h])=>{if(state.models.has(m))h.forEach((v,i)=>out[i]+=v||0);});
  });
  return out;
}
function focusDetail(){
  const fd=focusDays(); if(!fd)return null;
  const d={cache_read:0,top_cwds:{},top_sessions:{}};
  fd.forEach(day=>{const x=DATA.day_details[day];if(!x)return;Object.entries(x.cache_read_models||{}).forEach(([m,v])=>{if(state.models.has(m))d.cache_read+=v||0;});(x.cwds||x.top_cwds||[]).forEach(it=>{const k=it[2]||it[0],cur=d.top_cwds[k]||[it[0],0,it[2],{}];Object.entries(it[3]||{}).forEach(([m,v])=>{if(state.models.has(m)){cur[3][m]=(cur[3][m]||0)+v;cur[1]+=v;}});d.top_cwds[k]=cur;});(x.sessions||x.top_sessions||[]).forEach(it=>{const k=it[2]||it[0],cur=d.top_sessions[k]||[it[0],0,it[2],{}];Object.entries(it[3]||{}).forEach(([m,v])=>{if(state.models.has(m)){cur[3][m]=(cur[3][m]||0)+v;cur[1]+=v;}});d.top_sessions[k]=cur;});});
  d.top_cwds=Object.values(d.top_cwds).filter(x=>x[1]>0).sort((a,b)=>b[1]-a[1]).slice(0,6);d.top_sessions=Object.values(d.top_sessions).filter(x=>x[1]>0).sort((a,b)=>b[1]-a[1]).slice(0,6);return d;
}

function spanYears(gran){ const ys=[...new Set(DATA[gran].map(r=>(r.period||'').slice(0,4)))]; return ys.length>1; }
function fmtLabel(period, gran){
  const p=(period||'').split('-');
  if(gran==='month') return p[0]+'-'+(p[1]||'');
  if(gran==='day'||gran==='week'){ return spanYears(gran)?period:(p[1]||'')+'-'+(p[2]||''); }
  return period;
}
function selectedCacheRead(){
  const fd=focusDays();let total=0;
  Object.entries(DATA.day_details||{}).forEach(([day,detail])=>{if(fd&&!fd.has(day))return;Object.entries(detail.cache_read_models||{}).forEach(([m,v])=>{if(state.models.has(m))total+=v||0;});});
  return total;
}

function selectedRows(all=false){
  const key='rows|'+stateKey()+'|'+(all?'all':'focus');
  return memoDerived(key,()=>{
    let src=DATA[state.gran];
    if(state.focusPeriod&&!all) src=src.filter(r=>r.period===state.focusPeriod);
    return src.map(r=>{
      const models={}; let total=0,calls=0;
      state.models.forEach(m=>{ const v=r.models[m]||0; if(v){models[m]=v;total+=v;}calls+=(r.model_calls||{})[m]||0; });
      return {period:r.period, calls, models, total};
    });
  });
}

function motionDisabled(){return document.documentElement.dataset.motion==='off'||window.matchMedia('(prefers-reduced-motion: reduce)').matches;}
function scrollBehavior(){return motionDisabled()?'auto':'smooth';}
/* count-up 数字动画 */
function animateNum(el, to, dur, formatter=fmt){
  if(!el) return;
  if(motionDisabled()){ el.textContent=formatter(to); return; }
  const start=performance.now();
  function tick(t){if(motionDisabled()){el.textContent=formatter(to);return;} const k=Math.min(1,(t-start)/dur), e=1-Math.pow(1-k,3);
    el.textContent=formatter(Math.round(to*e)); if(k<1) requestAnimationFrame(tick); }
  requestAnimationFrame(tick);
}

function forecastForLatestMonth(rows){
  if(state.gran!=='month'||state.focusPeriod||!rows.length)return null;
  const last=rows[rows.length-1],generated=String(DATA.generated||'').slice(0,10),month=generated.slice(0,7);
  if(!generated||last.period!==month)return null;
  const until=DATA.range?.until;if(until&&until<generated)return null;
  const coveredDay=Number(generated.slice(8,10)),[yy,mm]=last.period.split('-').map(Number),dim=new Date(yy,mm,0).getDate(),day=Math.max(1,Math.min(dim,coveredDay||1));
  if(day>=dim)return null;
  return {total:Math.round(last.total/day*dim),progress:Math.round(day/dim*100)};
}

function renderKPI(){
  const rows=selectedRows();
  const total=rows.reduce((a,r)=>a+r.total,0); lastTotal=total;
  const calls=rows.reduce((a,r)=>a+r.calls,0);
  const mtot={};
  rows.forEach(r=>Object.entries(r.models).forEach(([m,v])=>mtot[m]=(mtot[m]||0)+v));
  let dom='—', domv=-1;
  Object.entries(mtot).forEach(([m,v])=>{ if(v>domv){domv=v;dom=m;} });
  animateNum(document.getElementById('k-total'), total, 600, displayNumber);
  document.getElementById('k-total-u').textContent = human(total)+' tk';
  animateNum(document.getElementById('k-calls'), calls, 500);
  animateNum(document.getElementById('k-models'), Object.keys(mtot).length, 400);
  document.getElementById('k-dom').textContent = dom!=='—' ? pretty(dom) : '—';
  // 环比 Δ：最末一期 vs 上一期（多 token 不代表好坏，故中性配色，非红绿）
  const dEl=document.getElementById('k-delta');
  if(rows.length>=2 && rows[rows.length-2].total>0){
    const last=rows[rows.length-1].total, prev=rows[rows.length-2].total, d=(last-prev)/prev*100;
    dEl.style.display=''; dEl.className='delta '+(d>=0?'up':'down');
    dEl.textContent=(d>=0?'▲ ':'▼ ')+Math.abs(d).toFixed(1)+'% 环比';
  } else dEl.style.display='none';
  // 缓存命中：cache_read 占比；省下 = cache_read（无需重算的 token）
  const detail=focusDetail();
  const cr=detail?detail.cache_read:selectedCacheRead(), hit=total?(cr/total*100):0;
  animateNum(document.getElementById('k-cache-pct'), Math.round(hit), 500);
  document.getElementById('k-saved').textContent = human(cr)+' tk';
  setTimeout(()=>{ document.getElementById('gauge-fill').style.width=Math.min(100,hit).toFixed(1)+'%'; }, 60);
  // 本月预测：按已过天数速率推算月末
  const fEl=document.getElementById('k-forecast'),forecast=forecastForLatestMonth(rows);
  if(forecast){fEl.style.display='';fEl.textContent='预计月末 '+human(forecast.total)+' tk · '+forecast.progress+'%进度';}
  else fEl.style.display='none';
  renderSpark(rows);
}

/* 总量 KPI 里的迷你折线（最近若干期） */
function renderSpark(rows){
  const svg=document.getElementById('spark');
  const vals=rows.slice(-16).map(r=>r.total);
  if(vals.length<2){ svg.innerHTML=''; return; }
  const W=96,H=30,max=Math.max(...vals),min=Math.min(...vals),sp=(max-min)||1;
  const pts=vals.map((v,i)=>[ (i/(vals.length-1))*W, H-3-((v-min)/sp)*(H-6) ]);
  const line='M'+pts.map(p=>p[0].toFixed(1)+' '+p[1].toFixed(1)).join('L');
  const area=line+` L ${W} ${H} L 0 ${H} Z`;
  const last=pts[pts.length-1];
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  svg.innerHTML=`<path d="${area}" fill="var(--accent-soft)"/><path d="${line}" fill="none" stroke="var(--accent-2)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/><circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2" fill="var(--accent)"/>`;
}

let barCursor=0;
function describeBar(el,focus=true){
  const rows=selectedRows(true),i=Number(el.dataset.index||0),r=rows[i];if(!r)return;
  barCursor=i;document.querySelectorAll('#bar .barstack').forEach((x,j)=>x.setAttribute('tabindex',j===i?'0':'-1'));
  const dom=Object.entries(r.models||{}).sort((a,b)=>b[1]-a[1])[0],hint=fmtLabel(r.period,state.gran)+' · '+fmt(r.total)+' Token'+(dom?' · 主力 '+pretty(dom[0])+' '+pct(dom[1],r.total):'')+' · Enter 回看';
  document.getElementById('bar-hint').textContent=hint;if(focus)el.focus();
}
function renderBar(){
  const rows=selectedRows(true);
  const W=1040,H=340,padL=56,padR=18,padT=18;
  const plotW=W-padL-padR;
  const n=Math.max(1,rows.length), step=plotW/n;
  // 每根柱都标日期：少→横排，中→斜排(-45)，密→竖排(-90)，永不抽稀、不重叠
  const ang = n<=10 ? 0 : step>=26 ? -45 : -90;
  const padB = ang===0 ? 40 : ang===-90 ? 48 : 56;
  const plotH=H-padT-padB;
  const compared=state.compare?rows.map((r,i)=>i?rows[i-1].total:0):[];
  const vmax=Math.max(1, ...rows.map(r=>r.total), ...compared);
  // 整图锁定单一单位，避免 y 轴/标签 万与亿混用造成「629→7.5」歧义
  const U = vmax>=1e8?['亿',1e8]:vmax>=1e4?['万',1e4]:['',1];
  const vfmt = nn => { const v=nn/U[1]; return U[0] ? (v<10?v.toFixed(1):String(Math.round(v)))+U[0] : String(Math.round(nn)); };
  const bw=Math.max(3,Math.min(54,step*0.6));
  const showVal = n<=12;
  const p=['<svg viewBox="0 0 '+W+' '+H+'" class="chart" preserveAspectRatio="xMidYMid meet">'];
  for(let i=0;i<=4;i++){
    const frac=i/4, y=padT+plotH*(1-frac), val=Math.round(vmax*frac);
    p.push('<line class="grid-l" x1="'+padL+'" y1="'+y.toFixed(1)+'" x2="'+(W-padR)+'" y2="'+y.toFixed(1)+'"/>');
    if(i>0) p.push('<text x="'+(padL-8)+'" y="'+(y+3.5).toFixed(1)+'" text-anchor="end" class="tick">'+vfmt(val)+'</text>');
  }
  p.push('<line class="axis" x1="'+padL+'" y1="'+(padT+plotH).toFixed(1)+'" x2="'+(W-padR)+'" y2="'+(padT+plotH).toFixed(1)+'"/>');
  if(rows.length===0){ p.push('<text x="'+(W/2)+'" y="'+(H/2)+'" text-anchor="middle" class="tick">无数据</text></svg>'); document.getElementById('bar').innerHTML=p.join(''); return; }
  const _vals=rows.map(r=>r.total);
  const mean=_vals.reduce((a,b)=>a+b,0)/_vals.length;
  let peakI=0; for(let i=1;i<rows.length;i++){ if(rows[i].total>rows[peakI].total) peakI=i; }
  rows.forEach((r,i)=>{
    const x=padL+step*i+(step-bw)/2;
    p.push('<rect class="bar-track" x="'+x.toFixed(1)+'" y="'+padT.toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+plotH.toFixed(1)+'" rx="4"/>');
    if(state.compare&&i>0){
      const pv=rows[i-1].total, gh=(pv/vmax)*plotH, gy=padT+plotH-gh;
      p.push('<rect class="ghostbar" x="'+(x-3).toFixed(1)+'" y="'+gy.toFixed(1)+'" width="'+(bw+6).toFixed(1)+'" height="'+gh.toFixed(1)+'" rx="5"><title>上一期 '+esc(rows[i-1].period)+' · '+fmt(pv)+' tk</title></rect>');
    }
    let segs=''; let y0=padT+plotH;
    state.models.forEach(m=>{ const v=r.models[m]||0; if(v<=0) return;
      const h=(v/vmax)*plotH, y=y0-h;
      segs+='<rect class="seg model-mark" data-model="'+esc(m)+'" x="'+x.toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+h.toFixed(1)+'" rx="2" fill="'+DATA.colors[m]+'"><title>'+esc(r.period)+' · '+esc(pretty(m))+': '+fmt(v)+' ('+pct(v,r.total)+')</title></rect>';
      y0-=h;
    });
    const isPeak = rows.length>1 && i===peakI;
    const isFocus=state.focusPeriod===r.period;
    const aria=fmtLabel(r.period,state.gran)+'，'+fmt(r.total)+' Token'+(isPeak?'，峰值':'')+(isFocus?'，当前时光探针':'')+'，按 Enter 回看';
    p.push('<g class="barstack'+(isPeak?' peak':'')+(isFocus?' focused':'')+(state.focusPeriod&&!isFocus?' muted':'')+'" data-period="'+esc(r.period)+'" data-index="'+i+'" tabindex="'+(i===Math.min(barCursor,rows.length-1)?'0':'-1')+'" role="button" aria-label="'+esc(aria)+'"><rect class="bar-focus" x="'+(padL+step*i+2).toFixed(1)+'" y="'+(padT+1).toFixed(1)+'" width="'+Math.max(1,step-4).toFixed(1)+'" height="'+(plotH+padB-2).toFixed(1)+'" rx="6"/>'+segs+'</g>');
    if(isPeak&&!state.focusPeriod){
      p.push('<text class="peak-flag" x="'+(x+bw/2).toFixed(1)+'" y="'+(padT+plotH-r.total/vmax*plotH-7).toFixed(1)+'" text-anchor="middle">▲峰值 '+vfmt(r.total)+'</text>');
    } else if(showVal){
      p.push('<text class="vlabel" x="'+(x+bw/2).toFixed(1)+'" y="'+(padT+plotH-r.total/vmax*plotH-6).toFixed(1)+'" text-anchor="middle">'+vfmt(r.total)+'</text>');
    }
    if(state.compare&&i>0&&rows[i-1].total>0&&n<=18){
      const d=(r.total-rows[i-1].total)/rows[i-1].total*100;
      p.push('<text class="delta-tag" x="'+(x+bw/2).toFixed(1)+'" y="'+Math.max(11,padT+plotH-Math.max(r.total,rows[i-1].total)/vmax*plotH-18).toFixed(1)+'" text-anchor="middle">'+(d>=0?'+':'')+d.toFixed(0)+'%</text>');
    }
    const lx=padL+step*i+step/2;
    let ly, anchor, tr;
    if(ang===0){ ly=H-padB+18; anchor='middle'; tr=''; }
    else if(ang===-45){ ly=H-padB+30; anchor='end'; tr='transform="rotate(-45 '+lx.toFixed(1)+' '+ly.toFixed(1)+')"'; }
    else { ly=H-8; anchor='start'; tr='transform="rotate(-90 '+lx.toFixed(1)+' '+ly.toFixed(1)+')"'; }
    p.push('<text x="'+lx.toFixed(1)+'" y="'+ly.toFixed(1)+'" text-anchor="'+anchor+'" class="xlabel" '+tr+'>'+esc(fmtLabel(r.period,state.gran))+'</text>');
    p.push('<rect class="bar-hit" data-period="'+esc(r.period)+'" x="'+(padL+step*i).toFixed(1)+'" y="'+padT+'" width="'+step.toFixed(1)+'" height="'+(plotH+padB).toFixed(1)+'"><title>点击回看 '+esc(r.period)+'</title></rect>');
  });
  if(rows.length>1 && mean>0){
    const my=padT+plotH-(mean/vmax)*plotH;
    p.push('<line class="mean-line" x1="'+padL+'" y1="'+my.toFixed(1)+'" x2="'+(W-padR)+'" y2="'+my.toFixed(1)+'"/>');
    p.push('<text class="mean-lab" x="'+(W-padR-2)+'" y="'+(my-4).toFixed(1)+'" text-anchor="end">μ '+vfmt(mean)+'</text>');
  }
  p.push('</svg>');
  const box=document.getElementById('bar'); box.innerHTML=p.join('');
  const stacks=[...box.querySelectorAll('.barstack')];
  stacks.forEach(el=>{
    el.addEventListener('click',()=>toggleFocus(el.dataset.period));
    el.addEventListener('focus',()=>describeBar(el,false));
    el.addEventListener('keydown',e=>{const i=Number(el.dataset.index||0);if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();const next=Math.max(0,Math.min(stacks.length-1,i+(e.key==='ArrowRight'?1:-1)));describeBar(stacks[next]);}else if(e.key==='Home'||e.key==='End'){e.preventDefault();describeBar(stacks[e.key==='Home'?0:stacks.length-1]);}else if(e.key==='Enter'||e.key===' '){e.preventDefault();toggleFocus(el.dataset.period,true);}});
  });
  box.querySelectorAll('.bar-hit').forEach(el=>el.addEventListener('click',()=>toggleFocus(el.dataset.period)));
  box.querySelectorAll('.model-mark').forEach(el=>{el.addEventListener('mouseenter',e=>{modelHover(el.dataset.model,true);e.stopPropagation();});el.addEventListener('mouseleave',e=>{modelHover(el.dataset.model,false);e.stopPropagation();});});
}

function renderDonut(){
  const rows=selectedRows();
  const mtot={};
  rows.forEach(r=>Object.entries(r.models).forEach(([m,v])=>mtot[m]=(mtot[m]||0)+v));
  const entries=Object.entries(mtot).sort((a,b)=>b[1]-a[1]);
  const total=entries.reduce((a,[,v])=>a+v,0);
  const box=document.getElementById('donut');
  if(total===0){ box.innerHTML='<div class="hint">所选区间无数据</div>'; document.getElementById('donut-legend').innerHTML=''; return; }
  const size=220, cx=size/2, cy=size/2, r=size/2-8;
  let angle=-Math.PI/2; const p=['<svg viewBox="0 0 '+size+' '+size+'" class="pie">'];
  entries.forEach(([m,v])=>{
    const frac=v/total, a0=angle, a1=angle+frac*2*Math.PI;
    if(frac>=0.999){
      p.push('<circle class="slice model-mark" data-model="'+esc(m)+'" cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="'+DATA.colors[m]+'"><title>'+esc(pretty(m))+' '+pct(v,total)+'</title></circle>');
    }else{
      const large=frac>0.5?1:0;
      const x0=cx+r*Math.cos(a0), y0=cy+r*Math.sin(a0), x1=cx+r*Math.cos(a1), y1=cy+r*Math.sin(a1);
      p.push('<path class="slice model-mark" data-model="'+esc(m)+'" d="M '+cx+' '+cy+' L '+x0.toFixed(2)+' '+y0.toFixed(2)+' A '+r+' '+r+' 0 '+large+' 1 '+x1.toFixed(2)+' '+y1.toFixed(2)+' Z" fill="'+DATA.colors[m]+'"><title>'+esc(pretty(m))+' '+pct(v,total)+'</title></path>');
    }
    angle=a1;
  });
  p.push('<circle class="pie-hole" cx="'+cx+'" cy="'+cy+'" r="'+(r*0.58).toFixed(1)+'"/>');
  p.push('<text x="'+cx+'" y="'+(cy-2)+'" text-anchor="middle" class="pie-center">'+human(total)+'</text>');
  p.push('<text x="'+cx+'" y="'+(cy+14)+'" text-anchor="middle" class="pie-sub">TOKENS</text></svg>');
  box.innerHTML=p.join('');
  document.getElementById('donut-legend').innerHTML=entries.map(([m,v])=>
    '<li class="model-mark" data-model="'+esc(m)+'"><span class="ldot" style="background:'+DATA.colors[m]+'"></span>'+esc(pretty(m))+' <em>'+pct(v,total)+'</em></li>').join('');
}

function renderTable(){
  const rows=selectedRows();
  const cols=DATA.models.filter(m=>state.models.has(m));
  const th=cols.map(m=>'<th class=num>'+esc(pretty(m))+'</th>').join('');
  const body=rows.map(r=>{
    const tds=cols.map(m=> r.models[m]?'<td class=num>'+fmt(r.models[m])+'</td>':'<td class=num><span class=dim>·</span></td>').join('');
    return '<tr><td>'+esc(fmtLabel(r.period,state.gran))+'</td><td class=num>'+fmt(r.total)+'</td>'+tds+'<td class=num>'+fmt(r.calls)+'</td></tr>';
  }).join('');
  document.getElementById('thead').innerHTML='<tr><th>'+LABEL[state.gran]+'</th><th class=num>总 token</th>'+th+'<th class=num>调用</th></tr>';
  document.getElementById('tbody').innerHTML=body || '<tr><td colspan="' +(cols.length+3)+ '" class="hint">无数据</td></tr>';
}

let previousModels=null;
function setModels(next,label){previousModels=new Set(state.models);state.models=new Set(next);invalidateDerived();renderFilters();renderDataViews();if(label)toast(label);}
function renderFilterLedger(){
  const rows=DATA[state.gran]||[],all=rows.reduce((a,r)=>a+(r.total||0),0),selected=rows.reduce((a,r)=>a+Object.entries(r.models||{}).reduce((s,[m,v])=>s+(state.models.has(m)?v:0),0),0);
  document.getElementById('filter-summary').innerHTML='已选 <b>'+state.models.size+'/'+DATA.models.length+'</b> 个模型 · 覆盖 <b>'+pct(selected,all)+'</b> Token';document.getElementById('filter-undo').disabled=!previousModels;
}
function renderFilters(){
  const box=document.getElementById('filters');
  if(DATA.models.length===0){ box.innerHTML='<span class=hint>无模型数据</span>'; return; }
  box.innerHTML=DATA.models.map(m=>{
    const on=state.models.has(m);
    return '<label class="chip'+(on?'':' off')+'"><input type=checkbox value="'+esc(m)+'" '+(on?'checked':'')+'><span class=cdot style="background:'+DATA.colors[m]+'"></span>'+esc(pretty(m))+'</label>';
  }).join('');
  box.querySelectorAll('input').forEach(cb=>{
    cb.addEventListener('change',e=>{const next=new Set(state.models);e.target.checked?next.add(e.target.value):next.delete(e.target.value);setModels(next);});
    const chip=cb.closest('.chip');
    chip.title='点击切换 · 双击独看 · Alt 点击全选/清空 · 右键反选';
    chip.addEventListener('dblclick',e=>{e.preventDefault();setModels([cb.value],'Solo · '+pretty(cb.value));});
    chip.addEventListener('click',e=>{if(!e.altKey)return;e.preventDefault();setModels(state.models.size===DATA.models.length?[]:DATA.models);});
    chip.addEventListener('contextmenu',e=>{e.preventDefault();const next=new Set(state.models);next.has(cb.value)?next.delete(cb.value):next.add(cb.value);setModels(next);});
  });
  renderFilterLedger();
}
document.getElementById('filter-all').addEventListener('click',()=>setModels(DATA.models,'已选择全部模型'));
document.getElementById('filter-none').addEventListener('click',()=>setModels([],'已清空模型筛选'));
document.getElementById('filter-undo').addEventListener('click',()=>{if(!previousModels)return;state.models=new Set(previousModels);previousModels=null;invalidateDerived();renderFilters();renderDataViews();toast('已撤销上一次模型筛选');});

function lbRows(items,sessionRows=false){
  if(!items || !items.length) return '<div class="hint">无数据</div>';
  const filtered=items.map(it=>{const models=it[3]||{},parts=Object.entries(models).filter(([m])=>state.models.has(m)).sort((a,b)=>b[1]-a[1]),total=parts.reduce((a,[,v])=>a+v,0);return {it,parts,total};});
  const max=Math.max(1,...filtered.map(x=>x.total));
  return filtered.map(({it,parts,total},i)=>{
    const w=total/max*100,full=it[2]||it[0],dom=parts[0],comp=total?parts.map(([m,v])=>'<i style="width:'+(v/total*100).toFixed(1)+'%;background:'+DATA.colors[m]+'" title="'+esc(pretty(m))+' '+pct(v,total)+'"></i>').join(''):'';
    const attrs=sessionRows?' role="button" tabindex="0" aria-label="会话 '+esc(it[0])+'，'+fmt(total)+' Token，按 Enter 回放"':'';
    return '<div class=lb-row'+attrs+'><span class=rk>'+String(i+1).padStart(2,'0')+'</span>'
      +'<span class=lb-name title="'+esc(full)+'">'+esc(it[0])+'</span>'
      +'<span class=lb-bar><i style="width:'+w.toFixed(1)+'%"></i></span>'
      +'<span class=lb-val>'+human(total)+'</span><span class=lb-comp>'+comp+'</span><span class=lb-dom>'+(dom?'主力 '+esc(pretty(dom[0]))+' · 当前模型筛选构成':'当前模型筛选下无 Token')+'</span></div>';
  }).join('');
}
function renderTop(){
  const detail=focusDetail(), cwds=detail?detail.top_cwds:DATA.top_cwds, sessions=detail?detail.top_sessions:DATA.top_sessions;
  document.getElementById('top-cwd').innerHTML = lbRows(cwds);
  document.getElementById('top-sess').innerHTML = lbRows(sessions,true);
  document.getElementById('top-hint').textContent=(state.focusPeriod?'当前回看期 · ':'')+'保持原 Top 顺序 · 数值和色条按当前模型筛选 · 会话可回放';
  Array.from(document.getElementById('top-sess').querySelectorAll('.lb-row')).forEach((row,i)=>{
    const it=sessions[i]; if(!it) return;
    row.style.cursor='pointer';row.title='点击或按 Enter 回放逐轮 token';
    const activate=()=>openReplay(it[2],it[0]);row.addEventListener('click',activate);row.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate();}});
  });
}

function renderClock(){
  const h=filteredHourly(), box=document.getElementById('clock');
  const total=h.reduce((a,b)=>a+(b||0),0);
  if(!total){ box.innerHTML='<div class="hint">无数据</div>'; return; }
  const max=Math.max.apply(null,h);
  let peak=0; for(let i=1;i<24;i++) if((h[i]||0)>(h[peak]||0)) peak=i;
  const size=270, cx=size/2, cy=size/2, rmax=size/2-28, rmin=34;
  const sw=Math.max(3, 2*Math.PI*rmin/24-3);
  const p=['<svg viewBox="0 0 '+size+' '+size+'" class="clock" aria-label="每小时 token 分布">'];
  p.push('<circle cx="'+cx+'" cy="'+cy+'" r="'+rmax+'" fill="none" stroke="var(--border)" stroke-dasharray="2 5"/>');
  for(let i=0;i<24;i++){
    const ang=(i/24)*2*Math.PI - Math.PI/2;
    if(i%3===0){
      const r2=rmax+5;
      p.push('<line x1="'+(cx+Math.cos(ang)*rmax).toFixed(1)+'" y1="'+(cy+Math.sin(ang)*rmax).toFixed(1)+'" x2="'+(cx+Math.cos(ang)*r2).toFixed(1)+'" y2="'+(cy+Math.sin(ang)*r2).toFixed(1)+'" class="clk-tick"/>');
      p.push('<text x="'+(cx+Math.cos(ang)*(r2+10)).toFixed(1)+'" y="'+(cy+Math.sin(ang)*(r2+10)+3).toFixed(1)+'" text-anchor="middle" class="clk-h">'+String(i).padStart(2,'0')+'</text>');
    }
  }
  for(let i=0;i<24;i++){
    const v=h[i]||0; if(v<=0) continue;
    const frac=v/max, ang=(i/24)*2*Math.PI - Math.PI/2;
    const ri=rmin, ro=rmin+frac*(rmax-rmin), isPeak=i===peak;
    p.push('<line class="clk-spoke'+(isPeak?' peak':'')+'" x1="'+(cx+Math.cos(ang)*ri).toFixed(1)+'" y1="'+(cy+Math.sin(ang)*ri).toFixed(1)+'" x2="'+(cx+Math.cos(ang)*ro).toFixed(1)+'" y2="'+(cy+Math.sin(ang)*ro).toFixed(1)+'" stroke-width="'+sw.toFixed(1)+'"><title>'+String(i).padStart(2,'0')+':00 · '+human(v)+' tk</title></line>');
  }
  p.push('<circle class="clk-core" cx="'+cx+'" cy="'+cy+'" r="'+rmin+'"/>');
  p.push('<text x="'+cx+'" y="'+(cy-2)+'" text-anchor="middle" class="clk-center">'+String(peak).padStart(2,'0')+':00</text>');
  p.push('<text x="'+cx+'" y="'+(cy+14)+'" text-anchor="middle" class="clk-sub">峰值时段</text></svg>');
  box.innerHTML=p.join('');
}

function buildDiscoveries(){
  const days=DATA.day||[], vals=days.map(d=>d.total||0), total=vals.reduce((a,b)=>a+b,0), avg=vals.length?total/vals.length:0;
  if(!days.length)return [{t:'数据还在沉睡，等第一批 Token 落下后，故事会从这里开始。',s:'暂无足够数据'}];
  const top=[...days].sort((a,b)=>b.total-a.total), h=DATA.hourly||[], ht=h.reduce((a,b)=>a+b,0), peak=h.indexOf(Math.max(...h));
  const mt={};days.forEach(d=>Object.entries(d.models||{}).forEach(([m,v])=>mt[m]=(mt[m]||0)+v));const me=Object.entries(mt).sort((a,b)=>b[1]-a[1]);
  const wd=Array(7).fill(0);days.forEach(d=>{const p=d.period.split('-'),x=new Date(Date.UTC(+p[0],+p[1]-1,+p[2]));wd[(x.getUTCDay()+6)%7]+=d.total;});
  const out=[];
  if(top[0])out.push({t:'你最猛烈的一天是 '+fmtLabel(top[0].period,'day')+'，单日燃烧 '+human(top[0].total)+' Token。',s:avg?'相当于日均值的 '+(top[0].total/avg).toFixed(1)+' 倍':''});
  if(top.length>=3){const v=top.slice(0,3).reduce((a,d)=>a+d.total,0);out.push({t:'仅仅三个最高峰日，就贡献了全部 Token 的 '+(v/total*100).toFixed(1)+'%。',s:'少数时刻塑造了大部分数据地貌'});}
  if(peak>=0)out.push({t:'你的算力生物最喜欢在 '+String(peak).padStart(2,'0')+':00 出没。',s:'这个小时累计 '+human(h[peak]||0)+' Token'});
  const night=(h.slice(0,6).reduce((a,b)=>a+b,0)+h.slice(22).reduce((a,b)=>a+b,0))/(ht||1);if(night>.25)out.push({t:'夜色承载了你 '+(night*100).toFixed(1)+'% 的 Token，屏幕熄灭得比城市更晚。',s:'统计范围：22:00–06:00'});
  if(me[0])out.push({t:pretty(me[0][0])+' 是你的主力引擎，独自承载 '+(me[0][1]/total*100).toFixed(1)+'% 的算力。',s:me[1]?'是第二名的 '+(me[0][1]/me[1][1]).toFixed(1)+' 倍':'目前没有第二名'});
  if(me.length>=3)out.push({t:'你使用过 '+me.length+' 种模型，数据光谱已经不再是单色。',s:'每种模型都在 Token 星云中凝聚成不同颜色的星团'});
  const best=wd.indexOf(Math.max(...wd));out.push({t:['周一','周二','周三','周四','周五','周六','周日'][best]+'是你一周里算力气压最高的一天。',s:'累计 '+human(wd[best])+' Token'});
  const cr=DATA.cache_read||0;if(total&&cr/total>.5)out.push({t:'超过一半的 Token 曾被缓存记住，你的上下文很少真正从零开始。',s:'缓存占比 '+(cr/total*100).toFixed(1)+'%'});
  if(DATA.top_cwds&&DATA.top_cwds[0])out.push({t:'「'+DATA.top_cwds[0][0]+'」是这座数据宇宙里质量最大的项目。',s:'累计 '+human(DATA.top_cwds[0][1])+' Token'});
  const recent=vals.slice(-7),old=vals.slice(-14,-7),ra=recent.reduce((a,b)=>a+b,0)/(recent.length||1),oa=old.reduce((a,b)=>a+b,0)/(old.length||1);if(oa)out.push({t:'最近七天的日均 Token 比此前七天 '+(ra>=oa?'高':'低')+' '+Math.abs((ra/oa-1)*100).toFixed(1)+'%。',s:ra>=oa?'数据天气正在升温':'算力气压正在回落'});
  out.push({t:'你的 '+fmt(DATA.n_sessions||0)+' 个会话，正在共同组成一份无法复制的开发者轨迹。',s:'它只存在于这份本地生成的 HTML 中'});
  return out;
}
let discoveryIndex=0, discoveryPinned=false;
const DISCOVERY_KEY='tk-discovery';
function loadDiscovery(){try{const v=JSON.parse(localStorage.getItem(DISCOVERY_KEY)||'{}');discoveryIndex=Math.max(0,Number(v.index)||0);discoveryPinned=!!v.pinned;}catch(e){}}
function saveDiscovery(){try{localStorage.setItem(DISCOVERY_KEY,JSON.stringify({index:discoveryIndex,pinned:discoveryPinned}));}catch(e){}}
function renderDiscovery(step=0,force=false){const a=buildDiscoveries();if(step&&(!discoveryPinned||force))discoveryIndex=(discoveryIndex+step+a.length)%a.length;discoveryIndex%=a.length;document.getElementById('discovery-text').textContent=a[discoveryIndex].t;document.getElementById('discovery-sub').textContent=(a[discoveryIndex].s||'所有发现均由本地数据计算。')+(discoveryPinned?' · 当前洞察已固定':'');document.getElementById('discovery-pos').textContent=(discoveryIndex+1)+'/'+a.length;const pin=document.getElementById('discovery-pin'),card=document.getElementById('discovery-card');pin.classList.toggle('on',discoveryPinned);pin.setAttribute('aria-pressed',String(discoveryPinned));pin.textContent=discoveryPinned?'◆ 已固定':'◇ 固定';card.classList.toggle('pinned',discoveryPinned);saveDiscovery();}
function stepDiscovery(step){if(discoveryPinned){toast('当前洞察已固定，取消固定后可切换');return;}renderDiscovery(step,true);}
loadDiscovery();
document.getElementById('discovery-next').addEventListener('click',e=>{e.stopPropagation();stepDiscovery(1);});
document.getElementById('discovery-pin').addEventListener('click',e=>{e.stopPropagation();discoveryPinned=!discoveryPinned;renderDiscovery();});
document.getElementById('discovery-card').addEventListener('click',e=>{if(e.target.closest('button'))return;stepDiscovery(1);});
document.getElementById('discovery-card').addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();stepDiscovery(e.key==='ArrowRight'?1:-1);}else if((e.key==='Enter'||e.key===' ')&&!e.target.closest('button')){e.preventDefault();stepDiscovery(1);}});
function renderFooter(){
  const h=DATA.hourly||[], peak=h.indexOf(Math.max(...h)), lines=[
    'by <b>LingXi</b> · 本页装载了 <b>'+human(DATA.day.reduce((s,d)=>s+d.total,0))+'</b> Token 的痕迹。',
    '你的缓存替你记住了 <b>'+human(DATA.cache_read||0)+'</b> Token。',
    '算力最常在 <b>'+String(Math.max(0,peak)).padStart(2,'0')+':00</b> 亮起。',
    '纯本地生成 · 没有任何数据离开这台电脑。'
  ];if(_ach)lines.splice(2,0,'<b>'+fmt(_ach.all.length-_ach.got)+'</b> 枚成就仍在数据深处沉睡。');document.getElementById('dynamic-footer').innerHTML=lines[(new Date().getDate()+DATA.day.length)%lines.length];
}

function shareStats(){
  if(!lazyState.creature?.rendered){lazyState.creature=Object.assign({},lazyState.creature,{visible:true});renderLazy('creature',true);}
  const days=DATA.day||[],total=days.reduce((a,d)=>a+d.total,0),calls=days.reduce((a,d)=>a+d.calls,0),h=DATA.hourly||[],peak=h.indexOf(Math.max(...h)),mt={};days.forEach(d=>Object.entries(d.models||{}).forEach(([m,v])=>mt[m]=(mt[m]||0)+v));const dom=Object.entries(mt).sort((a,b)=>b[1]-a[1])[0];
  return {total,calls,peak,dom:dom?pretty(dom[0]):'—',cache:total?(DATA.cache_read||0)/total:0,ach:_ach||getBadgeData(),creature:document.getElementById('creature-name').textContent||'Token 生物'};
}
function openShare(type){
  const x=shareStats(), content=document.getElementById('share-content');
  if(type==='passport')content.innerHTML='<div class=passport id=share-card><div class=pass-head><div><div class=pass-k>LOCAL DEVELOPER IDENTITY</div><h3>TOKEN PASSPORT</h3></div><div class=pass-id>ISSUED '+esc(DATA.generated)+'<br>NO DATA UPLOADED</div></div><div class=pass-grid><div><div class=pass-k>DEVELOPER TYPE</div><div class=pass-hero>'+(x.peak<6||x.peak>=22?'MIDNIGHT<br>NAVIGATOR':'DAYLIGHT<br>BUILDER')+'</div><div class=pass-sub>'+esc(x.creature)+' · 本地数据宇宙居民</div></div><div class=pass-fields><div class=pass-field><span>TOTAL TOKENS</span><b>'+fmt(x.total)+'</b></div><div class=pass-field><span>PRIMARY MODEL</span><b>'+esc(x.dom)+'</b></div><div class=pass-field><span>PEAK GATE</span><b>'+String(Math.max(0,x.peak)).padStart(2,'0')+':00</b></div><div class=pass-field><span>CACHE</span><b>'+Math.round(x.cache*100)+'%</b></div><div class=pass-field><span>CALLS</span><b>'+fmt(x.calls)+'</b></div><div class=pass-field><span>ACHIEVEMENTS</span><b>'+fmt(x.ach.got)+' / '+fmt(x.ach.all.length)+'</b></div></div></div><div class=pass-foot><span>VALID IN ALL LOCAL TERMINALS<br>PRIVACY CLASS: OFFLINE</span><span class=barcode>||| || ||| | |||| || |</span></div></div>';
  else content.innerHTML='<div class=receipt id=share-card><h3>TOKEN STORE</h3><div class=receipt-center>LOCAL TERMINAL · '+esc(DATA.generated.slice(0,10))+'<br>ORDER #'+String(x.total%100000).padStart(5,'0')+'</div><hr>'+(DATA.models||[]).map(m=>{const v=(DATA.day||[]).reduce((a,d)=>a+(d.models[m]||0),0);return '<div class=receipt-row><span>'+esc(pretty(m)).slice(0,18)+'</span><b>'+fmt(v)+'</b></div>';}).join('')+'<hr><div class=receipt-row><span>CALLS</span><b>'+fmt(x.calls)+'</b></div><div class=receipt-row><span>CACHE SAVED</span><b>'+fmt(DATA.cache_read||0)+'</b></div><div class=receipt-row><span>ACHIEVEMENTS</span><b>'+fmt(x.ach.got)+'</b></div><hr><div class="receipt-row receipt-total"><span>TOTAL</span><b>'+fmt(x.total)+' TK</b></div><div class=receipt-code>|||| || ||||| | ||| ||</div><div class=receipt-note>THANK YOU FOR CODING<br>OPEN 24 HOURS · NO DATA UPLOADED</div></div>';
  openModal(document.getElementById('share-modal'),document.getElementById('share-close'));document.getElementById('share-modal').dataset.type=type;
}
function closeShare(){closeModal(document.getElementById('share-modal'));}
document.getElementById('passport-btn').addEventListener('click',()=>openShare('passport'));document.getElementById('receipt-btn').addEventListener('click',()=>openShare('receipt'));document.getElementById('share-close').addEventListener('click',closeShare);document.getElementById('share-modal').addEventListener('click',e=>{if(e.target.id==='share-modal')closeShare();});document.getElementById('share-modal').addEventListener('keydown',e=>trapModalFocus(e,e.currentTarget));
document.getElementById('share-save').addEventListener('click',()=>{const card=document.getElementById('share-card'),style=[...document.querySelectorAll('style')].map(x=>x.textContent).join('\n'),html='<!doctype html><meta charset=utf-8><style>'+style+'body{display:grid;place-items:center;min-height:100vh;background:#080b12;padding:30px}</style>'+card.outerHTML;const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([html],{type:'text/html;charset=utf-8'}));a.download='token-'+document.getElementById('share-modal').dataset.type+'.html';a.click();toast('分享卡已保存为 HTML');});

function renderWeather(){
  const days=(DATA.day||[]).slice(-14), recent=days.slice(-7), prev=days.slice(-14,-7);
  const rt=recent.reduce((a,d)=>a+d.total,0), pt=prev.reduce((a,d)=>a+d.total,0), ratio=pt?rt/pt:1;
  const h=filteredHourly(), ht=h.reduce((a,b)=>a+b,0), night=ht?(h.slice(0,6).reduce((a,b)=>a+b,0)+h.slice(22).reduce((a,b)=>a+b,0))/ht:0;
  const total=selectedRows().reduce((a,r)=>a+r.total,0), detail=focusDetail(), cr=detail?detail.cache_read:selectedCacheRead(), cache=total?cr/total:0;
  let w={i:'☀️',t:'Token 晴朗',c:'用量平稳，算力气压舒适。今天适合把注意力留给代码本身。',m:'稳定',g:'rgba(245,158,11,.28)'};
  if(cache>=.72) w={i:'🌈',t:'缓存彩虹',c:'大量上下文被成功复用，重复算力正在悄悄变成你的隐形红利。',m:Math.round(cache*100)+'%',g:'rgba(167,139,250,.34)'};
  if(ratio>=1.35) w={i:'🌧️',t:'局部 Token 暴雨',c:'最近七期明显高于此前节奏，算力云层正在快速增厚。',m:'+'+Math.round((ratio-1)*100)+'%',g:'rgba(91,141,239,.42)'};
  if(ratio>=1.8) w={i:'⛈️',t:'模型风暴',c:'Token 气压出现强烈跃升。建议点开柱状图，定位是哪一期掀起了风暴。',m:'×'+ratio.toFixed(1),g:'rgba(244,114,182,.38)'};
  if(night>=.42) w={i:'🌙',t:'深夜低压',c:'大量算力聚集在夜间，屏幕亮着的时候，城市可能已经睡了。',m:Math.round(night*100)+'%',g:'rgba(99,102,241,.38)'};
  if(state.focusPeriod) w.c='时光探针已锁定 '+fmtLabel(state.focusPeriod,state.gran)+'。此刻的天气只属于这一段时间。';
  document.getElementById('w-icon').textContent=w.i; document.getElementById('w-title').textContent=w.t; document.getElementById('w-copy').textContent=w.c; document.getElementById('w-metric').textContent=w.m; document.getElementById('w-metric-label').textContent=state.focusPeriod?'局部气候':'相对近况'; document.getElementById('weather-card').style.setProperty('--weather-glow',w.g);
}
function renderProbe(){
  const el=document.getElementById('time-probe');
  if(!state.focusPeriod){el.classList.remove('on');return;}
  const row=selectedRows()[0], dom=row?Object.entries(row.models).sort((a,b)=>b[1]-a[1])[0]:null;
  document.getElementById('probe-copy').innerHTML='<b>正在回看 '+esc(fmtLabel(state.focusPeriod,state.gran))+'</b> · '+human(row?row.total:0)+' tk'+(dom?' · 主力 '+esc(pretty(dom[0])):'')+' · Esc 返回全景';
  el.classList.add('on');
}
function toggleFocus(period,restoreBar=false){ state.focusPeriod=state.focusPeriod===period?null:period;invalidateDerived(); renderDataViews();if(restoreBar){const el=[...document.querySelectorAll('#bar .barstack')].find(x=>x.dataset.period===period);if(el){barCursor=Number(el.dataset.index||0);el.focus();}} }
function clearFocus(restoreBar=false){ if(!state.focusPeriod)return;const period=state.focusPeriod;state.focusPeriod=null;invalidateDerived();renderDataViews();if(restoreBar){const el=[...document.querySelectorAll('#bar .barstack')].find(x=>x.dataset.period===period);if(el){barCursor=Number(el.dataset.index||0);el.focus();}} }

document.getElementById('probe-close').addEventListener('click',clearFocus);

const THEMES=[['auto','🌗','自动'],['light','☀️','亮色'],['dark','🌙','暗色']];
let restoringView=true;
function currentTheme(){return document.documentElement.getAttribute('data-theme')||'auto';}
function validFocus(period,gran){return !!period&&DATA[gran].some(r=>r.period===period);}
function viewParams(){
  const p=new URLSearchParams();p.set('gran',state.gran);
  if(state.models.size!==DATA.models.length)DATA.models.filter(m=>state.models.has(m)).forEach(m=>p.append('model',m));
  if(state.focusPeriod)p.set('focus',state.focusPeriod);
  if(state.compare)p.set('compare','1');
  const theme=currentTheme();if(theme!=='auto')p.set('t',theme);
  return p;
}
function viewURL(){const u=new URL(location.href);u.search=viewParams().toString();u.hash='';return u.toString();}
function portableViewURL(){if(location.protocol!=='file:')return viewURL();const q=viewParams().toString(),name=location.pathname.split('/').pop()||'dashboard.html';return name+(q?'?'+q:'');}
function syncViewURL(replace=true){if(restoringView||!history.replaceState)return;const u=viewURL();history[replace?'replaceState':'pushState'](null,'',u);}
function restoreViewFromURL(){
  const p=new URLSearchParams(location.search),g=p.get('gran')||((location.hash||'').replace('#',''));
  if(['day','week','month'].includes(g))state.gran=g;
  const requested=p.getAll('model'),legacy=p.get('models');if(requested.length||legacy!==null){const allowed=new Set(DATA.models),models=(requested.length?requested:(legacy?legacy.split(','):[])).filter(m=>allowed.has(m));state.models=new Set(models);}else state.models=new Set(DATA.models);previousModels=null;
  const focus=p.get('focus');state.focusPeriod=validFocus(focus,state.gran)?focus:null;state.compare=p.get('compare')==='1';
  const theme=(p.get('t')||'').toLowerCase();if(['auto','light','dark'].includes(theme))applyTheme(theme);
}
function viewDescription(){const gran={day:'按日',week:'按周',month:'按月'}[state.gran],modelCount=state.models.size,focus=state.focusPeriod?fmtLabel(state.focusPeriod,state.gran):'全景',compare=state.compare?'已开启':'关闭';return {gran,modelCount,focus,compare};}
function syncGranControls(){document.querySelectorAll('#tabs button').forEach(x=>{const on=x.dataset.gran===state.gran;x.classList.toggle('on',on);x.setAttribute('aria-pressed',String(on));});}
function renderViewCapsule(){
  const d=viewDescription(),label=document.getElementById('view-label'),capsule=document.getElementById('view-capsule');
  label.textContent=d.gran.replace('按','')+' · '+(d.modelCount===DATA.models.length?'全部模型':d.modelCount+'/'+DATA.models.length+' 模型')+' · '+d.focus;
  capsule.classList.toggle('dirty',!!state.focusPeriod||state.models.size!==DATA.models.length||state.compare);
  document.getElementById('view-summary').innerHTML='<b>'+d.gran+'</b> · '+d.modelCount+' / '+DATA.models.length+' 个模型<br><b>'+(state.focusPeriod?'时光探针':'时间范围')+'</b> · '+esc(d.focus)+'<br><b>幻影对比</b> · '+d.compare;
  syncGranControls();document.getElementById('compare-btn').classList.toggle('on',state.compare);
}
function resetView(){state.gran='month';state.models=new Set(DATA.models);state.focusPeriod=null;state.compare=false;previousModels=null;invalidateDerived();renderFilters();renderDataViews();toast('已恢复月度全景');}
async function copyText(text){try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(text);return true;}}catch(e){}const ta=document.createElement('textarea');ta.value=text;ta.style.cssText='position:fixed;left:-9999px;top:0';document.body.appendChild(ta);ta.select();let ok=false;try{ok=document.execCommand('copy');}catch(e){}ta.remove();return ok;}
function copyViewLink(){copyText(portableViewURL()).then(ok=>toast(ok?'当前视图链接已复制':'复制失败，请从地址栏复制'));}
document.getElementById('view-capsule').addEventListener('click',e=>{e.stopPropagation();const pop=document.getElementById('view-pop'),open=!pop.classList.contains('open');pop.classList.toggle('open',open);e.currentTarget.setAttribute('aria-expanded',String(open));});
document.getElementById('view-copy').addEventListener('click',copyViewLink);document.getElementById('view-reset').addEventListener('click',resetView);document.addEventListener('click',e=>{if(!e.target.closest('.view-wrap')){document.getElementById('view-pop').classList.remove('open');document.getElementById('view-capsule').setAttribute('aria-expanded','false');}});
window.addEventListener('popstate',()=>{restoringView=true;restoreViewFromURL();invalidateDerived();renderFilters();renderDataViews();restoringView=false;});

document.getElementById('compare-btn').addEventListener('click',()=>{ state.compare=!state.compare; renderBar();renderViewCapsule();syncViewURL(); });

const LAZY_RENDERERS={project:renderProjectLens,reuse:renderReuseRiver,flow:renderFlow,creature:renderCreature,race:renderRace,badges:renderBadges,dna:renderDNA};
const lazyState={};
function renderLazy(name,force=false){const card=document.querySelector('[data-lazy="'+name+'"]');if(!card||card.style.display==='none')return;if(!force&&!lazyState[name]?.visible){card.classList.add('lazy-pending');lazyState[name]=Object.assign({},lazyState[name],{dirty:true});return;}card.classList.remove('lazy-pending');LAZY_RENDERERS[name]();lazyState[name]=Object.assign({},lazyState[name],{dirty:false,rendered:true});}
function markLazyDirty(){['project','reuse','flow','dna'].forEach(name=>{lazyState[name]=Object.assign({},lazyState[name],{dirty:true});if(lazyState[name].visible)renderLazy(name,true);});}
function markStaticLazyDirty(){['creature','race','badges'].forEach(name=>{if(!lazyState[name]?.rendered)lazyState[name]=Object.assign({},lazyState[name],{dirty:true});});}
function initLazyRendering(){
  document.querySelectorAll('[data-lazy]').forEach(card=>{const name=card.dataset.lazy;lazyState[name]={visible:false,dirty:true,rendered:false};card.classList.add('lazy-pending');});
  if(!('IntersectionObserver'in window)){Object.keys(LAZY_RENDERERS).forEach(name=>{lazyState[name].visible=true;renderLazy(name,true);});return;}
  const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{const name=entry.target.dataset.lazy;lazyState[name]=Object.assign({},lazyState[name],{visible:entry.isIntersecting});if(entry.isIntersecting&&(lazyState[name].dirty||!lazyState[name].rendered))renderLazy(name,true);}),{rootMargin:'500px 0px'});
  document.querySelectorAll('[data-lazy]').forEach(card=>observer.observe(card));
}
function renderCoreViews(){renderKPI();const n=DATA[state.gran].length;document.getElementById('bar-hint').textContent=n+' 期 · 点击柱子进入时光探针';renderBar();renderDonut();renderTable();renderTop();renderStatusPulse();renderViewCapsule();}
function renderTimeViews(){renderClock();renderWeather();renderProbe();renderRhythm();renderBlock();renderDaily();}
function renderModelViews(){renderMultiples();markLazyDirty();markStaticLazyDirty();}
function renderDataViews(){renderCoreViews();renderTimeViews();renderModelViews();renderFunFacts();renderFortune();renderDiscovery();renderFooter();bindModelLinks();syncViewURL();}
function render(){renderDataViews();}


document.getElementById('tabs').addEventListener('click',e=>{
  const b=e.target.closest('button'); if(!b) return;
  setGran(b.dataset.gran);
});
function setGran(g){
  if(!['day','week','month'].includes(g))return;
  state.gran=g; state.focusPeriod=null;invalidateDerived();
  renderDataViews();
}

document.getElementById('meta').textContent =
  '生成于 '+DATA.generated+' · '+(DATA.range.since||'起始')+' ~ '+(DATA.range.until||'至今')+(DATA.anonymized?' · 脱敏导出（标识已替换）':'');
document.getElementById('source-txt').textContent = '来源 '+(DATA.source.join(' / ')||'无');
if(DATA.anonymized){document.getElementById('source-pill').title='项目路径、会话标识与自然语言标题已替换；精确日期、Token、模型与逐轮序列仍保留。';}

/* 主题：自动 / 亮 / 暗 三态，localStorage 记忆，覆盖系统 */
function applyTheme(t){
  if(t==='light'||t==='dark') document.documentElement.setAttribute('data-theme',t);
  else document.documentElement.removeAttribute('data-theme');
  const c=THEMES.find(x=>x[0]===t)||THEMES[0];
  const b=document.getElementById('theme-btn');
  b.textContent=c[1]; b.title='主题：'+c[2]+'（点击切换）';
  try{localStorage.setItem('tk-theme',t);}catch(e){}
  if(typeof restoringView!=='undefined')syncViewURL();
}
document.getElementById('theme-btn').addEventListener('click',()=>{
  const order=['auto','light','dark'], cur=localStorage.getItem('tk-theme')||'auto';
  applyTheme(order[(order.indexOf(cur)+1)%order.length]);
});
function defaultMotion(){if(window.matchMedia('(prefers-reduced-motion: reduce)').matches)return 'off';if(window.matchMedia('(pointer: coarse)').matches||innerWidth<760)return 'low';const mem=navigator.deviceMemory||8,cores=navigator.hardwareConcurrency||8;return mem<=4||cores<=4?'low':'full';}
function applyMotion(choice,persist=true){if(!['auto','full','low','off'].includes(choice))choice='auto';const reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches,effective=reduce?'off':choice==='auto'?defaultMotion():choice;document.documentElement.setAttribute('data-motion',effective);document.getElementById('motion-select').value=choice;if(persist)try{localStorage.setItem('tk-motion',choice);}catch(e){}window.dispatchEvent(new CustomEvent('tk-motion-change',{detail:{choice,effective}}));}
document.getElementById('motion-select').addEventListener('change',e=>applyMotion(e.target.value));
let motionChoice='auto';try{motionChoice=localStorage.getItem('tk-motion')||'auto';}catch(e){}applyMotion(motionChoice,false);
const motionMedia=window.matchMedia('(prefers-reduced-motion: reduce)');if(motionMedia.addEventListener)motionMedia.addEventListener('change',()=>applyMotion(document.getElementById('motion-select').value,false));
let motionResizeT=0;addEventListener('resize',()=>{if(document.getElementById('motion-select').value!=='auto')return;clearTimeout(motionResizeT);motionResizeT=setTimeout(()=>applyMotion('auto',false),120);},{passive:true});
// 初始主题：URL ?t=light|dark 优先（可分享/截图），否则 localStorage，否则跟随系统
(function(){
  const q=(new URLSearchParams(location.search).get('t')||'').toLowerCase();
  applyTheme(['light','dark'].includes(q)?q:(localStorage.getItem('tk-theme')||'auto'));
})();

function markdownCell(value){return String(value).replace(/\\/g,'\\\\').replace(/\|/g,'\\|').replace(/[\r\n]+/g,' ');}
function downloadBlob(content,type,filename){const url=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),0);}

const modalState=new WeakMap();
function modalFocusables(modal){return [...modal.querySelectorAll('button,input,select,textarea,a[href],[tabindex]:not([tabindex="-1"])')].filter(x=>!x.disabled&&x.getClientRects().length);}
function openModal(modal,initialFocus){modalState.set(modal,{returnFocus:document.activeElement});modal.classList.add('open');modal.setAttribute('aria-hidden','false');document.body.classList.add('modal-open');setTimeout(()=>{const target=initialFocus||modalFocusables(modal)[0];if(target)target.focus();},0);}
function closeModal(modal){modal.classList.remove('open');modal.setAttribute('aria-hidden','true');if(!document.querySelector('.share-modal.open,.ach-modal.open,.help-modal.open,.modal.open'))document.body.classList.remove('modal-open');const state=modalState.get(modal);modalState.delete(modal);if(state?.returnFocus&&document.contains(state.returnFocus))state.returnFocus.focus();}
function trapModalFocus(e,modal){if(e.key!=='Tab'||!modal.classList.contains('open'))return;const items=modalFocusables(modal);if(!items.length){e.preventDefault();return;}const first=items[0],last=items[items.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}
function activeModal(){return document.querySelector('.share-modal.open,.ach-modal.open,.help-modal.open,.modal.open');}

// CSV 导出（当前粒度 + 所选模型）
function exportCSV(){
  const rows=selectedRows(), cols=DATA.models.filter(m=>state.models.has(m));
  const head=['period','total_tokens',...cols.map(pretty),'calls'];
  const body=rows.map(r=>[r.period,r.total,...cols.map(m=>r.models[m]||0),r.calls]);
  const csv=[head,...body].map(r=>r.map(x=>/[,\"\n]/.test(String(x))?'"'+String(x).replace(/"/g,'""')+'"':x).join(',')).join('\n');
  downloadBlob('﻿'+csv,'text/csv;charset=utf-8','tokens-'+state.gran+'.csv');
}
document.getElementById('csv-btn').addEventListener('click', exportCSV);
function exportMarkdown(){
  const rows=selectedRows(), cols=DATA.models.filter(m=>state.models.has(m));
  const head=[LABEL[state.gran],'总 token',...cols.map(pretty),'调用'];
  const body=rows.map(r=>[r.period,fmt(r.total),...cols.map(m=>fmt(r.models[m]||0)),fmt(r.calls)]);
  const line=a=>'| '+a.map(markdownCell).join(' | ')+' |';
  const md=['# Token 用量报告','',line(head),line(head.map((_,i)=>i?'---:':'---')),...body.map(line),'','> 本地生成于 '+markdownCell(DATA.generated)+'，未上传任何数据。'].join('\n');
  downloadBlob(md,'text/markdown;charset=utf-8','tokens-'+state.gran+'.md');toast('Markdown 报告已生成');
}
document.getElementById('md-btn').addEventListener('click',exportMarkdown);
function openHelp(){const modal=document.getElementById('help-modal');openModal(modal,document.getElementById('help-close'));}
function closeHelp(){closeModal(document.getElementById('help-modal'));}
document.getElementById('help-close').addEventListener('click',closeHelp);document.getElementById('help-modal').addEventListener('click',e=>{if(e.target.id==='help-modal')closeHelp();});document.getElementById('help-modal').addEventListener('keydown',e=>trapModalFocus(e,e.currentTarget));
// 键盘：1/2/3 切粒度，T 切主题，E 导出 CSV，? 查看帮助
document.addEventListener('keydown',e=>{
  const tag=(e.target.tagName||'').toUpperCase();
  if(tag==='INPUT'||tag==='TEXTAREA') return;
  if(e.key==='1') setGran('day');
  else if(e.key==='2') setGran('week');
  else if(e.key==='3') setGran('month');
  else if(e.key==='t'||e.key==='T'){ const o=['auto','light','dark'],c=localStorage.getItem('tk-theme')||'auto'; applyTheme(o[(o.indexOf(c)+1)%3]); }
  else if(e.key==='e'||e.key==='E') exportCSV();
  else if(e.key==='?') openHelp();
});

/* ---- 趣味 / 意想不到的交互 ---- */
function toast(msg, ms=2600){
  let t=document.getElementById('toast');
  if(!t){t=document.createElement('div');t.id='toast';t.setAttribute('role','status');t.setAttribute('aria-live','polite');t.setAttribute('aria-atomic','true');document.body.appendChild(t);}
  t.textContent=msg;t.classList.add('show');clearTimeout(t._t);
  t._t=setTimeout(()=>t.classList.remove('show'),ms);
}
function confetti(){
  if(motionDisabled())return;
  const cs=['#5b8def','#a78bfa','#f472b6','#14b8a6','#f59e0b','#7aa2f7'];
  for(let i=0;i<90;i++){
    const d=document.createElement('div');d.className='confetti';
    d.style.left=(Math.random()*100)+'vw';d.style.background=cs[i%cs.length];
    d.style.animationDelay=(Math.random()*.5)+'s';d.style.animationDuration=(1.6+Math.random()*1)+'s';
    document.body.appendChild(d);setTimeout(()=>d.remove(),2700);
  }
}
// Konami ↑↑↓↓←→←→BA
(function(){
  const SEQ=['ArrowUp','ArrowUp','ArrowDown','ArrowDown','ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','b','a'];
  let i=0;
  document.addEventListener('keydown',e=>{
    const k=e.key.length===1?e.key.toLowerCase():e.key;
    if(k===SEQ[i]){i++;if(i===SEQ.length){i=0;confetti();toast('🎉 Konami 触发！真·肝帝已觉醒');}}
    else i=(k===SEQ[0])?1:0;
  });
})();
// 点 Logo：随机吐槽/夸奖
document.getElementById('logo').addEventListener('click',()=>{
  const lg=document.getElementById('logo');lg.classList.remove('spin');void lg.offsetWidth;lg.classList.add('spin');
  const h=DATA.hourly||[];let ph=-1,pi=-1;for(let i=0;i<24;i++)if((h[i]||0)>ph){ph=h[i]||0;pi=i;}
  const top=(DATA.top_cwds&&DATA.top_cwds[0])?DATA.top_cwds[0][0]:'—';
  const calls=(DATA.day||[]).reduce((a,r)=>a+r.calls,0);
  const F=[
    '缓存帮你省了 '+human(DATA.cache_read||0)+' token，钱包松了口气',
    '峰值在 '+(pi>=0?String(pi).padStart(2,'0')+':00':'?')+'，夜猫子实锤',
    human(lastTotal)+' token ≈ '+fmt(Math.max(0,Math.round(lastTotal/27000)))+' 篇毕业论文',
    '最肝的项目：'+top,
    '别肝了，站起来活动活动 🧘',
    '已累计 '+fmt(calls)+' 次调用，键盘冒烟了',
    '今日份的算力已燃烧 ✨'
  ];
  toast(F[Math.floor(Math.random()*F.length)]);
});
// 点 Hero 数字：短按切换表达方式；双击复制精确值
const heroValue=document.querySelector('.kpi.is-primary .v');
heroValue.addEventListener('click',()=>{
  state.numberMode=(state.numberMode+1)%3;
  document.getElementById('k-total').textContent=displayNumber(lastTotal);
  toast(['精确数字','中文数量级','国际缩写'][state.numberMode]);
});
heroValue.addEventListener('dblclick',()=>{
  try{navigator.clipboard.writeText(String(lastTotal));}catch(e){}
  toast('已复制 '+fmt(lastTotal)+' token');
});
// Hero 跟手光斑
(function(){
  const el=document.querySelector('.kpi.is-primary');
  if(!el)return;
  el.addEventListener('mousemove',e=>{const r=el.getBoundingClientRect();el.style.setProperty('--mx',(e.clientX-r.left)+'px');el.style.setProperty('--my',(e.clientY-r.top)+'px');});
})();
// 趣味换算
const FUN=[
  ['一本《红楼梦》全文',1000000],['一部《三体》三部曲',1200000],['整部《哈利波特》',1300000],
  ['一部《指环王》三部曲',1700000],['一集美剧字幕',10000],['一首流行歌词',400],
  ['一篇本科毕业论文',27000],['一次深度对话',5000],['一行代码',8],['一条推文',30],
  ['小时人类高速打字',18000],['杯程序员续命美式',250000],['次完整阅读技术文档',45000],
  ['小时键盘持续敲击',12000],['个中型函数的代码量',1800]
];
function renderFunFacts(){
  const box=document.getElementById('funfacts'), t=lastTotal||0;
  if(t<=0){box.innerHTML='<div class="hint">无数据</div>';return;}
  let cands=FUN.map(([l,p])=>({l,p,n:t/p})).filter(x=>x.n>=0.3&&x.n<1e7).sort((a,b)=>b.n-a.n);
  for(let i=cands.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[cands[i],cands[j]]=[cands[j],cands[i]];}
  box.innerHTML=cands.slice(0,3).map(x=>{
    const num=x.n>=100?fmt(Math.round(x.n)):(x.n>=10?x.n.toFixed(1):x.n.toFixed(2));
    return '<div class=ff><span class=ff-n>'+num+'</span><span class=ff-l>'+x.l+'</span></div>';
  }).join('') || '<div class="hint">数据太少，肝得还不够</div>';
}
document.getElementById('fun-shuffle').addEventListener('click',renderFunFacts);

/* ---- 模块开关（附加功能可勾选 + 记忆）---- */
const MODS_KEY='tk-mods', MOD_DEFAULT={clock:true,fun:true,block:true,daily:true,rhythm:true,fortune:true,multiples:true,project:true,reuse:true,flow:true,creature:true,race:true,badges:true,dna:true,top:true};
function loadMods(){ try{ const m=Object.assign({},JSON.parse(localStorage.getItem(MODS_KEY)||'{}'));let legacy;if(Object.prototype.hasOwnProperty.call(m,'orbit'))legacy=m.orbit;else if(Object.prototype.hasOwnProperty.call(m,'city'))legacy=m.city;if(!Object.prototype.hasOwnProperty.call(m,'flow')&&legacy!==undefined)m.flow=legacy;delete m.orbit;delete m.city;localStorage.setItem(MODS_KEY,JSON.stringify(m));return m; }catch(e){ return {}; } }
function applyMods(){
  const m=Object.assign({},MOD_DEFAULT,loadMods());
  document.querySelectorAll('[data-module]').forEach(el=>{const hidden=m[el.dataset.module]===false;el.style.display=hidden?'none':'';if(!hidden&&el.dataset.lazy&&typeof lazyState!=='undefined'){const name=el.dataset.lazy;lazyState[name]=Object.assign({},lazyState[name],{dirty:true});if(lazyState[name].visible||!('IntersectionObserver'in window))renderLazy(name,true);}});
  document.querySelectorAll('[data-sw]').forEach(sw=>{
    const on=m[sw.dataset.sw]!==false; sw.classList.toggle('on',on);
    const cb=document.querySelector('input[data-mod="'+sw.dataset.sw+'"]'); if(cb) cb.checked=on;
  });
}
document.getElementById('mods-btn').addEventListener('click',e=>{e.stopPropagation();const pop=document.getElementById('mods-pop'),open=!pop.classList.contains('open');pop.classList.toggle('open',open);e.currentTarget.setAttribute('aria-expanded',String(open));if(open)setTimeout(()=>pop.querySelector('input')?.focus(),0);});
document.addEventListener('click',e=>{if(!e.target.closest('#mods-pop')&&!e.target.closest('#mods-btn')){document.getElementById('mods-pop').classList.remove('open');document.getElementById('mods-btn').setAttribute('aria-expanded','false');}});
document.querySelectorAll('#mods-pop input[data-mod]').forEach(cb=>{
  cb.addEventListener('change',()=>{const k=cb.dataset.mod,m=Object.assign({},MOD_DEFAULT,loadMods());m[k]=cb.checked;try{localStorage.setItem(MODS_KEY,JSON.stringify(m));}catch(e){}applyMods();});
});

/* ---- 5h 计费窗口 ---- */
function renderBlock(){
  const b=DATA.block||{total:0,buckets:[]}, bars=document.getElementById('block-bars');
  document.getElementById('block-total').textContent=human(b.total)+' tk';
  const bk=b.buckets||[], max=Math.max(1,...bk.map(x=>x.total));
  bars.innerHTML=bk.map(x=>'<div class=bb style="height:'+Math.max(3,x.total/max*100).toFixed(1)+'%" title="'+String(x.h).padStart(2,'0')+':00 · '+human(x.total)+' tk"><span>'+String(x.h).padStart(2,'0')+'</span></div>').join('');
  document.getElementById('block-now').textContent='近 6 个小时桶（按生成时刻往前）';
}

function recentCalendarDays(count=14){
  const periods=(DATA.day||[]).map(d=>d.period).filter(Boolean).sort(),fallback=periods[periods.length-1],end=DATA.range?.until||String(DATA.generated||'').slice(0,10)||fallback;
  if(!end)return [];
  const p=end.split('-').map(Number),last=new Date(p[0],p[1]-1,p[2]),byPeriod=Object.fromEntries((DATA.day||[]).map(d=>[d.period,d]));
  return Array.from({length:count},(_,i)=>{const d=new Date(last);d.setDate(last.getDate()-(count-1-i));const period=localISO(d);return byPeriod[period]||{period,total:0,calls:0,models:{},model_calls:{},synthetic:true};});
}

/* ---- 每天（近 14 天）迷你柱条 ---- */
function renderDaily(){
  const box=document.getElementById('daily-bars'), days=recentCalendarDays();
  if(!days.length){ box.innerHTML='<div class="hint" style="width:100%">无数据</div>'; document.getElementById('daily-total').textContent=''; return; }
  const max=Math.max(1,...days.map(d=>d.total)), tot=days.reduce((a,d)=>a+d.total,0);
  document.getElementById('daily-total').textContent=human(tot)+' tk · '+days.length+' 天';
  box.innerHTML=days.map(d=>{
    const h=Math.max(3,d.total/max*100), dd=(d.period||'').split('-')[2]||'?';
    return '<div class=bb style="height:'+h.toFixed(1)+'%" title="'+esc(d.period)+' · '+human(d.total)+' tk（'+d.calls+' 次）"><span>'+dd+'</span></div>';
  }).join('');
}

function showRhythmTip(cell,e){
  const tip=document.getElementById('rhythm-tip'), v=Number(cell.dataset.value||0), share=cell.dataset.share||'0.0', h=Number(cell.dataset.hour||0);
  const part=h<5?'深夜':h<9?'清晨':h<12?'上午':h<14?'午间':h<18?'下午':h<22?'夜晚':'深夜';
  tip.innerHTML='<b>'+esc(cell.dataset.day)+' · '+String(h).padStart(2,'0')+':00–'+String((h+1)%24).padStart(2,'0')+':00</b><div><span class="rh-v">'+fmt(v)+'</span> Token</div><span>'+part+'时段 · 占当天 '+share+'% · 点击回看这一天</span>';
  tip.classList.add('on'); moveRhythmTip(e);
}
function moveRhythmTip(e){
  const tip=document.getElementById('rhythm-tip'), gap=14, w=tip.offsetWidth||190, h=tip.offsetHeight||70;
  let x=e.clientX+gap,y=e.clientY+gap;if(x+w>innerWidth-8)x=e.clientX-w-gap;if(y+h>innerHeight-8)y=e.clientY-h-gap;
  tip.style.left=x+'px';tip.style.top=y+'px';
}
function hideRhythmTip(){document.getElementById('rhythm-tip').classList.remove('on');}

function rhythmLevel(value,positiveValues){
  if(!value)return 0;
  const min=Math.min(...positiveValues),max=Math.max(...positiveValues);
  if(max<=min)return 4;
  return Math.min(4,Math.max(1,Math.ceil((value-min)/(max-min)*4)));
}

function activateRhythmCell(cell){
  if(!DATA.day.some(d=>d.period===cell.dataset.day)){toast(cell.dataset.day+' 无 Token 记录');return;}
  state.gran='day';state.focusPeriod=cell.dataset.day;invalidateDerived();hideRhythmTip();renderDataViews();
}
function focusRhythmCell(cells,index){const next=Math.max(0,Math.min(cells.length-1,index));cells.forEach((cell,i)=>cell.tabIndex=i===next?0:-1);cells[next].focus();}

function renderRhythm(){
  const box=document.getElementById('rhythm'), days=recentCalendarDays(), det=DATA.day_details||{};
  if(!days.length){box.innerHTML='<div class="hint">无数据</div>';document.getElementById('rhythm-persona').textContent='';return;}
  const matrix=days.map(d=>{ const x=det[d.period], out=Array(24).fill(0); if(x) Object.entries(x.hourly_models||{}).forEach(([m,h])=>{if(state.models.has(m))h.forEach((v,i)=>out[i]+=v||0);}); return out; });
  const vals=matrix.flat().filter(v=>v>0);let html='<div class="rhythm-grid"><div></div>'+days.map(d=>'<div class="rh-day">'+esc((d.period||'').slice(5).replace('-','/'))+'</div>').join('');
  const dayTotals=matrix.map(a=>a.reduce((x,y)=>x+y,0));
  for(let h=0;h<24;h++){html+='<div class="rh-hour">'+(h%3===0?String(h).padStart(2,'0'):'')+'</div>';for(let d=0;d<days.length;d++){const v=matrix[d][h],lv=rhythmLevel(v,vals),share=dayTotals[d]?v/dayTotals[d]*100:0,index=h*days.length+d;html+='<div class="rh-cell l'+lv+'" role=gridcell tabindex="'+(index===0?'0':'-1')+'" data-index="'+index+'" data-day="'+esc(days[d].period)+'" data-hour="'+h+'" data-value="'+v+'" data-share="'+share.toFixed(1)+'" aria-label="'+esc(days[d].period)+' '+String(h).padStart(2,'0')+':00，'+fmt(v)+' token"></div>';}}
  box.innerHTML='<div class="rhythm-grid" role=grid aria-label="最近 14 天每小时 Token 作息织锦">'+html.slice('<div class="rhythm-grid">'.length)+'</div>';
  const cells=[...box.querySelectorAll('.rh-cell')];
  cells.forEach((c,index)=>{
    c.addEventListener('click',()=>activateRhythmCell(c));
    c.addEventListener('mouseenter',e=>showRhythmTip(c,e));
    c.addEventListener('mousemove',moveRhythmTip);
    c.addEventListener('mouseleave',hideRhythmTip);
    c.addEventListener('focus',()=>{const r=c.getBoundingClientRect();showRhythmTip(c,{clientX:r.left+r.width/2,clientY:r.top+r.height/2});});
    c.addEventListener('blur',hideRhythmTip);
    c.addEventListener('keydown',e=>{let next=null;if(e.key==='ArrowLeft')next=index-1;else if(e.key==='ArrowRight')next=index+1;else if(e.key==='ArrowUp')next=index-days.length;else if(e.key==='ArrowDown')next=index+days.length;else if(e.key==='Home')next=index-index%days.length;else if(e.key==='End')next=index+(days.length-1-index%days.length);else if(e.key==='Enter'||e.key===' '){e.preventDefault();activateRhythmCell(c);return;}if(next!==null){e.preventDefault();focusRhythmCell(cells,next);}});
  });
  const hs=Array(24).fill(0);matrix.forEach(a=>a.forEach((v,i)=>hs[i]+=v));const total=hs.reduce((a,b)=>a+b,0),sum=(a,b)=>hs.slice(a,b).reduce((x,y)=>x+y,0);
  let p=['☀️','日间稳定型','算力主要沿着白昼平稳展开。'];
  if(total&&sum(0,6)+sum(22,24)>total*.42)p=['🌙','午夜航行型','你的高密度思考更常发生在城市熄灯以后。'];
  else if(total&&sum(5,10)>total*.38)p=['🌅','晨光启动型','大部分算力在清晨苏醒，像一台提前预热的机器。'];
  else if(total&&sum(17,22)>total*.4)p=['🌆','黄昏冲刺型','越接近夜幕，Token 越开始加速。'];
  else if(hs.filter(v=>v>0).length>=20)p=['🌐','全时域高能体','一天几乎没有真正的静默区。'];
  document.getElementById('rhythm-persona').innerHTML=p[0]+' <b>'+p[1]+'</b> · '+p[2];
}

let selectedProject=null;
function projectPeriod(day,gran){
  if(gran==='day')return day;if(gran==='month')return day.slice(0,7)+'-01';
  const p=day.split('-').map(Number),d=new Date(p[0],p[1]-1,p[2]),offset=(d.getDay()+6)%7;d.setDate(d.getDate()-offset);return localISO(d);
}
function projectCatalog(){
  const fd=focusDays(),items={};
  Object.entries(DATA.day_details||{}).forEach(([day,detail])=>{if(fd&&!fd.has(day))return;(detail.cwds||detail.top_cwds||[]).forEach(row=>{const id=row[2]||row[0],item=items[id]||(items[id]={id,label:row[0],total:0});Object.entries(row[3]||{}).forEach(([m,v])=>{if(state.models.has(m))item.total+=v||0;});});});
  return Object.values(items).filter(x=>x.total>0).sort((a,b)=>b.total-a.total||a.label.localeCompare(b.label));
}
function projectRows(projectId){
  const fd=focusDays(),buckets={};
  Object.entries(DATA.day_details||{}).forEach(([day,detail])=>{if(fd&&!fd.has(day))return;const row=(detail.cwds||detail.top_cwds||[]).find(x=>(x[2]||x[0])===projectId);if(!row)return;const period=projectPeriod(day,state.gran),item=buckets[period]||(buckets[period]={period,total:0,models:{}});Object.entries(row[3]||{}).forEach(([m,v])=>{if(state.models.has(m)&&v){item.models[m]=(item.models[m]||0)+v;item.total+=v;}});});
  return Object.values(buckets).filter(x=>x.total>0).sort((a,b)=>a.period.localeCompare(b.period));
}
function renderProjectLens(){
  const select=document.getElementById('project-select'),catalog=projectCatalog();
  if(!catalog.length){selectedProject=null;select.innerHTML='<option>当前筛选下无项目</option>';select.disabled=true;document.getElementById('project-kpis').innerHTML='';document.getElementById('project-chart').innerHTML='<text x="540" y="140" text-anchor="middle" class="reuse-label">当前筛选下没有项目数据</text>';document.getElementById('project-panel').textContent='选择包含 cwd 的来源和模型后生成项目透镜。';document.getElementById('project-thead').innerHTML='';document.getElementById('project-tbody').innerHTML='';return;}
  select.disabled=false;if(!selectedProject||!catalog.some(x=>x.id===selectedProject))selectedProject=catalog[0].id;
  select.innerHTML=catalog.map(x=>'<option value="'+esc(x.id)+'"'+(x.id===selectedProject?' selected':'')+'>'+esc(x.label)+' · '+human(x.total)+'</option>').join('');
  const chosen=catalog.find(x=>x.id===selectedProject),rows=projectRows(selectedProject),total=rows.reduce((a,r)=>a+r.total,0),overall=selectedRows().reduce((a,r)=>a+r.total,0),peak=rows.reduce((a,r)=>!a||r.total>a.total?r:a,null),mt={};rows.forEach(r=>Object.entries(r.models).forEach(([m,v])=>mt[m]=(mt[m]||0)+v));const dom=Object.entries(mt).sort((a,b)=>b[1]-a[1])[0];
  document.getElementById('project-kpis').innerHTML=[['项目 Token',human(total)],['当前占比',pct(total,overall)],['活跃期',rows.length],['峰值期',peak?fmtLabel(peak.period,state.gran):'—'],['主力模型',dom?pretty(dom[0]):'—']].map(x=>'<div><b>'+esc(x[1])+'</b>'+x[0]+'</div>').join('');
  const svg=document.getElementById('project-chart'),W=1080,H=280,pad=38,plotH=190,max=Math.max(1,...rows.map(r=>r.total)),step=(W-pad*2)/Math.max(1,rows.length),parts=[];for(let g=0;g<=3;g++){const y=24+plotH*g/3;parts.push('<line class="project-grid" x1="'+pad+'" y1="'+y+'" x2="'+(W-pad)+'" y2="'+y+'"/>');}
  rows.forEach((r,i)=>{const x=pad+i*step+step*.16,w=Math.max(3,step*.68);let y=24+plotH;Object.entries(r.models).sort((a,b)=>b[1]-a[1]).forEach(([m,v])=>{const h=v/max*plotH;y-=h;parts.push('<rect class="project-bar" x="'+x.toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+w.toFixed(1)+'" height="'+Math.max(.5,h).toFixed(1)+'" fill="'+DATA.colors[m]+'"><title>'+esc(pretty(m))+' · '+fmt(v)+' Token</title></rect>');});parts.push('<rect class="project-hit" data-i="'+i+'" tabindex="'+(i===rows.length-1?'0':'-1')+'" role="button" aria-label="'+esc(fmtLabel(r.period,state.gran))+'，'+fmt(r.total)+' Token" x="'+(pad+i*step).toFixed(1)+'" y="20" width="'+step.toFixed(1)+'" height="'+(plotH+12)+'"/>');if(rows.length<=16||i%Math.ceil(rows.length/12)===0)parts.push('<text class="reuse-label" x="'+(x+w/2).toFixed(1)+'" y="242" text-anchor="middle">'+esc(fmtLabel(r.period,state.gran))+'</text>');});svg.innerHTML=parts.join('');
  const panel=document.getElementById('project-panel'),hits=[...svg.querySelectorAll('.project-hit')],inspect=i=>{const r=rows[i];if(!r)return;hits.forEach((h,j)=>h.tabIndex=j===i?0:-1);const mix=Object.entries(r.models).sort((a,b)=>b[1]-a[1]).map(([m,v])=>pretty(m)+' '+human(v)).join(' · ');panel.textContent=fmtLabel(r.period,state.gran)+' · '+human(r.total)+' tk'+(mix?' · '+mix:'');};hits.forEach((hit,i)=>{hit.addEventListener('pointerenter',()=>inspect(i));hit.addEventListener('focus',()=>inspect(i));hit.addEventListener('click',()=>inspect(i));hit.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();const n=Math.max(0,Math.min(hits.length-1,i+(e.key==='ArrowRight'?1:-1)));inspect(n);hits[n].focus();}});});if(rows.length)inspect(rows.length-1);
  const models=DATA.models.filter(m=>rows.some(r=>r.models[m]));document.getElementById('project-thead').innerHTML='<tr><th>'+LABEL[state.gran]+'</th><th class=num>总 Token</th>'+models.map(m=>'<th class=num>'+esc(pretty(m))+'</th>').join('')+'</tr>';document.getElementById('project-tbody').innerHTML=rows.map(r=>'<tr><td>'+esc(fmtLabel(r.period,state.gran))+'</td><td class=num>'+fmt(r.total)+'</td>'+models.map(m=>'<td class=num>'+fmt(r.models[m]||0)+'</td>').join('')+'</tr>').join('');
  select.title=chosen?chosen.id:'';
}
document.getElementById('project-select').addEventListener('change',e=>{selectedProject=e.target.value;renderProjectLens();});

function modelHover(model,on){
  document.querySelectorAll('[data-model]').forEach(el=>{const same=el.dataset.model===model;el.classList.toggle('model-hot',on&&same);el.classList.toggle('model-dim',on&&!same);});
}
function bindModelLinks(){
  if(document.body.dataset.modelDelegated)return;document.body.dataset.modelDelegated='1';
  document.addEventListener('pointerover',e=>{const el=e.target.closest('[data-model]');if(el)modelHover(el.dataset.model,true);});
  document.addEventListener('pointerout',e=>{const el=e.target.closest('[data-model]');if(el&&!el.contains(e.relatedTarget))modelHover(el.dataset.model,false);});
}

function currentFlow(){
  if(!state.focusPeriod)return DATA.flow||{project_model:[],model_session:[]};
  const fd=focusDays(),pm={},ms={};
  (fd||[]).forEach(day=>{const f=DATA.day_details[day]?.flow;if(!f)return;(f.project_model||[]).forEach(x=>{const k=x[1]+'::'+x[2],v=pm[k]||[x[0],x[1],x[2],0];v[3]+=x[3]||0;pm[k]=v;});(f.model_session||[]).forEach(x=>{const k=x[0]+'::'+x[2],v=ms[k]||[x[0],x[1],x[2],0];v[3]+=x[3]||0;ms[k]=v;});});
  return {project_model:Object.values(pm),model_session:Object.values(ms)};
}
let flowLocked=null;
function selectedReuseRows(){
  const rows=(DATA.reuse||{})[state.gran]||[];
  return rows.map(([period,byModel])=>{const parts=[0,0,0,0,0];Object.entries(byModel||{}).forEach(([m,v])=>{if(state.models.has(m))v.forEach((n,i)=>parts[i]+=n||0);});return [period,...parts];});
}
function renderReuseRiver(){
  const rows=selectedReuseRows(),svg=document.getElementById('reuse-chart'),panel=document.getElementById('reuse-panel'),selectedTotal=rows.reduce((a,r)=>a+r.slice(1).reduce((x,y)=>x+(y||0),0),0);
  if(!rows.length||!selectedTotal){svg.innerHTML='<text x="540" y="150" text-anchor="middle" class="reuse-label">当前模型筛选下暂无 Token 构成</text>';document.getElementById('reuse-summary').textContent='0 Token';panel.textContent='选择至少一个有数据的模型后生成复用之河。';return;}
  let data=state.focusPeriod?rows.filter(r=>r[0]===state.focusPeriod):rows;if(data.length===1)data=[data[0],data[0]];
  const W=1080,H=300,pad=34,plotW=W-pad*2,plotH=H-60,series=[1,2,3,4,5],colors=['#5b8def','#f472b6','#14b8a6','#a78bfa','#94a3b8'],labels=['Fresh Input','Output','Cache Read','Cache Write','Other'];
  const totals=data.map(r=>series.reduce((a,i)=>a+(r[i]||0),0)),max=Math.max(1,...totals),step=plotW/Math.max(1,data.length-1);let lower=Array(data.length).fill(0),parts=['<defs>'];colors.forEach((c,i)=>parts.push('<linearGradient id="reuse-g-'+i+'" x1="0" y1="0" x2="0" y2="1"><stop stop-color="'+c+'" stop-opacity=".72"/><stop offset="1" stop-color="'+c+'" stop-opacity=".16"/></linearGradient>'));parts.push('</defs>');
  for(let g=0;g<=3;g++){const y=24+plotH*g/3;parts.push('<line class="reuse-grid" x1="'+pad+'" y1="'+y+'" x2="'+(W-pad)+'" y2="'+y+'"/>');}
  series.forEach((idx,si)=>{const upper=data.map((r,i)=>lower[i]+(r[idx]||0)),top=upper.map((v,i)=>(pad+i*step).toFixed(1)+','+(24+plotH-v/max*plotH).toFixed(1)),bottom=lower.map((v,i)=>(pad+i*step).toFixed(1)+','+(24+plotH-v/max*plotH).toFixed(1)).reverse(),d='M'+top.join(' L')+' L'+bottom.join(' L')+' Z';parts.push('<path class="reuse-area" d="'+d+'" fill="url(#reuse-g-'+si+')" opacity=".86"><title>'+labels[si]+'</title></path>');lower=upper;});
  const original=state.focusPeriod?rows.filter(r=>r[0]===state.focusPeriod):rows,hitW=plotW/Math.max(1,original.length);original.forEach((r,i)=>parts.push('<rect class="reuse-hit" data-i="'+i+'" tabindex="'+(i===original.length-1?'0':'-1')+'" role="button" aria-label="'+esc(fmtLabel(r[0],state.gran))+' Token 构成" x="'+(pad+i*hitW).toFixed(1)+'" y="20" width="'+Math.max(.5,hitW).toFixed(1)+'" height="'+(plotH+12)+'"/>'));
  parts.push('<line class="reuse-cursor" id="reuse-cursor" x1="-1" y1="20" x2="-1" y2="'+(24+plotH)+'"/>');svg.innerHTML=parts.join('');
  const totalAll=original.reduce((a,r)=>a+series.reduce((s,i)=>s+(r[i]||0),0),0),cacheAll=original.reduce((a,r)=>a+(r[3]||0),0);document.getElementById('reuse-summary').textContent='缓存复用 '+pct(cacheAll,totalAll);
  const hits=[...svg.querySelectorAll('.reuse-hit')],pointStep=plotW/Math.max(1,original.length-1),inspect=i=>{const r=original[i];if(!r)return;hits.forEach((h,j)=>h.setAttribute('tabindex',j===i?'0':'-1'));const x=original.length===1?pad+plotW/2:pad+i*pointStep,c=document.getElementById('reuse-cursor');c.setAttribute('x1',x);c.setAttribute('x2',x);panel.textContent=fmtLabel(r[0],state.gran)+' · Fresh '+human(r[1])+' · Output '+human(r[2])+' · Read '+human(r[3])+' · Write '+human(r[4])+' · Other '+human(r[5]);};
  hits.forEach((hit,i)=>{hit.addEventListener('pointerenter',()=>inspect(i));hit.addEventListener('click',()=>inspect(i));hit.addEventListener('focus',()=>inspect(i));hit.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();const next=Math.max(0,Math.min(hits.length-1,i+(e.key==='ArrowRight'?1:-1)));inspect(next);hits[next].focus();}});});if(original.length)inspect(original.length-1);
}


function renderFlow(){
  const svg=document.getElementById('flow-map'),raw=currentFlow(),selectedTotal=selectedRows().reduce((a,r)=>a+r.total,0);
  const pm=(raw.project_model||[]).filter(x=>state.models.has(x[2])&&x[3]>0),ms=(raw.model_session||[]).filter(x=>state.models.has(x[0])&&x[3]>0);
  const sumBy=(arr,key,val)=>{const o={};arr.forEach(x=>o[x[key]]=(o[x[key]]||0)+(x[val]||0));return o;};
  const pmModels=sumBy(pm,2,3),msModels=sumBy(ms,0,3),allModels=new Set([...Object.keys(pmModels),...Object.keys(msModels)]),mt={};allModels.forEach(m=>mt[m]=Math.max(pmModels[m]||0,msModels[m]||0));
  const modelIds=Object.keys(mt).filter(m=>state.models.has(m)).sort((a,b)=>(mt[b]||0)-(mt[a]||0)).slice(0,7),modelSet=new Set(modelIds),modelPM=pm.filter(x=>modelSet.has(x[2])),modelMS=ms.filter(x=>modelSet.has(x[0])),pt=sumBy(modelPM,1,3),st=sumBy(modelMS,2,3);
  const projectIds=Object.keys(pt).sort((a,b)=>pt[b]-pt[a]).slice(0,7),sessionIds=Object.keys(st).sort((a,b)=>st[b]-st[a]).slice(0,8),projectSet=new Set(projectIds),sessionSet=new Set(sessionIds),linksPM=modelPM.filter(x=>projectSet.has(x[1])),linksMS=modelMS.filter(x=>sessionSet.has(x[2]));
  if(!linksPM.length&&!linksMS.length){svg.innerHTML='<text x="560" y="220" text-anchor="middle" class="flow-col">暂无所选模型的流向数据</text>';document.getElementById('flow-stats').innerHTML='<span>0 条流光链路</span>';showFlowPanel(null);return;}
  const W=1120,H=470,xpos={project:130,model:560,session:990},layout=(ids,totals,type)=>{const gap=(H-90)/Math.max(1,ids.length),out={};ids.forEach((id,i)=>out[id]={x:xpos[type],y:55+gap*(i+.5),total:totals[id]||0});return out;},P=layout(projectIds,pt,'project'),M=layout(modelIds,mt,'model'),S=layout(sessionIds,st,'session'),maxLink=Math.max(1,...linksPM.map(x=>x[3]),...linksMS.map(x=>x[3]));
  const sessionLabels={};ms.forEach(x=>sessionLabels[x[2]]=x[1]);const projectLabels={};pm.forEach(x=>projectLabels[x[1]]=x[0]);
  let p=['<defs>'];modelIds.forEach((m,i)=>{const c=DATA.colors[m]||'#7aa2f7';p.push('<linearGradient id="flow-g-'+i+'" x1="0" x2="1"><stop stop-color="'+c+'" stop-opacity=".25"/><stop offset=".5" stop-color="'+c+'"/><stop offset="1" stop-color="'+c+'" stop-opacity=".35"/></linearGradient>');});p.push('</defs><text class="flow-col" x="55" y="28">PROJECT</text><text class="flow-col" x="520" y="28">MODEL</text><text class="flow-col" x="942" y="28">SESSION</text>');
  const path=(a,b)=>'M '+a.x+' '+a.y+' C '+(a.x+150)+' '+a.y+' '+(b.x-150)+' '+b.y+' '+b.x+' '+b.y;
  linksPM.forEach(x=>{const mi=modelIds.indexOf(x[2]),w=2+Math.sqrt(x[3]/maxLink)*17;p.push('<path class="flow-link motion" data-flow-from="project:'+esc(x[1])+'" data-flow-model="'+esc(x[2])+'" d="'+path(P[x[1]],M[x[2]])+'" stroke="url(#flow-g-'+mi+')" stroke-width="'+w.toFixed(1)+'"><title>'+esc(x[0])+' → '+esc(pretty(x[2]))+' · '+fmt(x[3])+' Token</title></path>');});
  linksMS.forEach(x=>{const mi=modelIds.indexOf(x[0]),w=2+Math.sqrt(x[3]/maxLink)*17;p.push('<path class="flow-link motion" data-flow-model="'+esc(x[0])+'" data-flow-to="session:'+esc(x[2])+'" d="'+path(M[x[0]],S[x[2]])+'" stroke="url(#flow-g-'+mi+')" stroke-width="'+w.toFixed(1)+'"><title>'+esc(pretty(x[0]))+' → '+esc(x[1])+' · '+fmt(x[3])+' Token</title></path>');});
  const node=(type,id,pos,label,total,color)=>{const share=Math.min(100,selectedTotal?total/selectedTotal*100:0),boxX=pos.x-80,boxY=pos.y-20,canLock=type!=='session';return '<g class="flow-node '+type+'" data-flow-type="'+type+'" data-flow-id="'+esc(id)+'" data-flow-name="'+esc(label)+'" data-flow-total="'+total+'" data-flow-share="'+share.toFixed(2)+'" tabindex="0" role="button" aria-label="'+(type==='project'?'项目 ':type==='model'?'模型 ':'会话 ')+esc(label)+'，'+fmt(total)+' Token，占比 '+share.toFixed(1)+'%"><rect class="flow-hit" x="'+(boxX-6)+'" y="'+(boxY-4)+'" width="172" height="48" rx="12"/><rect class="flow-box" x="'+boxX+'" y="'+boxY+'" width="160" height="40" rx="10" fill="'+color+'" fill-opacity=".22"/><text x="'+pos.x+'" y="'+(pos.y-2)+'" text-anchor="middle">'+esc(label.length>20?label.slice(0,19)+'…':label)+'</text><text class="flow-value" x="'+pos.x+'" y="'+(pos.y+13)+'" text-anchor="middle">'+human(total)+' tk</text><title>'+(canLock?'点击锁定链路':'点击回放会话')+'</title></g>';};
  projectIds.forEach((id,i)=>p.push(node('project',id,P[id],projectLabels[id]||id,pt[id],['#5b8def','#14b8a6','#a78bfa','#38bdf8'][i%4])));modelIds.forEach(m=>p.push(node('model',m,M[m],pretty(m),mt[m],DATA.colors[m]||'#7aa2f7')));sessionIds.forEach((id,i)=>p.push(node('session',id,S[id],sessionLabels[id]||id,st[id],['#f472b6','#f59e0b','#a78bfa','#38bdf8'][i%4])));
  svg.innerHTML=p.join('');document.getElementById('flow-stats').innerHTML='<span>'+projectIds.length+' 个项目</span><span>'+modelIds.length+' 个模型</span><span>'+sessionIds.length+' 个会话</span><span>'+(linksPM.length+linksMS.length)+' 条真实流向</span>';
  const nodes=[...svg.querySelectorAll('.flow-node')],links=[...svg.querySelectorAll('.flow-link')],keyFor=n=>n.dataset.flowType+':'+n.dataset.flowId,dataFor=n=>({type:n.dataset.flowType,id:n.dataset.flowId,name:n.dataset.flowName,total:Number(n.dataset.flowTotal),share:Number(n.dataset.flowShare)});
  const illuminate=n=>{const key=keyFor(n),type=n.dataset.flowType,id=n.dataset.flowId,models=new Set();if(type==='model')models.add(id);if(type==='project')links.filter(l=>l.dataset.flowFrom===key).forEach(l=>models.add(l.dataset.flowModel));if(type==='session')links.filter(l=>l.dataset.flowTo===key).forEach(l=>models.add(l.dataset.flowModel));links.forEach(l=>{const hot=type==='model'?l.dataset.flowModel===id:type==='project'?(l.dataset.flowFrom===key||models.has(l.dataset.flowModel)):type==='session'?(l.dataset.flowTo===key||models.has(l.dataset.flowModel)):false;l.classList.toggle('hot',hot);l.classList.toggle('dim',!hot);});const active=new Set([key]);links.filter(l=>l.classList.contains('hot')).forEach(l=>{if(l.dataset.flowFrom)active.add(l.dataset.flowFrom);if(l.dataset.flowTo)active.add(l.dataset.flowTo);if(l.dataset.flowModel)active.add('model:'+l.dataset.flowModel);});nodes.forEach(x=>x.classList.toggle('dim',!active.has(keyFor(x))));};
  const clear=()=>{links.forEach(l=>l.classList.remove('hot','dim'));nodes.forEach(n=>n.classList.remove('dim'));};
  nodes.forEach(n=>{n.addEventListener('mouseenter',()=>{illuminate(n);showFlowPanel(dataFor(n));});n.addEventListener('focus',()=>{illuminate(n);showFlowPanel(dataFor(n));});n.addEventListener('mouseleave',()=>{if(!flowLocked){clear();showFlowPanel(null);}});n.addEventListener('blur',()=>{if(!flowLocked){clear();showFlowPanel(null);}});const activate=()=>{const d=dataFor(n);if(d.type==='session'){openReplay(d.id,d.name);return;}const k=keyFor(n);flowLocked=flowLocked===k?null:k;nodes.forEach(x=>x.classList.toggle('locked',keyFor(x)===flowLocked));if(flowLocked){illuminate(n);showFlowPanel(d,true);}else{clear();showFlowPanel(null);}};n.addEventListener('click',activate);n.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate();}});});
  if(flowLocked){const locked=nodes.find(n=>keyFor(n)===flowLocked);if(locked){locked.classList.add('locked');illuminate(locked);showFlowPanel(dataFor(locked),true);}else flowLocked=null;}else showFlowPanel(null);
}
function showFlowPanel(d,locked=false){const panel=document.getElementById('flow-panel');if(!d){panel.innerHTML='<b>Token 流光图</b><span>① 悬停追踪链路　② 点击项目或模型锁定　③ 点击会话回放</span>';return;}const type=d.type==='project'?'项目':d.type==='model'?'模型':'会话';panel.innerHTML='<b>'+type+' · '+esc(d.name)+'</b><span>'+fmt(d.total)+' Token · 占当前筛选总量 '+d.share.toFixed(1)+'%'+(locked?' · 已锁定，再点取消':d.type==='session'?' · 点击回放':' · 点击锁定链路')+'</span>';}
function saveFlowSVG(){const source=document.getElementById('flow-map');if(!source.querySelector('.flow-node')){toast('当前筛选没有可导出的流向');return;}const svg=source.cloneNode(true);svg.setAttribute('xmlns','http://www.w3.org/2000/svg');svg.setAttribute('width','1120');svg.setAttribute('height','470');const bg=document.createElementNS('http://www.w3.org/2000/svg','rect');bg.setAttribute('width','1120');bg.setAttribute('height','470');bg.setAttribute('fill','#0b1120');svg.insertBefore(bg,svg.firstChild);const style=document.createElementNS('http://www.w3.org/2000/svg','style');style.textContent='.flow-col{fill:#8fa3c0;font:800 10px sans-serif;letter-spacing:.14em}.flow-link{fill:none;stroke-linecap:round;opacity:.58}.flow-box{stroke:rgba(255,255,255,.7);stroke-width:1}.flow-node text{fill:#e1ecfb;font:700 10px sans-serif}.flow-node .flow-value{fill:#9badc7;font:600 8.5px sans-serif}.flow-hit{display:none}';svg.insertBefore(style,bg.nextSibling);const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['<?xml version="1.0"?>\n'+svg.outerHTML],{type:'image/svg+xml'}));a.download='token-flow-'+state.gran+(state.focusPeriod?'-'+state.focusPeriod:'')+'.svg';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);toast('当前流光图已保存为 SVG');}
document.getElementById('flow-save').addEventListener('click',saveFlowSVG);

function renderCreature(){
  const svg=document.getElementById('creature'),days=DATA.day||[],total=days.reduce((a,d)=>a+d.total,0),h=DATA.hourly||[],ht=h.reduce((a,b)=>a+b,0),night=(h.slice(0,6).reduce((a,b)=>a+b,0)+h.slice(22).reduce((a,b)=>a+b,0))/(ht||1);
  const cr=DATA.cache_read||0,cache=total?cr/total:0,models=Math.max(1,DATA.models.length),projects=Math.max(1,DATA.n_cwds||1),streak=Math.min(40,days.length),stage=total>=1e9?5:total>=1e8?4:total>=1e7?3:total>=1e6?2:1;
  const names=['微光幼体','上下文游鱼','缓存水母','算力星灵','Token 远古体'],prefix=night>.42?'午夜':cache>.7?'晶核':models>=5?'虹彩':projects>=20?'漫游':'静默';
  const size=48+stage*8, tent=3+Math.min(7,models), spots=Math.min(18,Math.ceil(projects/2)), hue=(total%240)+80;
  let p=['<defs><radialGradient id="cg" cx="38%" cy="30%"><stop offset="0" stop-color="hsl('+hue+' 90% 82%)"/><stop offset=".55" stop-color="hsl('+hue+' 76% 61%)"/><stop offset="1" stop-color="hsl('+(hue+45)+' 70% 38%)"/></radialGradient><filter id="gl"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>'];
  p.push('<ellipse cx="130" cy="223" rx="'+(36+stage*4)+'" ry="7" fill="rgba(0,0,0,.16)"/>');
  for(let i=0;i<tent;i++){const x=92+i*(76/Math.max(1,tent-1)),len=25+((i*13+total)%25);p.push('<path d="M '+x+' 169 Q '+(x-12+(i%3)*10)+' '+(190+len/3)+' '+(x+(i%2?8:-8))+' '+(180+len)+'" fill="none" stroke="hsl('+(hue+i*8)+' 72% 58%)" stroke-width="'+(4+(i%3))+'" stroke-linecap="round" opacity=".65"/>');}
  p.push('<path d="M '+(130-size)+' 145 Q '+(130-size+4)+' '+(80-stage*3)+' 130 '+(71-stage*4)+' Q '+(130+size-4)+' '+(80-stage*3)+' '+(130+size)+' 145 Q '+(130+size-5)+' 174 130 178 Q '+(130-size+5)+' 174 '+(130-size)+' 145Z" fill="url(#cg)" stroke="rgba(255,255,255,.5)" stroke-width="1.5" filter="url(#gl)"/>');
  for(let i=0;i<spots;i++){const a=(i*2.399)+(total%11),r=size*.62*Math.sqrt((i+1)/(spots+1)),x=130+Math.cos(a)*r,y=126+Math.sin(a)*r*.55;p.push('<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+(1.8+(i%3))+'" fill="rgba(255,255,255,'+(cache*.55+.18).toFixed(2)+')"/>');}
  const eyeY=132,eyeGap=18+stage*2;p.push('<g class="creature-eye"><ellipse cx="'+(130-eyeGap)+'" cy="'+eyeY+'" rx="7" ry="'+(night>.4?9:7)+'" fill="#111827"/><circle cx="'+(128-eyeGap)+'" cy="'+(eyeY-2)+'" r="2" fill="white"/><ellipse cx="'+(130+eyeGap)+'" cy="'+eyeY+'" rx="7" ry="'+(night>.4?9:7)+'" fill="#111827"/><circle cx="'+(128+eyeGap)+'" cy="'+(eyeY-2)+'" r="2" fill="white"/></g>');
  p.push('<path d="M 119 153 Q 130 '+(158+stage)+' 141 153" fill="none" stroke="rgba(17,24,39,.75)" stroke-width="2.3" stroke-linecap="round"/>');
  if(cache>.65)p.push('<path d="M 104 105 Q 130 75 156 105" fill="none" stroke="rgba(255,255,255,.72)" stroke-width="3" stroke-linecap="round"/><circle cx="130" cy="86" r="6" fill="hsl('+(hue+90)+' 90% 73%)" filter="url(#gl)"/>');
  svg.innerHTML=p.join('');document.getElementById('creature-name').textContent=prefix+'·'+names[stage-1];document.getElementById('creature-desc').textContent='由总量、模型、项目、缓存与作息共同塑形 · 每份数据只会诞生这一只';
  document.getElementById('creature-info').innerHTML='<div><b>形态 '+stage+'/5</b>进化阶段</div><div><b>'+tent+' 条</b>模型触须</div><div><b>'+spots+' 枚</b>项目星斑</div><div><b>'+Math.round(cache*100)+'%</b>晶核纯度</div><div><b>'+Math.round(night*100)+'%</b>夜行倾向</div><div><b>'+streak+'</b>生命年轮</div>';
}
document.getElementById('creature-save').addEventListener('click',()=>{const s=document.getElementById('creature').cloneNode(true);s.setAttribute('xmlns','http://www.w3.org/2000/svg');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([s.outerHTML],{type:'image/svg+xml'}));a.download='token-creature.svg';a.click();toast('Token 生物已保存');});

/* ---- 每模型迷你趋势（small multiples）---- */
function renderMultiples(){
  const box=document.getElementById('multiples'), days=DATA.day||[];
  if(!days.length||!DATA.models.length){ box.innerHTML='<div class="hint">无数据</div>'; return; }
  box.innerHTML=DATA.models.map(m=>{
    const s=days.map(d=>d.models[m]||0), total=s.reduce((a,b)=>a+b,0), max=Math.max(1,...s), W=120,H=32,c=DATA.colors[m];
    let path=''; s.forEach((v,i)=>{ const x=i/Math.max(1,s.length-1)*W, y=H-3-(v/max)*(H-6); path+=(i?'L':'M')+x.toFixed(1)+' '+y.toFixed(1)+' '; });
    const area=path+'L '+W+' '+H+' L 0 '+H+' Z';
    return '<div class=mp data-model="'+esc(m)+'"><div class=nm><i style="background:'+c+'"></i>'+esc(pretty(m))+'</div><div class=vt>'+human(total)+'</div>'
      +'<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none"><path d="'+area+'" fill="'+c+'" fill-opacity="0.16"/><path d="'+path+'" fill="none" stroke="'+c+'" stroke-width="1.5" stroke-linejoin="round"/></svg></div>';
  }).join('');
}

/* ---- 柱图竞赛（累计 token 随日演变）---- */
let raceTimer=null, raceIdx=0;
function raceData(){
  const days=DATA.day||[], cum={}, out=[];
  days.forEach(d=>{ Object.keys(d.models).forEach(m=>cum[m]=(cum[m]||0)+d.models[m]); out.push({day:d.period,cum:Object.assign({},cum)}); });
  return out;
}
function renderRace(){
  const data=raceData(), box=document.getElementById('race');
  if(data.length<2){ box.innerHTML='<div class="hint">数据不足</div>'; document.getElementById('race-day').textContent='';const scrub=document.getElementById('race-scrub');scrub.disabled=true;scrub.max='0';scrub.value='0';scrub.removeAttribute('aria-valuetext'); return; }
  document.getElementById('race-scrub').disabled=false;
  raceIdx=Math.min(raceIdx,data.length-1);
  const cur=data[raceIdx], entries=Object.entries(cur.cum).sort((a,b)=>b[1]-a[1]).slice(0,6), max=Math.max(1,...entries.map(e=>e[1]));
  box.innerHTML=entries.map(([m,v])=>{
    const w=v/max*100;
    return '<div class=race-row><span class=race-name><i style="background:'+DATA.colors[m]+'"></i>'+esc(pretty(m))+'</span>'
      +'<span class=race-bar><i style="width:'+w.toFixed(1)+'%;background:'+DATA.colors[m]+'"></i></span><span class=race-val>'+human(v)+'</span></div>';
  }).join('');
  document.getElementById('race-day').textContent='截至 '+fmtLabel(cur.day,'day');
  document.getElementById('race-pos').textContent=(raceIdx+1)+'/'+data.length;
  const scrub=document.getElementById('race-scrub');scrub.max=String(data.length-1);scrub.value=String(raceIdx);scrub.setAttribute('aria-valuetext','截至 '+fmtLabel(cur.day,'day')+'，第 '+(raceIdx+1)+' / '+data.length+' 期');
}
document.getElementById('race-scrub').addEventListener('input',e=>{if(raceTimer){clearInterval(raceTimer);raceTimer=null;document.getElementById('race-play').textContent='▶ 播放';}raceIdx=Number(e.target.value||0);renderRace();});

document.getElementById('race-play').addEventListener('click',function(){
  const data=raceData();
  if(raceTimer){ clearInterval(raceTimer); raceTimer=null; this.textContent='▶ 播放'; return; }
  if(data.length<2) return;
  raceIdx=0; renderRace(); this.textContent='⏸ 暂停';
  raceTimer=setInterval(()=>{ raceIdx++; if(raceIdx>=data.length){ clearInterval(raceTimer); raceTimer=null; this.textContent='▶ 播放'; raceIdx=data.length-1; } renderRace(); },700);
});

function dataCommands(){
  const days=DATA.day||[],top=[...days].sort((a,b)=>b.total-a.total)[0],h=DATA.hourly||[],peak=h.indexOf(Math.max(...h)),mt={};days.forEach(d=>Object.entries(d.models||{}).forEach(([m,v])=>mt[m]=(mt[m]||0)+v));
  const out=[];if(top)out.push({ic:'🔍',t:'最高 Token 日 · '+top.period+' · '+human(top.total),k:'数据',run:()=>{setGran('day');setTimeout(()=>toggleFocus(top.period),30);}});if(peak>=0)out.push({ic:'🌙',t:'最活跃时刻 · '+String(peak).padStart(2,'0')+':00 · '+human(h[peak]),k:'数据',run:()=>document.querySelector('[data-module=clock]').scrollIntoView({behavior:scrollBehavior()})});Object.entries(mt).sort((a,b)=>b[1]-a[1]).forEach(([m,v])=>out.push({ic:'🤖',t:pretty(m)+' · '+human(v)+' · '+(v/Object.values(mt).reduce((a,b)=>a+b,0)*100).toFixed(1)+'%',k:'模型',run:()=>setModels([m],'Solo · '+pretty(m))}));return out;
}
function secretCommand(q){
  q=q.trim().toLowerCase();
  const secrets={
    'whoami':()=>{const x=shareStats();toast((x.peak<6||x.peak>=22?'午夜航行型':'日光构筑型')+'开发者 · '+x.dom+' · '+Math.round(x.cache*100)+'% 缓存',4200);},
    '42':()=>toast('宇宙终极答案是 42，但你的答案是 '+human(lastTotal)+' Token。',4200),
    'coffee':()=>toast('你的 Token 大约够续命 '+fmt(Math.round(lastTotal/250000))+' 杯程序员美式 ☕',4200),
    'sudo':()=>toast('权限不足：算力宇宙拒绝 root 接管。'),
    'rm -rf':()=>toast('操作已拦截。你的 '+fmt((_ach||getBadgeData()).got)+' 枚成就松了一口气。',4200),
    'matrix':()=>{document.body.style.filter='hue-rotate(75deg) saturate(1.5)';toast('Wake up, developer…');setTimeout(()=>document.body.style.filter='',2600);},
    'midnight':()=>{const h=DATA.hourly||[];toast('深夜共留下 '+human(h.slice(0,6).reduce((a,b)=>a+b,0)+h.slice(22).reduce((a,b)=>a+b,0))+' Token。',4200);},
    'receipt':()=>openShare('receipt'),'passport':()=>openShare('passport'),'flow':()=>scrollToSection('section-flow'),'orbit':()=>scrollToSection('section-flow'),'city':()=>scrollToSection('section-flow'),'creature':()=>document.querySelector('[data-module=creature]').scrollIntoView({behavior:scrollBehavior()})
  };if(secrets[q]){closePalette();setTimeout(secrets[q],80);return true;}return false;
}

function scrollToSection(id){const el=document.getElementById(id);if(!el)return;const lazy=el.dataset.lazy;if(lazy){lazyState[lazy]=Object.assign({},lazyState[lazy],{visible:true});renderLazy(lazy,true);}el.scrollIntoView({behavior:scrollBehavior(),block:'start'});}
const SECTION_LINKS=[['section-overview','总览'],['section-trend','趋势'],['section-project','项目'],['section-rhythm','节奏'],['section-reuse','复用'],['section-flow','流光'],['section-achievements','成就'],['section-top','Top']];
function initSectionDock(){
  const dock=document.getElementById('section-dock');dock.addEventListener('click',e=>{const b=e.target.closest('button[data-target]');if(b)scrollToSection(b.dataset.target);});
  const mark=id=>dock.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.target===id));
  if('IntersectionObserver'in window){const obs=new IntersectionObserver(entries=>{const hit=entries.filter(x=>x.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio)[0];if(hit)mark(hit.target.id);},{rootMargin:'-18% 0px -65% 0px',threshold:[0,.15,.4]});SECTION_LINKS.forEach(([id])=>{const el=document.getElementById(id);if(el)obs.observe(el);});}
}
initSectionDock();
document.getElementById('status-pulse').addEventListener('click',()=>scrollToSection('section-trend'));
function usageStatus(rows){if(rows.length<2)return {label:'—',cls:'',last:rows.length?rows[rows.length-1].total:0,avg:null,delta:null,detail:'至少需要两期数据才能计算状态'};const last=rows[rows.length-1].total,prior=rows.slice(Math.max(0,rows.length-5),-1),avg=prior.reduce((a,r)=>a+r.total,0)/Math.max(1,prior.length);if(avg===0){if(last>0)return {label:'升温',cls:'warming',last,avg,delta:null,detail:'此前均值为 0，本期出现新活动'};return {label:'平稳',cls:'steady',last,avg,delta:0,detail:'本期与此前均值均为 0'};}const delta=last/avg-1,label=delta>.12?'升温':delta<-.12?'降温':'平稳',cls=delta>.12?'warming':delta<-.12?'cooling':'steady';return {label,cls,last,avg,delta,detail:'变化 '+(delta>=0?'+':'')+(delta*100).toFixed(1)+'%'};}
function renderStatusPulse(){const el=document.getElementById('status-pulse'),text=document.getElementById('status-text'),s=usageStatus(selectedRows(true));el.classList.remove('warming','steady','cooling');if(s.cls)el.classList.add(s.cls);text.textContent='状态 '+s.label;el.title=s.avg===null?s.detail+' · 点击查看趋势':'最后一期 '+fmt(s.last)+' Token；此前均值 '+fmt(s.avg)+'；'+s.detail+' · 点击查看趋势';}

/* ---- 命令面板 Cmd+K ---- */
function cmdActions(){ return [
  {ic:'◎',t:'跳转 · 总览',k:'',run:()=>scrollToSection('section-overview')},
  {ic:'↗',t:'跳转 · 趋势',k:'',run:()=>scrollToSection('section-trend')},
  {ic:'▣',t:'跳转 · 项目透镜',k:'',run:()=>scrollToSection('section-project')},
  {ic:'◫',t:'跳转 · 节奏',k:'',run:()=>scrollToSection('section-rhythm')},
  {ic:'≈',t:'跳转 · Context Reuse River',k:'',run:()=>scrollToSection('section-reuse')},
  {ic:'≋',t:'跳转 · Token 流光图',k:'',run:()=>scrollToSection('section-flow')},
  {ic:'◇',t:'跳转 · 成就',k:'',run:()=>scrollToSection('section-achievements')},
  {ic:'№',t:'跳转 · Top',k:'',run:()=>scrollToSection('section-top')},
  {ic:'📅',t:'按日',k:'1',run:()=>setGran('day')},
  {ic:'📆',t:'按周',k:'2',run:()=>setGran('week')},
  {ic:'🗓️',t:'按月',k:'3',run:()=>setGran('month')},
  {ic:'☀️',t:'亮色主题',k:'',run:()=>applyTheme('light')},
  {ic:'🌙',t:'暗色主题',k:'',run:()=>applyTheme('dark')},
  {ic:'🌗',t:'跟随系统主题',k:'T',run:()=>applyTheme('auto')},
  {ic:'⤓',t:'导出 CSV',k:'E',run:exportCSV},
  {ic:'◇',t:'导出 Markdown',k:'',run:exportMarkdown},
  {ic:'◫',t:'切换幻影对比',k:'',run:()=>document.getElementById('compare-btn').click()},
  {ic:'⧉',t:'复制当前视图链接',k:'',run:copyViewLink},
  {ic:'?',t:'查看快捷键与隐藏操作',k:'?',run:openHelp},
  {ic:'🎲',t:'换一组趣味换算',k:'',run:renderFunFacts},
  {ic:'▶',t:'播放柱图竞赛',k:'',run:()=>{ if(!document.getElementById('race').closest('[data-module]')||document.getElementById('race').closest('[data-module]').style.display!=='none') document.getElementById('race-play').click(); }},
  {ic:'⚙️',t:'打开模块开关',k:'',run:()=>document.getElementById('mods-btn').click()},
  {ic:'🎉',t:'撒花彩蛋',k:'',run:()=>{confetti();toast('🎉');}}
]; }
let pal={items:[],i:0},paletteOpener=null;
function openPalette(){paletteOpener=document.activeElement;renderPalette('');const scrim=document.getElementById('scrim');scrim.classList.add('open');scrim.setAttribute('aria-hidden','false');setTimeout(()=>document.getElementById('palette-q').focus(),10);}
function closePalette(){const scrim=document.getElementById('scrim');scrim.classList.remove('open');scrim.setAttribute('aria-hidden','true');document.getElementById('palette-q').value='';document.getElementById('palette-q').removeAttribute('aria-activedescendant');const opener=paletteOpener;paletteOpener=null;if(opener&&document.contains(opener))opener.focus();}
function renderPalette(q){
  const ul=document.getElementById('palette-list'), base=[...cmdActions(),...dataCommands()];
  pal.items=base.filter(a=>!q||(a.t+a.ic+a.k).toLowerCase().includes(q.toLowerCase())); pal.i=0;
  ul.innerHTML = pal.items.length ? pal.items.map((a,i)=>'<li id="palette-opt-'+i+'" role=option aria-selected="'+(i===0?'true':'false')+'" data-i="'+i+'"><span class=ic>'+a.ic+'</span>'+a.t+(a.k?'<span class=k>'+a.k+'</span>':'')+'</li>').join('') : '<div class="empty">无匹配结果 · 试试 whoami、42、matrix、coffee</div>';
  syncPal();
}
function runPalette(i){ const a=pal.items[i]; if(!a) return; closePalette(); setTimeout(a.run,30); }
document.getElementById('palette-q').addEventListener('input',e=>renderPalette(e.target.value));
document.getElementById('palette-q').addEventListener('keydown',e=>{if(e.key==='Enter'&&secretCommand(e.target.value)){e.preventDefault();e.stopImmediatePropagation();}});
document.getElementById('palette-list').addEventListener('click',e=>{ const li=e.target.closest('li'); if(li) runPalette(+li.dataset.i); });
document.getElementById('scrim').addEventListener('click',e=>{ if(e.target.id==='scrim') closePalette(); });
function syncPal(){const input=document.getElementById('palette-q');document.querySelectorAll('#palette-list li').forEach((li,i)=>{const active=i===pal.i;li.classList.toggle('active',active);li.setAttribute('aria-selected',String(active));});if(pal.items.length)input.setAttribute('aria-activedescendant','palette-opt-'+pal.i);else input.removeAttribute('aria-activedescendant');}
document.addEventListener('keydown',e=>{
  if((e.metaKey||e.ctrlKey)&&(e.key==='k'||e.key==='K')){ e.preventDefault(); document.getElementById('scrim').classList.contains('open')?closePalette():openPalette(); return; }
  if(e.key==='Escape'){const modal=activeModal();if(modal){e.preventDefault();if(modal.id==='replay-modal')closeReplay();else if(modal.id==='help-modal')closeHelp();else if(modal.id==='share-modal')closeShare();else if(modal.id==='ach-modal')closeAchievements();return;}}
  if(e.key==='Escape' && state.focusPeriod){ e.preventDefault(); clearFocus(true); return; }
  if(!document.getElementById('scrim').classList.contains('open')) return;
  if(e.key==='Tab'){e.preventDefault();document.getElementById('palette-q').focus();}
  else if(e.key==='Escape'){ e.preventDefault(); closePalette(); }
  else if(e.key==='ArrowDown'){ e.preventDefault(); pal.i=(pal.i+1)%Math.max(1,pal.items.length); syncPal(); }
  else if(e.key==='ArrowUp'){ e.preventDefault(); pal.i=(pal.i-1+Math.max(1,pal.items.length))%Math.max(1,pal.items.length); syncPal(); }
  else if(e.key==='Enter'){ e.preventDefault(); runPalette(pal.i); }
});

/* ---- 成就徽章（生成器：3000+ 枚，四等 + 隐藏 + 分类折叠）---- */
function tierFor(i,n){ const r=n<=1?1:i/Math.max(1,n-1); return r>=.85?'prismatic':r>=.6?'gold':r>=.35?'silver':'bronze'; }
function mk(emoji, value, thresholds, unit, fmt, pool, secret){
  // 阶梯名称带序号，确保大图鉴中每枚都有独立身份。
  return thresholds.map((v,i)=>({e:emoji,n:pool[i%pool.length]+' · '+String(i+1).padStart(2,'0'),d:fmt(v)+unit,tier:tierFor(i,thresholds.length),ok:value>=v,secret:!!secret}));
}
const POOL_BIG=['初窥门径','初出茅庐','渐入佳境','小试牛刀','初露锋芒','小有所成','炉火纯青','驾轻就熟','游刃有余','登堂入室','十万火急','名声大噪','百万富翁','声名鹊起','日进斗金','富甲一方','千万大咖','名震江湖','亿万身家','一方霸主','登峰造极','富可敌国','名扬四海','威震天下','通天代','权倾朝野','宇宙级','神话','超凡入圣','不可名状','超脱','永恒','无尽','太初','混沌','虚无','归零','重启','飞升','涅槃'];
const POOL_STREAK=['初心','坚持','小成','连胜','热身','入门','上进','勤奋','刻苦','钻研','精通','大成','宗师','泰斗','传奇','不朽','一鼓作气','再接再厉','持之以恒','锲而不舍','水滴石穿','铁杵磨针','日复一日','年复一年','春秋不辍','冬夏无休','雷打不动','风雨无阻','马不停蹄','日夜兼程'];
const POOL_DAYS=['启程','起步','摸鱼','上手','入坑','沉迷','习惯','日常','本能','呼吸','熔铸','刻入DNA','老用户','熟客','常客','元老','资深','骨灰','活化石','传说玩家'];
const POOL_RATIO=['入门','及格','顺手','熟练','老练','精通','大成','化境','登顶','极限','极致','圆满'];
const WD=['周一','周二','周三','周四','周五','周六','周日'];
const WD_PERSONA=['Monday Blue','周二综合征','周三墙','小周末','TGIF','周末战士','周日恐慌'];
function getBadgeData(){
  const h=DATA.hourly||[]; let peak=-1; for(let i=0;i<24;i++)if((h[i]||0)>(h[peak]||0))peak=i;
  const hoursActive=(h||[]).filter(x=>x>0).length;
  const days=DATA.day||[], total=days.reduce((a,d)=>a+(d.total||0),0), cr=DATA.cache_read||0, cRatio=total?cr/total:0, models=DATA.models.length;
  const dayCount=days.length, maxDay=Math.max(0,...days.map(d=>d.total));
  const calls=days.reduce((a,d)=>a+(d.calls||0),0);
  let streak=0; for(let i=days.length-1;i>=0;i--){ if(days[i].total>0) streak++; else break; }
  const nCwds=DATA.n_cwds||0, nSess=DATA.n_sessions||0, maxTurns=DATA.max_turns||0;
  const avgPerDay=dayCount?total/dayCount:0;
  const AS=DATA.achievement_stats||{}, inputTotal=AS.input||0, outputTotal=AS.output||0, cacheWrite=AS.cache_write||0;
  const sessTotals=AS.session_totals||[], cwdTotals=AS.cwd_totals||[], sourceTotals=AS.source_totals||{}, modelStats=AS.model_stats||{};
  const sortedDays=days.map(d=>d.total||0), sumA=a=>a.reduce((x,y)=>x+y,0), avgA=a=>a.length?sumA(a)/a.length:0;
  const median=a=>{if(!a.length)return 0;const s=[...a].sort((x,y)=>x-y),i=Math.floor(s.length/2);return s.length%2?s[i]:(s[i-1]+s[i])/2;};
  const variance=a=>{const av=avgA(a);return a.length?avgA(a.map(x=>(x-av)*(x-av))):0;};
  const avgSession=nSess?total/nSess:0, avgProject=nCwds?total/nCwds:0, maxSession=sessTotals[0]||0, medSession=median(sessTotals), maxProject=cwdTotals[0]||0;
  const tokensPerCall=calls?total/calls:0, callsPerDay=dayCount?calls/dayCount:0, sessionsPerDay=dayCount?nSess/dayCount:0;
  const dailyCV=avgPerDay?Math.sqrt(variance(sortedDays))/avgPerDay:0;
  const recent7=sortedDays.slice(-7), prior7=sortedDays.slice(-14,-7), avg7=avgA(recent7), avg30=avgA(sortedDays.slice(-30));
  const momentum=avgA(prior7)?avg7/avgA(prior7)-1:0;
  let growthStreak=0, declineStreak=0; for(let i=sortedDays.length-1;i>0;i--){if(sortedDays[i]>sortedDays[i-1]&&!declineStreak)growthStreak++;else if(sortedDays[i]<sortedDays[i-1]&&!growthStreak)declineStreak++;else break;}
  const hTotal=sumA(h), hRatio=(a,b)=>hTotal?sumA(h.slice(a,b))/hTotal:0;
  const nightRatio=(sumA(h.slice(0,6))+sumA(h.slice(22)))/(hTotal||1), morningRatio=hRatio(6,11), workRatio=hRatio(9,18), eveningRatio=hRatio(18,22);
  const activeHours=h.filter(v=>v>0), hourlySpan=activeHours.length, maxHour=Math.max(0,...h), avgActiveHour=avgA(activeHours);
  const modelTotals={}; days.forEach(d=>Object.entries(d.models||{}).forEach(([m,v])=>modelTotals[m]=(modelTotals[m]||0)+v));
  const modelVals=Object.values(modelTotals), topModelShare=total&&modelVals.length?Math.max(...modelVals)/total:0;
  const modelHHI=total?modelVals.reduce((a,v)=>a+(v/total)*(v/total),0):0;
  const denseLog=(lo,hi,n)=>Array.from({length:n},(_,i)=>Math.round(lo*Math.pow(hi/lo,i/Math.max(1,n-1))));
  const denseLinear=(lo,hi,n)=>Array.from({length:n},(_,i)=>lo+(hi-lo)*i/Math.max(1,n-1));
  const pushLadder=(name,e,value,thresholds,unit,formatter,pool=POOL_BIG,secret=false)=>cats.push({name,e,items:mk(e,value,[...new Set(thresholds)],unit,formatter,pool,secret)});

  const wd=[0,0,0,0,0,0,0], mo=[0,0,0,0,0,0,0,0,0,0,0,0];
  days.forEach(d=>{ const p=d.period.split('-'); const dt=new Date(Date.UTC(+p[0],+p[1]-1,+p[2])); wd[(dt.getUTCDay()+6)%7]+=d.total; mo[(+p[1]-1)]+=d.total; });
  const fmtT=v=>human(v);
  const tok=denseLog(1e3,1e14,72);
  const dayTok=denseLog(1e3,1e12,48);
  const streaks=[...Array.from({length:30},(_,i)=>i+1),...Array.from({length:35},(_,i)=>(i+7)*5),365,400,500,600,666,730,888,1000];
  const daysList=[...Array.from({length:30},(_,i)=>i+1),...Array.from({length:40},(_,i)=>(i+7)*5),250,300,365,500,666,730,888,1000,1500,2000];
  const hours=Array.from({length:24},(_,i)=>i+1);
  const modelsList=[...Array.from({length:20},(_,i)=>i+1),25,30,40,50,60,75,100,150,200];
  const cwdsList=[...Array.from({length:20},(_,i)=>i+1),25,30,40,50,75,100,150,200,300,500];
  const sessList=denseLog(1,10000,48);
  const callList=denseLog(10,1e8,52);
  const ratioList=[...Array.from({length:20},(_,i)=>(i+1)*.025),...Array.from({length:19},(_,i)=>.5+(i+1)*.025),.98,.99,.995,.999];
  const turnsList=denseLog(5,50000,42);
  const cacheAbs=denseLog(1e3,1e14,52);
  const avgList=denseLog(1e3,1e11,44);

  let cats=[];
  cats.push({name:'累计 token',e:'📈',items:mk('📈',total,tok,' tk',fmtT,POOL_BIG)});
  cats.push({name:'单日峰值',e:'📅',items:mk('📅',maxDay,dayTok,' /日',fmtT,POOL_BIG)});
  cats.push({name:'连续天数',e:'⚡',items:mk('⚡',streak,streaks,' 天',v=>v,POOL_STREAK)});
  cats.push({name:'累计活跃天',e:'🗓️',items:mk('🗓️',dayCount,daysList,' 天',v=>v,POOL_DAYS)});
  cats.push({name:'活跃小时数',e:'🕐',items:mk('🕐',hoursActive,hours,' 小时',v=>v,POOL_RATIO)});
  cats.push({name:'模型种类',e:'🎲',items:mk('🎲',models,modelsList,' 模型',v=>v,POOL_RATIO)});
  cats.push({name:'项目足迹',e:'📁',items:mk('📁',nCwds,cwdsList,' 项目',v=>v,POOL_DAYS)});
  cats.push({name:'会话数量',e:'💬',items:mk('💬',nSess,sessList,' 会话',v=>v,POOL_DAYS)});
  cats.push({name:'调用次数',e:'🔔',items:mk('🔔',calls,callList,' 次',fmtT,POOL_BIG)});
  cats.push({name:'缓存命中',e:'💎',items:mk('💎',cRatio,ratioList,'% 量',v=>(v*100).toFixed(0),POOL_RATIO)});
  cats.push({name:'缓存省量',e:'🧊',items:mk('🧊',cr,cacheAbs,' tk',fmtT,POOL_BIG)});
  cats.push({name:'单会话轮数',e:'🦠',items:mk('🦠',maxTurns,turnsList,' 轮',v=>v,POOL_STREAK)});
  cats.push({name:'日均 token',e:'⚖️',items:mk('⚖️',avgPerDay,avgList,' /日均',fmtT,POOL_BIG)});
  pushLadder('累计输入','📥',inputTotal,denseLog(1e3,1e14,54),' 输入',fmtT);
  pushLadder('累计输出','📤',outputTotal,denseLog(1e3,1e13,50),' 输出',fmtT);
  pushLadder('缓存写入','🧬',cacheWrite,denseLog(1e3,1e13,46),' 写缓存',fmtT);
  pushLadder('每次调用密度','🧱',tokensPerCall,denseLog(10,1e8,42),' tk/次',fmtT);
  pushLadder('每日调用密度','🔔',callsPerDay,denseLog(1,1e5,38),' 次/日',v=>Number(v).toFixed(v<10?1:0),POOL_STREAK);
  pushLadder('平均会话体量','💬',avgSession,denseLog(100,1e10,46),' tk/会话',fmtT);
  pushLadder('会话中位数','🪨',medSession,denseLog(100,1e10,42),' tk 中位',fmtT);
  pushLadder('最大会话','🐋',maxSession,denseLog(1e3,1e12,48),' tk/会话',fmtT);
  pushLadder('每日会话密度','🫧',sessionsPerDay,denseLog(.1,1e3,34),' 会话/日',v=>Number(v).toFixed(v<10?1:0),POOL_RATIO);
  pushLadder('平均项目体量','🏗️',avgProject,denseLog(1e3,1e12,42),' tk/项目',fmtT);
  pushLadder('最大项目','🏰',maxProject,denseLog(1e3,1e13,44),' tk/项目',fmtT);
  // 趋势、节奏与集中度阶梯
  pushLadder('夜猫指数','🌙',nightRatio,denseLinear(.025,1,40),' 夜间',v=>(v*100).toFixed(1)+'%',POOL_RATIO);
  pushLadder('晨光指数','🌅',morningRatio,denseLinear(.025,1,36),' 清晨',v=>(v*100).toFixed(1)+'%',POOL_RATIO);
  pushLadder('工时集中度','💼',workRatio,denseLinear(.025,1,36),' 日间',v=>(v*100).toFixed(1)+'%',POOL_RATIO);
  pushLadder('黄昏指数','🌆',eveningRatio,denseLinear(.025,1,34),' 晚间',v=>(v*100).toFixed(1)+'%',POOL_RATIO);
  pushLadder('波动指数','🌊',dailyCV,denseLinear(.05,3,36),' CV',v=>Number(v).toFixed(2),POOL_RATIO);
  pushLadder('增长连击','📶',growthStreak,Array.from({length:30},(_,i)=>i+1),' 天连涨',v=>v,POOL_STREAK);
  pushLadder('回落连击','📉',declineStreak,Array.from({length:30},(_,i)=>i+1),' 天连降',v=>v,POOL_STREAK);
  pushLadder('近期加速度','🚀',Math.max(0,momentum),denseLinear(.025,5,40),' 增速',v=>'+'+(v*100).toFixed(1)+'%',POOL_BIG);
  pushLadder('七日均值','7️⃣',avg7,denseLog(1e3,1e11,42),' /近7日',fmtT);
  pushLadder('三十日均值','🗓️',avg30,denseLog(1e3,1e11,42),' /近30日',fmtT);
  pushLadder('活跃小时跨度','🧭',hourlySpan,Array.from({length:24},(_,i)=>i+1),' 个时段',v=>v,POOL_DAYS);
  pushLadder('单小时峰值','⚡',maxHour,denseLog(100,1e11,44),' /小时',fmtT);
  pushLadder('活跃小时均值','⌛',avgActiveHour,denseLog(100,1e10,40),' /活跃小时',fmtT);
  pushLadder('主力模型占比','👑',topModelShare,denseLinear(.05,1,38),' 占比',v=>(v*100).toFixed(1)+'%',POOL_RATIO);
  pushLadder('模型专注指数','🎯',modelHHI,denseLinear(.05,1,38),' HHI',v=>Number(v).toFixed(2),POOL_RATIO);

  // 星期 × 小时：每一个星期时刻都是独立可收集坐标
  const wdHour=Array.from({length:7},()=>Array(24).fill(0));
  days.forEach(d=>{const x=DATA.day_details[d.period],p=d.period.split('-'),dt=new Date(Date.UTC(+p[0],+p[1]-1,+p[2])),w=(dt.getUTCDay()+6)%7;if(x)(x.hourly||[]).forEach((v,hour)=>wdHour[w][hour]+=v||0);});
  const wdHourItems=[]; const WHT=[1e2,1e3,1e4,1e5];
  WD.forEach((day,w)=>{for(let hour=0;hour<24;hour++)WHT.forEach((v,i)=>wdHourItems.push({e:['·','▪','◆','✦'][i],n:day+' '+String(hour).padStart(2,'0')+'点·'+['微光','点亮','炽热','恒星'][i],d:day+' '+String(hour).padStart(2,'0')+':00 累计 '+fmtT(v)+' tk',tier:tierFor(i,WHT.length),ok:wdHour[w][hour]>=v,secret:i>=3}));});
  cats.push({name:'星期时空坐标',e:'🧿',items:wdHourItems});

  // 月份 × 四时段
  const moBand=Array.from({length:12},()=>Array(4).fill(0)), bands=[[0,6,'深夜'],[6,12,'晨午'],[12,18,'午后'],[18,24,'晚间']];
  days.forEach(d=>{const x=DATA.day_details[d.period],mon=Number(d.period.slice(5,7))-1;if(x)bands.forEach(([a,b],bi)=>moBand[mon][bi]+=sumA((x.hourly||[]).slice(a,b)));});
  const moBandItems=[];for(let m=0;m<12;m++)bands.forEach((band,bi)=>[1e3,1e5,1e7,1e9].forEach((v,i)=>moBandItems.push({e:['🌑','🌓','🌕','☀️'][i],n:(m+1)+'月·'+band[2]+'·'+['初响','回声','盛放','传说'][i],d:(m+1)+'月 '+band[2]+'累计 '+fmtT(v)+' tk',tier:tierFor(i,4),ok:moBand[m][bi]>=v,secret:i===3})));
  cats.push({name:'月份四时',e:'🌗',items:moBandItems});

  // 模型 × 时段人格
  const modelBandItems=[];Object.entries(modelStats).forEach(([m,ms],mi)=>{const mh=Array(24).fill(0);Object.values(DATA.day_details||{}).forEach(x=>{const a=(x.hourly_models||{})[m]||[];a.forEach((v,i)=>mh[i]+=v||0);});bands.forEach(([a,b,nm],bi)=>{const v=sumA(mh.slice(a,b));[1e3,1e5,1e7].forEach((th,i)=>modelBandItems.push({e:'🤖',n:pretty(m)+'·'+nm+'·'+['邂逅','搭档','灵魂'][i],d:pretty(m)+' 在'+nm+'累计 '+fmtT(th)+' tk',tier:tierFor(i,3),ok:v>=th,secret:i===2}));});});
  cats.push({name:'模型时段羁绊',e:'🪢',items:modelBandItems});

  // 来源阶梯
  Object.entries(sourceTotals).forEach(([src,v])=>pushLadder('来源 · '+src,'📡',v,denseLog(1e3,1e13,36),' tk',fmtT,POOL_BIG));

  // 组合成就：总量、缓存、连续、模型、会话彼此交叉
  const combo=[];
  const totalBands=[1e5,1e6,1e7,1e8,1e9,1e10], cacheBands=[.1,.3,.5,.7,.9];
  totalBands.forEach((tv,ti)=>cacheBands.forEach((cv,ci)=>combo.push({e:'⚗️',n:'算力炼金·'+(ti+1)+'-'+(ci+1),d:'累计 '+fmtT(tv)+' 且缓存率 '+Math.round(cv*100)+'%',tier:tierFor(ti+ci,totalBands.length+cacheBands.length),ok:total>=tv&&cRatio>=cv,secret:ci>=3})));
  [3,7,14,30,60,100].forEach((sv,si)=>[1e5,1e6,1e7,1e8,1e9].forEach((tv,ti)=>combo.push({e:'🔥',n:'长燃引擎·'+sv+'×'+(ti+1),d:'连续 '+sv+' 天且累计 '+fmtT(tv),tier:tierFor(si+ti,10),ok:streak>=sv&&total>=tv,secret:si>=4})));
  [1,2,3,5,8,12].forEach((mv,mi)=>[10,50,100,500,1000].forEach((sv,si)=>combo.push({e:'🧩',n:'多元宇宙·'+mv+'×'+sv,d:'使用 '+mv+' 模型且拥有 '+sv+' 会话',tier:tierFor(mi+si,10),ok:models>=mv&&nSess>=sv,secret:mi>=4})));
  cats.push({name:'复合炼金术',e:'⚗️',items:combo});

  // 24 时刻 × 量级矩阵
  const hourItems=[]; const htok=[1e2,1e3,1e4,1e5,1e6];
  for(let hr=0;hr<24;hr++){ htok.forEach((v,i)=>{ const name=['夜巡','更夫','守夜','夜神','夜之王'][i]; hourItems.push({e:'🕒',n:String(hr).padStart(2,'0')+'点·'+name,d:String(hr).padStart(2,'0')+':00 烧 '+fmtT(v)+' tk',tier:tierFor(i,htok.length),ok:(h[hr]||0)>=v,secret:i>=3}); }); }
  cats.push({name:'时刻战士',e:'🕒',items:hourItems});
  // 星期矩阵
  const wdItems=[]; const wdt=[1e4,1e6,1e8,1e10]; WD.forEach((nm,w)=> wdt.forEach((v,i)=> wdItems.push({e:'▮',n:nm+['·学徒','·常客','·狂魔','·化身'][i],d:nm+'累计 '+fmtT(v)+' tk',tier:tierFor(i,wdt.length),ok:wd[w]>=v})) );
  cats.push({name:'星期人格',e:'📆',items:wdItems});
  // 月份矩阵
  const moItems=[]; const mot=[1e5,1e7,1e9]; for(let m=0;m<12;m++) mot.forEach((v,i)=> moItems.push({e:'🌙',n:(m+1)+'月'+['·起势','·丰收','·封神'][i],d:(m+1)+'月累计 '+fmtT(v)+' tk',tier:tierFor(i,mot.length),ok:mo[m]>=v}));
  cats.push({name:'月份里程碑',e:'🌙',items:moItems});
  // 每个用过模型一枚
  const modelItems=(DATA.models||[]).map((m,i)=>{const tot=days.reduce((a,d)=>a+((d.models[m])||0),0);return {e:'🤖',n:pretty(m)+'用户',d:'用过 '+pretty(m),tier:tierFor(i,Math.max(1,DATA.models.length)),ok:tot>0};});
  cats.push({name:'模型图鉴',e:'🤖',items:modelItems});

  // ---- 奇思妙想 / 隐藏彩蛋 ----
  const SE=[];
  const has=v=>total>=v;
  // 数字彩蛋
  const eggs=[
    [42,'宇宙答案'],[64,'六十四位'],[128,'半字节军团'],[256,'像素方阵'],[404,'成就未找到'],[418,'我是茶壶'],[451,'不可用'],[500,'服务器冒烟'],[520,'我爱你'],[666,'恶魔契约'],[777,'幸运七'],[888,'发发发'],[999,'长长久久'],[1024,'一千零二十四'],[1314,'一生一世'],[1337,'Leet'],[2048,'合成玩家'],[4096,'页大小'],[5200,'我爱你加长版'],[7777,'老虎机'],[8192,'八千字节'],[9000,'Over 9000'],[10000,'万事开头'],[16384,'十六K'],[23333,'笑出声'],[32768,'有符号边界'],[65535,'端口之王'],[65536,'无符号飞升'],[66666,'六六大顺'],[88888,'暴富预兆'],[99999,'九九归一'],[111111,'全一教'],[123456,'顺子'],[161803,'黄金比'],[271828,'自然底'],[314159,'圆周率'],[524288,'半兆'],[654321,'倒顺子'],[666666,'六道轮回'],[777777,'七星连珠'],[888888,'一路发'],[999999,'无限逼近'],[1048576,'一兆门槛'],[1234567,'连续升级'],[16777216,'真彩色'],[5201314,'真爱粉'],[10000000,'千万俱乐部'],[16777215,'RGB 白'],[33554432,'三十二兆'],[100000000,'亿万先生'],[1073741824,'一吉字节'],[2147483647,'整数之巅'],[4294967295,'无符号边界']
  ];
  eggs.forEach(([v,nm])=>SE.push({e:'🎰',n:nm,d:'token 含 / 达到 '+fmtT(v),tier:'gold',ok:has(v)||String(total).includes(String(v)),secret:true}));
  // 单日数字蛋
  [[666666,'单日六六六'],[888888,'单日发发发'],[50000000,'单日五千万'],[100000000,'单日破亿']].forEach(([v,nm])=>SE.push({e:'🥚',n:nm,d:'单日达到 '+fmtT(v),tier:'gold',ok:maxDay>=v,secret:true}));
  // 时段人格（按峰值）
  const persona=[['🌅','破晓行者',5,8],['☕','早C战士',8,11],['🍱','午间摸鱼',11,14],['🍵','下午茶王',14,18],['🌆','黄昏斗士',18,21],['🌙','夜行者',21,24],['🦉','修仙党',0,5]];
  persona.forEach(([e,nm,a,b])=>SE.push({e,n:nm,d:'峰值在 '+a+'-'+b+' 点',tier:'silver',ok:peak>=a&&peak<b}));
  SE.push({e:'🕛',n:'子夜战神',d:'峰值恰在 0 点',tier:'gold',ok:peak===0,secret:true});
  SE.push({e:'🐓',n:'晨型人',d:'峰值在 6 点',tier:'silver',ok:peak===6,secret:true});
  // 星期人格
  WD_PERSONA.forEach((nm,w)=>SE.push({e:'📆',n:nm,d:'用量最高的是 '+WD[w],tier:'silver',ok: wd[w]===Math.max(...wd)&&Math.max(...wd)>0,secret:w<5}));
  // 周末战士
  const wkend=wd[5]+wd[6], wkdayAvg=(wd[0]+wd[1]+wd[2]+wd[3]+wd[4])/(5||1);
  SE.push({e:'🏄',n:'周末战士',d:'周末日均 > 工作日',tier:'gold',ok:wkend/2>wkdayAvg,secret:true});
  SE.push({e:'💼',n:'打工人',d:'工作日 > 周末',tier:'silver',ok:wkdayAvg>wkend/2,secret:true});
  // 全天候 / 极端
  SE.push({e:'🌍',n:'全天候',d:'24 小时都有用量',tier:'gold',ok:hoursActive>=24});
  SE.push({e:'🎯',n:'专一',d:'只用 1 个模型',tier:'bronze',ok:models===1});
  SE.push({e:'🌈',n:'万花筒',d:'用过 ≥5 模型',tier:'gold',ok:models>=5});
  SE.push({e:'🦠',n:'话痨',d:'单会话 ≥500 轮',tier:'gold',ok:maxTurns>=500,secret:true});
  SE.push({e:'🗂️',n:'多面手',d:'≥5 个项目',tier:'silver',ok:nCwds>=5});
  SE.push({e:'🐢',n:'龟速',d:'日均 <1 万',tier:'bronze',ok:avgPerDay<1e4&&dayCount>5,secret:true});
  SE.push({e:'🚀',n:'爆发',d:'单日占总量 ≥40%',tier:'gold',ok:maxDay>=total*0.4&&total>0,secret:true});
  // 编程梗（接真实条件）
  const TR=[
    ['👋','Hello World', total>=1e4],['🐛','捉虫能手', calls>=1000],['🧹','洁癖', cRatio>=0.9],['💀','rm -rf 幸存者', total>=1e8],
    ['🌀','无限循环', streak>=30],['📦','囤积狂', nCwds>=30],['🤡','摸鱼王', streak<3 && dayCount>10],['🎲','随机种子', models>=4],
    ['🧊','冷启动', cRatio<0.1 && total>1e5],['🔥','热加载', cRatio>=0.99],['🪦','坟墓', nSess>=100],['⚙️','CRUD 战神', calls>=1e4],
    ['🧪','实验狂', nCwds>=10],['🪄','魔法师', maxTurns>=1000],['🦆','鸭子调试', peak>=0&&peak<4],['🎈','内存泄漏', nSess>=500],
    ['🧭','导航员', nCwds>=20],['🍄','蘑菇', peak>=0&&peak<4],['🛷','滑坡', streak<dayCount-5 && dayCount>20],['🎨','调色板', models>=6],
    ['🧩','拼图', nCwds>=15],['🔭','观星者', hoursActive>=20],['🦾','钢铁肝', total>=5e7],['🧠','脑力劳动者', calls>=5000],
    ['🍔','外卖续命', peak>=22||peak<2],['💤','失眠', hoursActive>=22],['🪞','照镜子', models===1],['🎵','单曲循环', models===1 && total>1e6],
    ['🧶','乱麻', nCwds>=40],['🏹','神射手', cRatio>=0.85],
    ['🌃','赛博夜行人',nightRatio>=.5],['🌄','朝九之前',morningRatio>=.5],['🏢','标准工时',workRatio>=.65],['🌆','下班才上班',eveningRatio>=.5],
    ['🎢','过山车',dailyCV>=1.5],['🧘','稳定发挥',dailyCV<=.15&&dayCount>=7],['📈','牛市',growthStreak>=7],['📉','熊市',declineStreak>=7],
    ['🚄','高速迭代',momentum>=1],['🪶','轻量会话',avgSession>0&&avgSession<1e4],['🐘','重量级会话',avgSession>=1e7],['🐋','利维坦会话',maxSession>=1e9],
    ['🏙️','项目都市',nCwds>=100],['🌌','项目星系',nCwds>=500],['💬','群聊现场',sessionsPerDay>=20],['🔕','静默少言',sessionsPerDay<1&&dayCount>=7],
    ['🥇','一枝独秀',topModelShare>=.9],['🤹','左右开弓',models>=2&&topModelShare<.65],['🌈','模型联合国',models>=8],['🎯','极致专注',modelHHI>=.95],
    ['🫧','均匀分布',modelHHI<=.3&&models>=4],['📥','海纳百川',inputTotal>=1e9],['📤','滔滔不绝',outputTotal>=1e8],['🧬','缓存播种者',cacheWrite>=1e8],
    ['🧱','上下文长城',tokensPerCall>=1e6],['⚡','闪电问答',tokensPerCall<1e3&&calls>=100],['🧺','批处理大师',callsPerDay>=1000],['🕰️','长线主义',dayCount>=365],
    ['🪄','Prompt 巫师',outputTotal>inputTotal],['📚','上下文图书馆',inputTotal>=outputTotal*20&&outputTotal>0],['♻️','循环利用',cr>inputTotal],['🧯','缓存灭火器',cRatio>=.95&&total>=1e7],
    ['🧑‍🚀','全栈宇航员',nCwds>=20&&models>=5&&hoursActive>=18],['🧑‍💻','真正的程序员',nightRatio>=.4&&calls>=10000],['☕','咖啡编译器',h[9]>0&&h[14]>0&&h[21]>0],['🍜','泡面时区',h[0]+h[1]+h[2]>=hTotal*.25],
    ['🧿','零点观测站',h[0]>=maxHour*.8&&maxHour>0],['🐓','早起提交',h[6]>=maxHour*.8&&maxHour>0],['🥪','午休提交',h[12]+h[13]>=hTotal*.2],['🌇','晚高峰提交',h[18]+h[19]>=hTotal*.25],
    ['📆','周一启动器',wd[0]===Math.max(...wd)],['🎉','周五释放',wd[4]===Math.max(...wd)],['🏖️','双休日构建',wd[5]+wd[6]>(sumA(wd.slice(0,5))/5)*2],['🛠️','工作日机器',sumA(wd.slice(0,5))>=sumA(wd.slice(5))*4],
    ['🔬','微服务人格',avgProject<1e6&&nCwds>=10],['🗿','单体巨石',maxProject>=total*.8&&nCwds>0],['🪐','多项目轨道',nCwds>=50&&maxProject<total*.3],['🧳','项目旅行家',nCwds>=dayCount&&dayCount>10],
    ['🎛️','参数调优师',models>=3&&cRatio>=.7],['🔋','满电运行',streak>=100&&hoursActive>=18],['🕳️','Token 黑洞',maxDay>=1e9],['🌋','单日喷发',maxDay>=avgPerDay*8&&dayCount>=7],
    ['🧊','绝对零度',total===0],['🌱','第一粒 Token',total>0],['🛤️','万里长征',dayCount>=1000],['🏛️','数字文明',total>=1e12]
  ];
  TR.forEach(([e,nm,ok])=>SE.push({e,n:nm,d:nm,tier:'silver',ok,secret:true}));
  // 星座/生肖（按生成日期，必解锁其一）
  const ZODIAC=[['♈','白羊'],['♉','金牛'],['♊','双子'],['♋','巨蟹'],['♌','狮子'],['♍','处女'],['♎','天秤'],['♏','天蝎'],['♐','射手'],['♑','摩羯'],['♒','水瓶'],['♓','双鱼']];
  const gd=new Date(), gm=gd.getMonth()+1, gday=gd.getDate();
  const zidx=(gm===12&&gday>=22)||gm<=1&&gday<20?9:gm<=2?10:gm<=3?11:gm<=4?0:gm<=5?1:gm<=6?2:gm<=7?3:gm<=8?4:gm<=9?5:gm<=10?6:gm<=11?7:8;
  ZODIAC.forEach((z,i)=>SE.push({e:z[0],n:'星座·'+z[1],d:'今日星座 '+z[1],tier:'bronze',ok:i===zidx}));
  const SX=['🐀鼠','🐂牛','🐅虎','🐇兔','🐉龙','🐍蛇','🐎马','🐐羊','🐒猴','🐓鸡','🐕狗','🐖猪'];
  const sxIdx=(gd.getFullYear()-4)%12;
  SX.forEach((s,i)=>SE.push({e:'🔮',n:'生肖·'+s,d:'今年生肖 '+s,tier:'bronze',ok:i===sxIdx}));
  // 节日（按 mm-dd）
  const fest=[['01-01','元旦'],['02-14','情人节'],['03-08','妇女节'],['03-14','圆周率日'],['04-01','愚人节'],['04-22','地球日'],['05-01','劳动节'],['05-04','青年节'],['05-17','电信日'],['06-01','儿童节'],['07-01','建党节'],['07-17','世界 Emoji 日'],['08-15','抗战胜利'],['09-10','教师节'],['09-13','程序员节'],['10-01','国庆'],['10-24','程序员节 1024'],['10-31','万圣节'],['11-11','双十一'],['12-24','平安夜'],['12-25','圣诞节']];
  const today=String(gm).padStart(2,'0')+'-'+String(gday).padStart(2,'0');
  fest.forEach(([d,nm])=>SE.push({e:'🎉',n:'节日·'+nm,d:'在 '+nm+' 跑了统计',tier:'silver',ok:d===today,secret:true}));
  const solar=['小寒','大寒','立春','雨水','惊蛰','春分','清明','谷雨','立夏','小满','芒种','夏至','小暑','大暑','立秋','处暑','白露','秋分','寒露','霜降','立冬','小雪','大雪','冬至'];
  solar.forEach((nm,i)=>{const target=Math.round(i*365/24),now=Math.floor((gd-new Date(gd.getFullYear(),0,1))/86400000);SE.push({e:'🌿',n:'节气·'+nm,d:'在'+nm+'附近生成报告',tier:i%6===0?'gold':'bronze',ok:Math.abs(now-target)<=2,secret:true});});
  const dateEggs=[['镜像日期',today.split('-').join('')===today.split('-').join('').split('').reverse().join('')],['双数之日',/[02468]{4}/.test(today.replace('-',''))],['幸运七日',today.includes('07')],['六六之日',today.includes('06')],['八八之日',today.includes('08')],['连续日期',/123|234|345|456|567|678|789/.test(today.replace('-',''))],['月日相同',gm===gday],['月末守望',gday===new Date(gd.getFullYear(),gm,0).getDate()]];
  dateEggs.forEach(([nm,ok])=>SE.push({e:'📟',n:nm,d:'生成日期触发：'+nm,tier:'silver',ok,secret:true}));
  cats.push({name:'奇思妙想 · 隐藏',e:'✨',items:SE});

  const ALL=[].concat(...cats.map(c=>c.items));
  const got=ALL.filter(b=>b.ok).length;
  return {cats, all:ALL, got, pct: ALL.length? got/ALL.length:0};
}
function badgeCell(b){
  const masked=b.secret&&!b.ok;
  const cls='badge '+(b.ok?('on tier-'+b.tier):'off')+(b.secret?' secret':'');
  return '<div class="'+cls+'" title="'+(masked?'隐藏成就，达成自动揭晓':esc(b.d))+'">'
    +'<div class=ring>'+(masked?'❓':(b.ok?b.e:'🔒'))+'</div>'
    +'<div class=nm>'+(masked?'???':esc(b.n))+'</div>'
    +'<div class=dc>'+(masked?'隐藏':esc(b.d))+'</div></div>';
}
function runAchievementStrip(){
  if(!_ach)return;if(_stripT){clearInterval(_stripT);_stripT=null;}
  const a=_ach,roll=()=>{const src=a.all.filter(b=>b.ok),pool=src.length?src:a.all,pick=[];for(let i=0;i<6;i++)pick.push(pool[Math.floor(Math.random()*pool.length)]);document.getElementById('ach-strip').innerHTML=pick.map(badgeCell).join('');};
  roll();if(document.documentElement.dataset.motion==='full')_stripT=setInterval(roll,3500);
}
let _ach=null, _stripT=null;
function renderBadges(){
  _ach=getBadgeData(); const a=_ach;
  document.getElementById('ach-meta').innerHTML='已解锁 <b>'+a.got+'</b> / '+a.all.length;
  document.getElementById('ach-meta2').innerHTML='收集进度 <b>'+a.got+'</b> / '+a.all.length+' 枚';
  const C=2*Math.PI*42, arc=document.getElementById('ach-arc');
  arc.style.strokeDasharray=C.toFixed(1);
  arc.style.strokeDashoffset=C.toFixed(1);
  setTimeout(()=>{ arc.style.strokeDashoffset=(C*(1-a.pct)).toFixed(1); document.getElementById('ach-pct').textContent=Math.round(a.pct*100)+'%'; }, 60);
  document.getElementById('ach-pct').textContent=Math.round(a.pct*100)+'%';
  runAchievementStrip();
  // 等级分布条 + 最高等级
  const TCOL={bronze:'#c08457',silver:'#b8c0cc',gold:'#f0b429',prismatic:'linear-gradient(90deg,#5b8def,#a78bfa,#f472b6,#14b8a6)'};
  const TLB={bronze:'青铜',silver:'白银',gold:'黄金',prismatic:'彩钻'};
  const TORD=['prismatic','gold','silver','bronze'];
  const trows=TORD.map(t=>{ const bs=a.all.filter(b=>b.tier===t); const g=bs.filter(b=>b.ok).length; return {t,g,n:bs.length,pct:bs.length?g/bs.length:0}; });
  document.getElementById('ach-tiers').innerHTML=trows.map(r=>{
    const bg=TCOL[r.t];
    return '<div class=trow><span class=tl><i style="background:'+(r.t==='prismatic'?'#a78bfa':bg)+'"></i>'+TLB[r.t]+'</span>'
      +'<span class=tbar><j style="width:'+(r.pct*100).toFixed(1)+'%;background:'+bg+'"></j></span>'
      +'<span class=tv>'+r.g+'/'+r.n+'</span></div>';
  }).join('');
  const top=TORD.find(t=>trows.find(r=>r.t===t&&r.g>0))||'bronze';
  const tr=trows.find(r=>r.t===top);
  document.getElementById('ach-ringlab').innerHTML='最高 <b>'+TLB[top]+'</b><br>'+tr.g+' 枚已集齐';
}
window.addEventListener('tk-motion-change',()=>{if(_ach)runAchievementStrip();});
function achievementCategory(c,items,open,index){
  const g=items.filter(b=>b.ok).length, collapsed=open?'':' collapsed',contentId='ach-cat-'+index;
  return '<div class="cat'+collapsed+'" data-ach-cat="'+esc(c.name)+'"><button type=button class=cat-h aria-expanded="'+(open?'true':'false')+'" aria-controls="'+contentId+'"><span class=ce>'+c.e+'</span><span>'+c.name+'</span><span class=cc><b>'+g+'</b> / '+items.length+'</span><span class=chev aria-hidden=true>▼</span></button><div class=cat-grid id="'+contentId+'">'+(open?items.map(badgeCell).join(''):'')+'</div></div>';
}
function renderAchievements(q){
  if(!_ach) _ach=getBadgeData(); const a=_ach; q=(q||'').trim().toLowerCase();
  const filter=document.getElementById('ach-filter').value;
  const okFilter=b=>filter==='all'||(filter==='on'&&b.ok)||(filter==='off'&&!b.ok)||(filter==='secret'&&b.secret)||b.tier===filter;
  document.getElementById('ach-modal-meta').innerHTML='已解锁 <b>'+a.got+'</b> / '+a.all.length+' · '+Math.round(a.pct*100)+'%';
  let shown=0, visibleCats=0; const forceOpen=!!q||filter!=='all';
  const body=a.cats.map((c,index)=>{
    let items=c.items.filter(okFilter);
    if(q) items=items.filter(b=>(c.name+' '+b.n+' '+b.d).toLowerCase().includes(q));
    if(!items.length) return '';
    shown+=items.length; visibleCats++;
    return achievementCategory(c,items,forceOpen,index);
  }).join('');
  document.getElementById('ach-body').innerHTML='<div class=ach-stats><span>当前显示 <b>'+shown+'</b> 枚</span><span><b>'+visibleCats+'</b> 个分类</span><span>总图鉴 <b>'+a.all.length+'</b> 枚</span><span>展开分类时按需渲染</span></div>'+body;
  document.querySelectorAll('#ach-body .cat-h').forEach(h=>h.addEventListener('click',()=>{
    const cat=h.parentElement, grid=cat.querySelector('.cat-grid');
    if(cat.classList.contains('collapsed')){
      const c=a.cats.find(x=>x.name===cat.dataset.achCat); if(!c)return;
      let items=c.items.filter(okFilter);if(q)items=items.filter(b=>(c.name+' '+b.n+' '+b.d).toLowerCase().includes(q));
      if(!grid.childElementCount)grid.innerHTML=items.map(badgeCell).join('');cat.classList.remove('collapsed');h.setAttribute('aria-expanded','true');
    }else{cat.classList.add('collapsed');h.setAttribute('aria-expanded','false');}
  }));
}
function openAchievements(){renderAchievements(document.getElementById('ach-search').value);openModal(document.getElementById('ach-modal'),document.getElementById('ach-search'));}
function closeAchievements(){closeModal(document.getElementById('ach-modal'));}
document.getElementById('ach-open').addEventListener('click',openAchievements);
document.getElementById('ach-x').addEventListener('click',closeAchievements);
document.getElementById('ach-modal').addEventListener('click',e=>{if(e.target.id==='ach-modal')closeAchievements();});document.getElementById('ach-modal').addEventListener('keydown',e=>trapModalFocus(e,e.currentTarget));
document.getElementById('ach-search').addEventListener('input',e=>renderAchievements(e.target.value));
document.getElementById('ach-filter').addEventListener('change',()=>renderAchievements(document.getElementById('ach-search').value));
document.getElementById('ach-confetti').addEventListener('click',()=>{ confetti(); toast('🎉 庆祝 '+Math.round((_ach?_ach.pct:0)*100)+'% 进度'); });

/* ---- Token 星云：数据生成的彩色深空 ---- */
function renderDNA(){
  const svg=document.getElementById('dna'), h=filteredHourly(), days=selectedRows(), total=days.reduce((a,d)=>a+d.total,0), cr=focusDetail()?.cache_read??selectedCacheRead(), cache=total?cr/total:0;
  const mt={};days.forEach(d=>Object.entries(d.models||{}).forEach(([m,v])=>mt[m]=(mt[m]||0)+v));const models=Object.entries(mt).sort((a,b)=>b[1]-a[1]),ht=h.reduce((a,b)=>a+b,0),hmax=Math.max(1,...h),cx=150,cy=150;
  let p=['<defs><radialGradient id="ng" cx="50%" cy="50%"><stop offset="0" stop-color="#ffffff"/><stop offset=".18" stop-color="#d8e7ff"/><stop offset=".52" stop-color="#8daeff" stop-opacity=".9"/><stop offset="1" stop-color="#5b8def" stop-opacity="0"/></radialGradient><filter id="nb"><feGaussianBlur stdDeviation="5"/></filter><filter id="nbl"><feGaussianBlur stdDeviation="11"/></filter></defs>'];
  // 背景恒星：确定性分布，避免每次渲染跳动
  for(let i=0;i<72;i++){const seed=(i*7919+(total%104729))%100003,a=seed*.017,r=35+(seed%110),x=cx+Math.cos(a)*r,y=cy+Math.sin(a)*r*.86,rr=.35+(seed%7)/10;p.push('<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+rr.toFixed(1)+'" fill="#dbe9ff" opacity="'+(.18+(seed%5)*.1)+'"/>');}
  // 每个模型形成一条独立旋臂，模型颜色清晰可辨
  const arms=models.length?models:[[null,total]];
  arms.slice(0,8).forEach(([m,mv],mi)=>{
    const color=m?DATA.colors[m]:'#7aa2f7',frac=total?mv/total:1,count=Math.max(18,Math.round(24+frac*74)),phase=mi/Math.max(1,arms.length)*Math.PI*2+(total%97)/31;
    let haze='';for(let j=0;j<count;j++){const t=(j+1)/count,a=phase+t*Math.PI*(3.2+arms.length*.12),hour=Math.floor(t*24)%24,energy=(h[hour]||0)/hmax,rad=18+t*112+(energy-.5)*16,wob=Math.sin(j*1.73+mi)*9*(1-t*.45),x=cx+Math.cos(a)*rad+Math.cos(a+Math.PI/2)*wob,y=cy+Math.sin(a)*rad*.72+Math.sin(a+Math.PI/2)*wob*.72,rr=1.1+energy*2.9+(j%9===0?1.5:0),op=.25+energy*.58;haze+='<circle class="nebula-particle" cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+rr.toFixed(1)+'" fill="'+color+'" opacity="'+op.toFixed(2)+'"><title>'+esc(m?pretty(m):'Token')+' · '+String(hour).padStart(2,'0')+':00 · '+human(h[hour]||0)+' tk</title></circle>';if(j%4===0)haze+='<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+(rr*3.4).toFixed(1)+'" fill="'+color+'" opacity="'+(.035+energy*.055).toFixed(3)+'" filter="url(#nb)"/>';}
    p.push('<g class="nebula-arm" style="animation-delay:-'+(mi*11)+'s">'+haze+'</g>');
  });
  // 24 个小时轨道信标
  for(let hour=0;hour<24;hour++){const v=h[hour]||0,energy=v/hmax,a=hour/24*Math.PI*2-Math.PI/2,r=126+energy*13,x=cx+Math.cos(a)*r,y=cy+Math.sin(a)*r*.72;if(v>0)p.push('<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+(1.4+energy*3).toFixed(1)+'" fill="#fff" opacity="'+(.28+energy*.7).toFixed(2)+'"><title>'+String(hour).padStart(2,'0')+':00 · '+fmt(v)+' Token</title></circle>');}
  // 缓存率越高，中央星核越明亮并出现更多光环
  p.push('<circle cx="150" cy="150" r="'+(24+cache*19).toFixed(1)+'" fill="url(#ng)" opacity=".32" filter="url(#nbl)"/><g class="nebula-core"><circle cx="150" cy="150" r="'+(10+cache*6).toFixed(1)+'" fill="url(#ng)"/><circle cx="150" cy="150" r="3.2" fill="#fff"/></g>');
  if(models.length){const dom=models[0];p.push('<text x="150" y="282" text-anchor="middle" fill="#91a6c8" font-size="8.5" letter-spacing="1.5">DOMINANT · '+esc(pretty(dom[0]).toUpperCase())+'</text>');}
  svg.innerHTML=p.join('');
  let peak=0;for(let i=1;i<24;i++)if((h[i]||0)>(h[peak]||0))peak=i;
  document.getElementById('nebula-meta').innerHTML='<div><b>'+models.length+' 个星团</b>模型光谱</div><div><b>'+String(peak).padStart(2,'0')+':00</b>最亮轨道</div><div><b>'+Math.round(cache*100)+'%</b>星核亮度</div>';
}
document.getElementById('dna-dl').addEventListener('click',()=>{
  const svg=document.getElementById('dna').cloneNode(true); svg.setAttribute('xmlns','http://www.w3.org/2000/svg');
  svg.setAttribute('style','background:#0b1120');
  const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob(['<?xml version="1.0"?>\n'+svg.outerHTML],{type:'image/svg+xml'})); a.download='token-nebula.svg'; a.click(); toast('Token 星云已收藏为 SVG');
});

/* ---- 会话时间轴回放 ---- */
let rp={series:[],i:0,timer:null};
function openReplay(sid,label){
  const s=DATA.session_series[sid]||[];
  if(!s.length){ toast('该会话无逐轮数据'); return; }
  rp.series=s; rp.i=0;
  document.getElementById('replay-title').textContent=label||'会话回放';
  document.getElementById('replay-sub').textContent=s.length+' 轮'+(s.length>=200?'（最近 200 轮）':'')+' · 共 '+human(s.reduce((a,b)=>a+b,0))+' token · 横轴为轮次，不代表真实耗时';
  const modal=document.getElementById('replay-modal');openModal(modal,document.getElementById('replay-x'));
  const scrub=document.getElementById('replay-scrub');scrub.max=String(s.length-1);scrub.value='0';
  drawECG(0);
}
function closeReplay(){if(rp.timer){clearInterval(rp.timer);rp.timer=null;}document.getElementById('replay-play').textContent='▶ 播放';closeModal(document.getElementById('replay-modal'));}
function drawECG(index){
  const s=rp.series, W=700,H=160, max=Math.max(1,...s), n=s.length;
  let line=''; s.forEach((v,i)=>{ const x=i/Math.max(1,n-1)*W, y=H-6-(v/max)*(H-12); line+=(i?'L':'M')+x.toFixed(1)+' '+y.toFixed(1)+' '; });
  const cur=Math.max(0,Math.min(n-1,Math.round(index))),cx=cur/Math.max(1,n-1)*W,cy=H-6-(s[cur]||0)/max*(H-12),total=s.reduce((a,b)=>a+b,0),cum=s.slice(0,cur+1).reduce((a,b)=>a+b,0);rp.i=cur;
  document.getElementById('replay-ecg').innerHTML='<path d="'+line+'L '+W+' '+H+' L 0 '+H+' Z" fill=var(--accent-soft)/><path d="'+line+'" fill=none stroke=var(--accent-2) stroke-width=1.5/>'
    +'<line x1="'+cx.toFixed(1)+'" y1=0 x2="'+cx.toFixed(1)+'" y2='+H+' stroke=var(--accent)/><circle cx="'+cx.toFixed(1)+'" cy="'+cy.toFixed(1)+'" r=3.5 fill=var(--accent)/>';
  document.getElementById('replay-pos').textContent=(cur+1)+'/'+n;
  const scrub=document.getElementById('replay-scrub');scrub.value=String(cur);scrub.setAttribute('aria-valuetext','第 '+(cur+1)+' 轮，'+fmt(s[cur]||0)+' Token，累计 '+(total?cum/total*100:0).toFixed(1)+'%');
  document.getElementById('replay-stats').innerHTML='<span>当前轮 '+fmt(s[cur]||0)+' tk</span><span>累计 '+fmt(cum)+' tk</span><span>累计占比 '+(total?cum/total*100:0).toFixed(1)+'%</span>';
}
document.getElementById('replay-x').addEventListener('click',closeReplay);
document.getElementById('replay-modal').addEventListener('keydown',e=>trapModalFocus(e,e.currentTarget));
document.getElementById('replay-modal').addEventListener('click',e=>{ if(e.target.id==='replay-modal') closeReplay(); });
function stopReplay(){if(rp.timer){clearInterval(rp.timer);rp.timer=null;document.getElementById('replay-play').textContent='▶ 播放';}}
document.getElementById('replay-scrub').addEventListener('input',e=>{stopReplay();drawECG(Number(e.target.value||0));});
document.getElementById('replay-ecg').addEventListener('pointerdown',e=>{stopReplay();const r=e.currentTarget.getBoundingClientRect(),index=(e.clientX-r.left)/Math.max(1,r.width)*Math.max(0,rp.series.length-1);drawECG(index);});
document.getElementById('replay-play').addEventListener('click',function(){
  if(rp.timer){ clearInterval(rp.timer); rp.timer=null; this.textContent='▶ 播放'; return; }
  if(rp.series.length<2) return; let index=rp.i;if(index>=rp.series.length-1)index=-1;this.textContent='⏸ 暂停';
  rp.timer=setInterval(()=>{ index++; if(index>=rp.series.length-1){index=rp.series.length-1;clearInterval(rp.timer);rp.timer=null;this.textContent='▶ 播放';}drawECG(index); },120);
});

/* ---- 今日 token 运势 ---- */
function daySeed(){ const d=new Date(); return d.getFullYear()*10000+(d.getMonth()+1)*100+d.getDate(); }
function uhash(n){ n=Math.imul(n^(n>>>15),0x27d4eb2d); n=n^(n>>>13); return (n>>>0)/4294967296; }
function renderFortune(){
  const seed=daySeed(), r=k=>uhash(seed*(k+7));
  const yi=['宜重构','宜写测试','宜删废代码','宜提交','宜读文档','宜改名','宜早睡','宜喝口水','宜拆函数','宜加注释'];
  const ji=['忌 rm -rf','忌深夜上线','忌动数据库','忌裸奔 main','忌盲信 AI','忌硬编码','忌跳过测试','忌复制粘贴','忌不留缓存'];
  const poem=['token 如流水，缓存尚可留。','一日肝到夜，bug 自然来。','代码千行，缓存一响，黄金万两。','commit 之前，三思而后行。','算力烧不尽，春风吹又生。','多喝热水，少写 any。','重构像减肥，明天再说。'];
  const total=lastTotal||0, cr=DATA.cache_read||0, cRatio=total?cr/total:0;
  const score=Math.max(12,Math.min(99,Math.round(45+cRatio*40+r(3)*20-10)));
  const grade=score>=88?'大吉':score>=72?'中吉':score>=58?'吉':score>=44?'末吉':'凶';
  const pick=(arr,k)=>arr[Math.floor(r(k)*arr.length)];
  document.getElementById('f-date').textContent=new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'});
  document.getElementById('fortune').innerHTML=
    '<div class=f-head><div class=f-grade>'+grade+'</div><div class=f-score>运势 <b style="color:var(--ink);font-size:16px">'+score+'</b> / 100</div></div>'
    +'<div class=f-bar><i style="width:'+score+'%"></i></div>'
    +'<div class=f-yj><span class=f-yi><b>宜</b>'+pick(yi,1)+'</span><span class=f-ji><b>忌</b>'+pick(ji,2)+'</span></div>'
    +'<div class=f-poem>'+pick(poem,4)+'</div>';
}

/* ---- 3D 鼠标倾斜卡：仅处理指针所在卡片 ---- */
(function(){
  if(window.matchMedia('(prefers-reduced-motion: reduce)').matches||window.matchMedia('(pointer: coarse)').matches)return;
  let active=null,raf=0,mx=0,my=0;
  document.addEventListener('pointermove',e=>{if(document.documentElement.dataset.motion!=='full')return;mx=e.clientX;my=e.clientY;active=e.target.closest('.card');if(!raf)raf=requestAnimationFrame(()=>{raf=0;if(!active)return;const r=active.getBoundingClientRect(),dx=(mx-(r.left+r.width/2))/(r.width/2),dy=(my-(r.top+r.height/2))/(r.height/2);active.style.transform='rotateX('+Math.max(-1.6,Math.min(1.6,-dy*1.6)).toFixed(2)+'deg) rotateY('+Math.max(-1.6,Math.min(1.6,dx*1.6)).toFixed(2)+'deg)';});},{passive:true});
  document.addEventListener('pointerout',e=>{const card=e.target.closest('.card');if(card&&!card.contains(e.relatedTarget)){card.style.transform='';if(active===card)active=null;}},{passive:true});
  addEventListener('tk-motion-change',e=>{if(e.detail.effective!=='full'){if(active)active.style.transform='';document.querySelectorAll('.card[style*="transform"]').forEach(card=>card.style.transform='');active=null;}});
})();

// 双击页面空白：模型色数据尘埃
(function(){
  document.addEventListener('dblclick',e=>{
    if(e.target.closest('button,input,label,a,.card,svg'))return;
    const cs=Object.values(DATA.colors||{});for(let i=0;i<38;i++){const d=document.createElement('i');d.style.cssText='position:fixed;z-index:110;pointer-events:none;left:'+e.clientX+'px;top:'+e.clientY+'px;width:'+(3+i%4)+'px;height:'+(3+i%4)+'px;border-radius:50%;background:'+(cs[i%Math.max(1,cs.length)]||'#7aa2f7')+';transition:transform .85s cubic-bezier(.15,.7,.2,1),opacity .85s';document.body.appendChild(d);requestAnimationFrame(()=>{const a=i/38*Math.PI*2,r=40+(i%9)*9;d.style.transform='translate('+Math.cos(a)*r+'px,'+Math.sin(a)*r+'px) scale(.2)';d.style.opacity='0';});setTimeout(()=>d.remove(),900);}
  });
})();

// 光标彗星：单 Canvas + 固定粒子池，不持续创建 DOM
(function(){
  const canvas=document.getElementById('comet-canvas'),ctx=canvas.getContext('2d'),particles=Array.from({length:28},()=>({life:0})),colors=Object.values(DATA.colors||{});let cursor=0,raf=0,last=0,allocated=false;
  function release(){if(raf)cancelAnimationFrame(raf);raf=0;particles.forEach(p=>p.life=0);canvas.width=1;canvas.height=1;allocated=false;}
  function resize(){if(document.documentElement.dataset.motion!=='full'){release();return;}const dpr=Math.min(1.5,devicePixelRatio||1),maxPixels=8000000,scale=Math.min(dpr,Math.sqrt(maxPixels/Math.max(1,innerWidth*innerHeight)));canvas.width=Math.max(1,Math.round(innerWidth*scale));canvas.height=Math.max(1,Math.round(innerHeight*scale));canvas.style.width=innerWidth+'px';canvas.style.height=innerHeight+'px';ctx.setTransform(scale,0,0,scale,0,0);allocated=true;}
  function tick(){raf=0;ctx.clearRect(0,0,innerWidth,innerHeight);let alive=false;particles.forEach(p=>{if(p.life<=0)return;p.life-=.055;p.x+=p.vx;p.y+=p.vy;p.vy+=.015;const a=Math.max(0,p.life);ctx.globalAlpha=a;ctx.fillStyle=p.color;ctx.shadowColor=p.color;ctx.shadowBlur=8;ctx.beginPath();ctx.arc(p.x,p.y,p.size*a,0,Math.PI*2);ctx.fill();alive=true;});ctx.globalAlpha=1;ctx.shadowBlur=0;if(alive&&!document.hidden)raf=requestAnimationFrame(tick);}
  function spawn(e){if(document.documentElement.dataset.motion!=='full'||document.hidden)return;const now=performance.now();if(now-last<38)return;last=now;const p=particles[cursor++%particles.length];p.x=e.clientX;p.y=e.clientY;p.vx=-.6+(cursor%5)*.3;p.vy=.7+(cursor%7)*.18;p.size=2+(cursor%4)*.55;p.life=1;p.color=colors.length?colors[cursor%colors.length]:'#7aa2f7';if(!raf)raf=requestAnimationFrame(tick);}
  resize();addEventListener('resize',resize,{passive:true});addEventListener('tk-motion-change',e=>e.detail.effective==='full'?resize():release());document.addEventListener('pointermove',spawn,{passive:true});document.addEventListener('visibilitychange',()=>{if(document.hidden){release();}else if(document.documentElement.dataset.motion==='full')resize();});
})();
document.addEventListener('visibilitychange',()=>{if(document.hidden){if(raceTimer){clearInterval(raceTimer);raceTimer=null;document.getElementById('race-play').textContent='▶ 播放';}if(rp.timer){clearInterval(rp.timer);rp.timer=null;document.getElementById('replay-play').textContent='▶ 播放';}if(_stripT){clearInterval(_stripT);_stripT=null;}}else if(_ach&&lazyState.badges?.rendered&&!_stripT)runAchievementStrip();});

// 滚到深处出现返航火箭
(function(){const r=document.getElementById('rocket');window.addEventListener('scroll',()=>r.classList.toggle('on',scrollY>innerHeight*.9),{passive:true});r.addEventListener('click',()=>{if(motionDisabled()){scrollTo({top:0,behavior:'auto'});return;}r.classList.remove('launch');void r.offsetWidth;r.classList.add('launch');setTimeout(()=>{scrollTo({top:0,behavior:scrollBehavior()});r.classList.remove('launch');},360);});})();

/* URL 可恢复当前视图；旧版 #day/#week/#month 仍兼容 */
applyMods();
initLazyRendering();
restoringView=true;restoreViewFromURL();invalidateDerived();renderFilters();render();restoringView=false;syncViewURL();
