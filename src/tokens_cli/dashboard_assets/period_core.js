/* ---- 环比纯派生核心 PeriodCore ----
   只接收周期键、粒度、生成日、覆盖上限与日期范围；自带 UTC 日期运算，无需注入，
   便于按函数抽取的 Node 合约测试直接前置本文件。
   不读取 DOM、DATA/state、存储、语言或当前时间；标签文案与按日求和留在 dashboard.js。 */
(function(global){
'use strict';
function isoDayValid(value){
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
  const [y,m,d]=value.split('-').map(Number),dt=new Date(Date.UTC(y,m-1,d));
  return dt.getUTCFullYear()===y&&dt.getUTCMonth()===m-1&&dt.getUTCDate()===d;
}
function addISODays(day,delta){
  const [y,m,d]=day.split('-').map(Number),dt=new Date(Date.UTC(y,m-1,d+delta));
  return dt.getUTCFullYear()+'-'+String(dt.getUTCMonth()+1).padStart(2,'0')+'-'+String(dt.getUTCDate()).padStart(2,'0');
}
function periodDays(period,gran){
  if(gran==='day')return [period];
  if(!isoDayValid(period))return [];
  const out=[];
  if(gran==='week'){for(let i=0;i<7;i++)out.push(addISODays(period,i));return out;}
  const first=period.slice(0,8)+'01';
  for(let day=first;day.slice(0,7)===first.slice(0,7);day=addISODays(day,1))out.push(day);
  return out;
}
/* 返回 null（不可比）或 {mode,currentDays,previousDays}：
   - whole：本期完整且已结束；无范围时两侧 days 为 null（直接用周期行合计），
     有范围时两侧都是完整周期日列表（上期不按偏移截断，合计与模型拆分同口径）。
   - same-point：本期含生成日，按生成日前已过天数对齐上期同偏移日。
   - partial：日期范围裁剪了本期，按同历日偏移对齐上期。 */
function comparisonWindow({gran,currentPeriod,previousPeriod,generated=null,coverageUntil=null,scopeDays=null}){
  const fullCurrent=periodDays(currentPeriod,gran),fullPrevious=periodDays(previousPeriod,gran);
  const scoped=scopeDays==null?fullCurrent:scopeDays;
  if(!scoped.length)return null;
  const open=!!generated&&scoped.includes(generated)&&(!coverageUntil||coverageUntil>=generated);
  if(open&&gran==='day')return null;
  const clipped=scoped.length<fullCurrent.length;
  if(!open&&!clipped){
    return scopeDays==null?{mode:'whole',currentDays:null,previousDays:null}
      :{mode:'whole',currentDays:fullCurrent,previousDays:fullPrevious};
  }
  const currentDays=open?scoped.filter(day=>day<generated):scoped;
  if(!currentDays.length)return null;
  const offsets=new Map(fullCurrent.map((day,offset)=>[day,offset]));
  const previousDays=currentDays.map(day=>{const offset=offsets.get(day);return offset==null?null:fullPrevious[offset];}).filter(Boolean);
  if(!previousDays.length)return null;
  return {mode:open?'same-point':'partial',currentDays,previousDays};
}
function percentChange(current,previous){
  if(!(previous>0))return null;
  return (current-previous)/previous*100;
}
/* 与 dashboard 的 topModelOf(models,false) 同口径：值降序，平局保留插入顺序。 */
function topModel(models){
  const entries=Object.entries(models||{}).sort((a,b)=>b[1]-a[1]);
  return entries.length?entries[0]:null;
}
function attributionParts(current,previous,models){
  return models.map(model=>{const curr=current[model]||0,prev=previous[model]||0;return {model,curr,prev,delta:curr-prev};})
    .sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta)||a.model.localeCompare(b.model));
}
function dominantShift(current,previous){
  const prevTop=topModel(previous),currTop=topModel(current);
  if(!prevTop||!currTop||prevTop[0]===currTop[0])return null;
  return {from:prevTop[0],to:currTop[0]};
}
global.PeriodCore=Object.freeze({periodDays,comparisonWindow,percentChange,topModel,attributionParts,dominantShift});
})(globalThis);
