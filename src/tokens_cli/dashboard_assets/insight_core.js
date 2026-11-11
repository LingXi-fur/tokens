/* ---- 洞察纯派生核心 InsightCore ----
   三个首屏洞察共用：今日 vs 昨日同时刻的累计赛跑、按日模型份额流、活跃日历与连续天数。
   只接收已经按模型筛选过的数字数组/映射与 ISO 日期；自带 UTC 日期运算，无需注入。
   不读取 DOM、DATA/state、存储、语言或当前时间；文案、配色与绘制留在 dashboard.js。 */
(function(global){
'use strict';
function isoDayValid(value){
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
  const [y,m,d]=value.split('-').map(Number),dt=new Date(Date.UTC(y,m-1,d));
  return dt.getUTCFullYear()===y&&dt.getUTCMonth()===m-1&&dt.getUTCDate()===d;
}
function addDays(day,delta){
  const [y,m,d]=day.split('-').map(Number),dt=new Date(Date.UTC(y,m-1,d+delta));
  return dt.getUTCFullYear()+'-'+String(dt.getUTCMonth()+1).padStart(2,'0')+'-'+String(dt.getUTCDate()).padStart(2,'0');
}
function dayIndex(day){const [y,m,d]=day.split('-').map(Number);return Math.round(Date.UTC(y,m-1,d)/86400000);}
/* 周一为 0。 */
function weekdayMonday(day){return ((dayIndex(day)+3)%7+7)%7;}
function num(value){const n=Number(value);return Number.isFinite(n)&&n>0?n:0;}
function hours24(values){const out=new Array(24).fill(0);if(Array.isArray(values))for(let i=0;i<24;i++)out[i]=num(values[i]);return out;}
/* 25 个整点边界上的累计值：cum[k] = 前 k 个小时之和。 */
function cumulative(hours){const out=[0];for(let i=0;i<24;i++)out.push(out[i]+hours[i]);return out;}
function cumulativeAt(cum,hours,hour,minute){return cum[hour]+hours[hour]*minute/60;}
function percentChange(current,previous){return previous>0?(current-previous)/previous*100:null;}

/* 今日 vs 昨日同时刻：生成时刻 hour:minute 是截止点。
   今日只取已记录的数据（截止点之后本就没有数据）；昨日与基线在截止小时内按分钟线性折算，
   避免把昨日整小时和今日刚开始的小时作不对等比较。 */
function paceRace({today,yesterday,baseline,hour,minute}){
  if(!Number.isInteger(hour)||hour<0||hour>23)return null;
  const mm=Number.isInteger(minute)&&minute>=0&&minute<60?minute:0;
  const t=hours24(today),y=hours24(yesterday);
  const tCum=cumulative(t),yCum=cumulative(y);
  const todayTotal=tCum[24],yesterdayAt=cumulativeAt(yCum,y,hour,mm),yesterdayTotal=yCum[24];
  const days=Array.isArray(baseline)?baseline.map(hours24):[];
  let base=null;
  if(days.length){
    const avg=new Array(24).fill(0);
    days.forEach(day=>day.forEach((v,i)=>avg[i]+=v/days.length));
    const bCum=cumulative(avg);
    base={days:days.length,cum:bCum,atCutoff:cumulativeAt(bCum,avg,hour,mm),total:bCum[24]};
    base.delta=percentChange(todayTotal,base.atCutoff);
  }
  const delta=percentChange(todayTotal,yesterdayAt);
  let lead='even';
  if(yesterdayAt<=0)lead=todayTotal>0?'new':'idle';
  else if(Math.abs(delta)>=0.5)lead=delta>0?'ahead':'behind';
  /* 按昨日曲线形状外推全天：今日 × 昨日全天/昨日同时刻；只有昨日截止前已有用量才给出。 */
  const projection=yesterdayAt>0&&todayTotal>0?todayTotal*yesterdayTotal/yesterdayAt:null;
  /* 今日领先/落后的最大幅度出现在哪个整点：供“今天在几点反超”之类的叙述。 */
  let crossover=null;
  for(let k=1;k<=hour;k++){
    const before=tCum[k-1]-yCum[k-1],after=tCum[k]-yCum[k];
    if(before<=0&&after>0)crossover=k;
  }
  return {hour,minute:mm,cutoff:hour+mm/60,
    today:{cum:tCum.slice(0,hour+2),total:todayTotal},
    yesterday:{cum:yCum,atCutoff:yesterdayAt,total:yesterdayTotal},
    baseline:base,delta,lead,projection,crossover};
}

/* 连续日历日（含两端）；非法或倒序时返回空数组，最长 1500 天防止病态输入。 */
function continuousDays(since,until){
  if(!isoDayValid(since)||!isoDayValid(until)||since>until)return [];
  const out=[];for(let day=since;day<=until&&out.length<1500;day=addDays(day,1))out.push(day);
  return out;
}

/* 按日模型份额流。rows: {day:{model:tokens}}；models 决定图层自下而上的顺序。
   mode='share' 为 100% 份额；mode='volume' 为居中基线的河流图（silhouette）。
   smooth 为居中移动平均窗口（1 = 不平滑），只影响图形，raw 保留原始每日值。 */
function shareStream({days,rows,models,mode,smooth}){
  const list=Array.isArray(days)?days.filter(isoDayValid):[];
  const order=Array.isArray(models)?models.filter((m,i,a)=>typeof m==='string'&&a.indexOf(m)===i):[];
  const win=Number.isInteger(smooth)&&smooth>1?Math.min(smooth,30):1;
  const kind=mode==='volume'?'volume':'share';
  const raw=list.map(day=>{const src=rows&&rows[day]||{},out={};order.forEach(m=>out[m]=num(src[m]));return out;});
  const totals=raw.map(r=>order.reduce((s,m)=>s+r[m],0));
  /* 居中窗口：两端自动收窄，避免尾随窗口在首日只剩一天原始值而形成“夹点”。 */
  const back=Math.floor((win-1)/2),ahead=win-1-back;
  const smoothed=raw.map((_,i)=>{const out={},from=Math.max(0,i-back),to=Math.min(raw.length-1,i+ahead),n=to-from+1;order.forEach(m=>{let s=0;for(let j=from;j<=to;j++)s+=raw[j][m];out[m]=s/n;});return out;});
  const sums=smoothed.map(r=>order.reduce((s,m)=>s+r[m],0));
  const max=Math.max(0,...sums);
  const present=order.filter(m=>raw.some(r=>r[m]>0));
  const layers=present.map(model=>({model,y0:[],y1:[],share:[]}));
  list.forEach((_,i)=>{
    const sum=sums[i];
    let acc=kind==='share'?0:-sum/2;
    layers.forEach(layer=>{
      const v=smoothed[i][layer.model],h=kind==='share'?(sum>0?v/sum:0):v;
      layer.y0.push(acc);acc+=h;layer.y1.push(acc);
      layer.share.push(sum>0?v/sum:0);
    });
  });
  /* 每个模型份额峰值所在日：“这一层在哪天最宽”。 */
  layers.forEach(layer=>{let best=-1,at=null;layer.share.forEach((s,i)=>{if(s>best){best=s;at=list[i];}});layer.peak={day:at,share:Math.max(0,best)};});
  return {mode:kind,smooth:win,days:list,raw,totals,max,layers,
    domain:kind==='share'?[0,1]:[-max/2,max/2]};
}

/* 活跃日历：最后一列包含 endDay，周一为第一行；共 weeks 列。
   totals: {day:tokens}，first: 报告起始日（更早的格子标记为 outside）。
   色阶 1–4 取非零日的四分位，避免单个尖峰把其余日子压成同一色。 */
function quantile(sorted,q){if(!sorted.length)return 0;const pos=(sorted.length-1)*q,lo=Math.floor(pos),hi=Math.ceil(pos);return sorted[lo]+(sorted[hi]-sorted[lo])*(pos-lo);}
function activityCalendar({totals,endDay,weeks,first}){
  if(!isoDayValid(endDay))return null;
  const cols=Math.max(1,Math.min(60,Number.isInteger(weeks)?weeks:13));
  const lastMonday=addDays(endDay,-weekdayMonday(endDay)),start=addDays(lastMonday,-(cols-1)*7);
  const map=totals&&typeof totals==='object'?totals:{};
  const begin=isoDayValid(first)?first:null;
  const nonzero=Object.keys(map).filter(d=>isoDayValid(d)&&d<=endDay&&num(map[d])>0).map(d=>num(map[d])).sort((a,b)=>a-b);
  const cuts=[quantile(nonzero,.25),quantile(nonzero,.5),quantile(nonzero,.75)];
  const level=v=>v<=0?0:v<=cuts[0]?1:v<=cuts[1]?2:v<=cuts[2]?3:4;
  const cells=[],months=[];
  for(let c=0;c<cols;c++){
    const monday=addDays(start,c*7);
    for(let r=0;r<7;r++){
      const day=addDays(monday,r);
      if(day>endDay)break;
      const total=num(map[day]);
      cells.push({day,col:c,row:r,total,level:level(total),outside:!!begin&&day<begin});
      /* 月份标签落在含该月 1 日的列。 */
      if(day.slice(8)==='01')months.push({col:c,month:day.slice(0,7),monthNumber:Number(day.slice(5,7))});
    }
  }
  /* 首列补标所在月，但若两列内就有月初标签则省略，避免文字重叠。 */
  if(!months.length||months[0].col>2)months.unshift({col:0,month:start.slice(0,7),monthNumber:Number(start.slice(5,7))});
  return {start,end:endDay,weeks:cols,cells,months,cuts,stats:streakStats(map,endDay,begin)};
}

/* 连续活跃天数。current 以 endDay 结束；若 endDay 尚无用量（当天可能还没开工），从前一天起算并标记。 */
function streakStats(totals,endDay,first){
  const map=totals&&typeof totals==='object'?totals:{};
  const active=Object.keys(map).filter(d=>isoDayValid(d)&&d<=endDay&&num(map[d])>0).sort();
  const activeSet=new Set(active);
  let longest={length:0,start:null,end:null},run=0,runStart=null,prev=null;
  active.forEach(day=>{
    if(prev&&addDays(prev,1)===day)run++;else{run=1;runStart=day;}
    if(run>longest.length)longest={length:run,start:runStart,end:day};
    prev=day;
  });
  let anchor=endDay,pending=false;
  if(!activeSet.has(anchor)){anchor=addDays(endDay,-1);pending=true;}
  let current=0,cursor=anchor;
  while(activeSet.has(cursor)){current++;cursor=addDays(cursor,-1);}
  let busiest=null;
  active.forEach(day=>{const v=num(map[day]);if(!busiest||v>busiest.total)busiest={day,total:v};});
  const weekday=new Array(7).fill(0);active.forEach(day=>weekday[weekdayMonday(day)]+=num(map[day]));
  const topWeekday=active.length?weekday.indexOf(Math.max(...weekday)):null;
  const span=isoDayValid(first)&&first<=endDay?dayIndex(endDay)-dayIndex(first)+1:null;
  return {activeDays:active.length,spanDays:span,current:{length:current,start:current?addDays(cursor,1):null,end:current?anchor:null,pendingToday:pending},
    longest,busiest,weekdayTotals:weekday,topWeekday};
}

global.InsightCore=Object.freeze({isoDayValid,addDays,weekdayMonday,continuousDays,paceRace,shareStream,activityCalendar,streakStats,percentChange});
})(globalThis);
