/* ---- 日历纯派生核心 CalendarCore ----
   只接收记录和范围；共享日期/安全整数助手由 Dashboard 注入。
   不读取 DOM、DATA/state、存储、语言或当前时间。 */
(function(global){
'use strict';
function create({isoDayValid,addISODays,dailySafeInt}){
function calendarMonthParse(month){
  if(typeof month!=='string')return null;
  const match=/^(\d{4})-(\d{2})$/.exec(month);
  if(!match)return null;
  const year=Number(match[1]),monthNumber=Number(match[2]);
  if(year<100||year>9999||monthNumber<1||monthNumber>12)return null;
  return {year:year,monthIndex:monthNumber-1,monthNumber:monthNumber};
}
function calendarIsLeapYear(year){return year%4===0&&(year%100!==0||year%400===0);}
function calendarDaysInMonth(year,monthIndex){
  const lengths=[31,calendarIsLeapYear(year)?29:28,31,30,31,30,31,31,30,31,30,31];
  return lengths[monthIndex];
}
function calendarWeekdayMonday(day){
  const parts=day.split('-'),year=Number(parts[0]),month=Number(parts[1]),date=Number(parts[2]);
  const adjusted=year-(month<=2?1:0),era=Math.floor(adjusted/400),yearOfEra=adjusted-era*400;
  const dayOfYear=Math.floor((153*(month+(month>2?-3:9))+2)/5)+date-1;
  const dayOfEra=yearOfEra*365+Math.floor(yearOfEra/4)-Math.floor(yearOfEra/100)+dayOfYear;
  const daysSinceEpoch=era*146097+dayOfEra-719468;
  return ((daysSinceEpoch+3)%7+7)%7;
}
function calendarMonthShift(month,delta){
  const parsed=calendarMonthParse(month);
  if(!parsed||!Number.isInteger(delta))return null;
  const total=parsed.year*12+parsed.monthIndex+delta;
  if(total<1200||total>119999)return null;
  return String(Math.floor(total/12)).padStart(4,'0')+'-'+String(total%12+1).padStart(2,'0');
}
function calendarBase(info,rows,generated){
  const until=info&&isoDayValid(info.until)?info.until:null;
  if(until)return {day:until,month:until.slice(0,7),basis:'range'};
  let latest=null;
  if(Array.isArray(rows))rows.forEach(row=>{
    const period=row&&row.period;
    if(isoDayValid(period)&&(!latest||period>latest))latest=period;
  });
  if(latest)return {day:latest,month:latest.slice(0,7),basis:'records'};
  if(isoDayValid(generated))return {day:generated,month:generated.slice(0,7),basis:'generated'};
  return {day:null,month:null,basis:'unavailable'};
}
function calendarRangeKey(info){
  if(!info)return '';
  return (info.preset||'')+'|'+(info.since||'')+'|'+(info.until||'');
}
function calendarIntensityLevel(tokens,max){
  if(tokens<=0n||max<=0n)return 0;
  if(tokens*4n<=max)return 1;
  if(tokens*2n<=max)return 2;
  if(tokens*4n<=max*3n)return 3;
  return 4;
}
function calendarMonthData(rows,models,month,coverage,range=null){
  const selectedModels=Array.from(new Set(Array.from(models||[]).filter(model=>typeof model==='string'&&model)));
  const parsed=calendarMonthParse(month);
  const rawFirst=coverage&&isoDayValid(coverage.first_day)?coverage.first_day:null;
  const rawLast=coverage&&isoDayValid(coverage.last_day)?coverage.last_day:null;
  const coverageFirst=rawFirst&&rawLast&&rawFirst<=rawLast?rawFirst:null;
  const coverageLast=coverageFirst?rawLast:null;
  const coverageInfo={first:coverageFirst,last:coverageLast,hasCoverage:!!coverageFirst};
  if(!parsed)return {valid:false,reason:'invalid-month',month:typeof month==='string'?month:null,year:null,monthIndex:null,monthNumber:null,daysInMonth:0,firstWeekday:null,weeks:[],cells:[],selectedModels:selectedModels,modelCount:selectedModels.length,coverage:coverageInfo,maxTokens:null,exactTokenDays:0,recordedDays:0,anyDayRows:0,boundaryMismatch:false};
  const daysInMonth=calendarDaysInMonth(parsed.year,parsed.monthIndex);
  const monthPrefix=month.slice(0,7);
  const firstDay=monthPrefix+'-01';
  const lastDay=monthPrefix+'-'+String(daysInMonth).padStart(2,'0');
  const firstWeekday=calendarWeekdayMonday(firstDay);
  const rangeSince=range&&isoDayValid(range.since)?range.since:null;
  const rangeUntil=range&&isoDayValid(range.until)?range.until:null;
  const byDay=new Map();
  if(Array.isArray(rows))for(const row of rows){
    const period=row&&row.period;
    if(!isoDayValid(period)||period<firstDay||period>lastDay)continue;
    let bucket=byDay.get(period);
    if(!bucket){bucket={models:new Map()};byDay.set(period,bucket);}
    const rowTokens=row.models&&typeof row.models==='object'?row.models:{};
    const rowCalls=row.model_calls&&typeof row.model_calls==='object'?row.model_calls:{};
    for(const model of selectedModels){
      const hasTokens=Object.prototype.hasOwnProperty.call(rowTokens,model);
      const hasCalls=Object.prototype.hasOwnProperty.call(rowCalls,model);
      if(!hasTokens&&!hasCalls)continue;
      let acc=bucket.models.get(model);
      if(!acc){acc={hasTokens:false,hasCalls:false,tokens:0n,calls:0n,tokensSafe:true,callsSafe:true};bucket.models.set(model,acc);}
      if(hasTokens){
        acc.hasTokens=true;
        const safe=dailySafeInt(rowTokens[model]);
        if(safe===null)acc.tokensSafe=false;else acc.tokens+=BigInt(safe);
      }
      if(hasCalls){
        acc.hasCalls=true;
        const safe=dailySafeInt(rowCalls[model]);
        if(safe===null)acc.callsSafe=false;else acc.calls+=BigInt(safe);
      }
    }
  }
  const cells=[];
  for(let dayNumber=1;dayNumber<=daysInMonth;dayNumber++){
    const day=monthPrefix+'-'+String(dayNumber).padStart(2,'0');
    const bucket=byDay.get(day);
    let selectedPresent=0,missingToken=0,missingCalls=0,unsafeToken=0,unsafeCalls=0,safeTokenModels=0,safeCallModels=0,tokensKnown=0n,callsKnown=0n;
    if(bucket)for(const model of selectedModels){
      const acc=bucket.models.get(model);
      if(!acc)continue;
      selectedPresent++;
      if(!acc.hasTokens)missingToken++;
      else if(!acc.tokensSafe)unsafeToken++;
      else{safeTokenModels++;tokensKnown+=acc.tokens;}
      if(!acc.hasCalls)missingCalls++;
      else if(!acc.callsSafe)unsafeCalls++;
      else{safeCallModels++;callsKnown+=acc.calls;}
    }
    const hasRecord=selectedPresent>0;
    const tokensAnyKey=safeTokenModels+unsafeToken>0;
    const callsAnyKey=safeCallModels+unsafeCalls>0;
    const tokensExact=hasRecord&&tokensAnyKey&&missingToken===0&&unsafeToken===0;
    const callsExact=hasRecord&&callsAnyKey&&missingCalls===0&&unsafeCalls===0;
    const noSelection=selectedModels.length===0;
    const tokenStatus=noSelection?'no-selection':!hasRecord?'no-record':!tokensAnyKey?'missing':unsafeToken>0?'unsafe':!tokensExact?'partial':tokensKnown===0n?'zero':'known';
    const callsStatus=noSelection?'no-selection':!hasRecord?'no-record':!callsAnyKey?'missing':unsafeCalls>0?'unsafe':!callsExact?'partial':callsKnown===0n?'zero':'known';
    const tokens=tokensAnyKey&&safeTokenModels>0?tokensKnown.toString():null;
    const calls=callsAnyKey&&safeCallModels>0?callsKnown.toString():null;
    const inCoverage=coverageFirst?(day>=coverageFirst&&day<=coverageLast):null;
    const inRange=!rangeSince||(day>=rangeSince&&(!rangeUntil||day<=rangeUntil));
    cells.push({day:day,hasAnyDayRow:!!bucket,hasRecord:hasRecord,inRange:inRange,inCoverage:inCoverage,outsideCoverageRecord:!!bucket&&inCoverage===false,tokens:tokens,calls:calls,tokenStatus:tokenStatus,callsStatus:callsStatus,tokensExact:tokensExact,callsExact:callsExact,zeroRecorded:tokensExact&&callsExact&&tokensKnown===0n&&callsKnown===0n,intensity:null,selectedPresent:selectedPresent,missingToken:missingToken,missingCalls:missingCalls,unsafeToken:unsafeToken,unsafeCalls:unsafeCalls});
  }
  let maxExact=null,exactTokenDays=0,recordedDays=0,anyDayRows=0,boundaryMismatch=false;
  for(const cell of cells){
    if(cell.tokensExact){exactTokenDays++;const value=cell.tokens===null?0n:BigInt(cell.tokens);if(maxExact===null||value>maxExact)maxExact=value;}
    if(cell.hasRecord)recordedDays++;
    if(cell.hasAnyDayRow)anyDayRows++;
    if(cell.outsideCoverageRecord)boundaryMismatch=true;
  }
  if(maxExact!==null)for(const cell of cells){
    if(cell.tokenStatus==='zero')cell.intensity=0;
    else if(cell.tokenStatus==='known')cell.intensity=calendarIntensityLevel(BigInt(cell.tokens),maxExact);
  }
  const weeks=[];let week=new Array(7).fill(null),slot=firstWeekday;
  for(const cell of cells){
    week[slot%7]=cell;slot++;
    if(slot%7===0){weeks.push(week);week=new Array(7).fill(null);}
  }
  if(slot%7!==0)weeks.push(week);
  return {valid:true,reason:null,month:monthPrefix,year:parsed.year,monthIndex:parsed.monthIndex,monthNumber:parsed.monthNumber,daysInMonth:daysInMonth,firstWeekday:firstWeekday,weeks:weeks,cells:cells,selectedModels:selectedModels,modelCount:selectedModels.length,coverage:coverageInfo,maxTokens:maxExact===null?null:maxExact.toString(),exactTokenDays:exactTokenDays,recordedDays:recordedDays,anyDayRows:anyDayRows,boundaryMismatch:boundaryMismatch};
}
/* 每次预览仅在局部 Map 复用旧月聚合；不缓存、不改写月格或精度口径。 */
function calendarStripDays(end){
  if(!isoDayValid(end)||!calendarMonthParse(end.slice(0,7)))return [];
  const days=[end];
  while(days.length<7){
    const previous=addISODays(days[0],-1).padStart(10,'0');
    if(!isoDayValid(previous)||!calendarMonthParse(previous.slice(0,7)))break;
    days.unshift(previous);
  }
  return days;
}
function calendarPreviewData(rows,models,end,month,coverage,range=null,expanded=false){
  const months=new Map(),selectedModels=Array.from(models||[]);
  const getMonth=key=>{
    if(!months.has(key))months.set(key,calendarMonthData(rows,selectedModels,key,coverage,range));
    return months.get(key);
  };
  const days=calendarStripDays(end).map(day=>{
    const data=getMonth(day.slice(0,7));
    return {...data.cells[Number(day.slice(8,10))-1]};
  });
  let max=0n;
  for(const cell of days)if(cell.tokensExact&&cell.tokens!==null){const value=BigInt(cell.tokens);if(value>max)max=value;}
  for(const cell of days)cell.intensity=cell.tokenStatus==='zero'?0:cell.tokenStatus==='known'?calendarIntensityLevel(BigInt(cell.tokens),max):null;
  const monthData=expanded&&calendarMonthParse(month)?getMonth(month):null;
  return {days:days,monthData:monthData,monthCount:months.size};
}
return {calendarMonthParse,calendarWeekdayMonday,calendarMonthShift,calendarBase,
  calendarRangeKey,calendarMonthData,calendarStripDays,calendarPreviewData};
}
global.CalendarCore={create};
})(globalThis);
