/* Monthly budgets use the same scaled money as CostCore; no browser state here. */
(function(global){
'use strict';
function create({CostCore,calendar,isoDayValid}){
  const scale=1000000000000n,maxMonths=120;
  function parseAmount(value){
    if(typeof value!=='string'||value.length>32||!/^\d+(?:\.\d{1,2})?$/.test(value))return {ok:false};
    const [whole,fraction='']=value.split('.'),cents=BigInt(whole)*100n+BigInt(fraction.padEnd(2,'0'));
    if(cents<=0n||cents>100000000n)return {ok:false};
    return {ok:true,scaled:cents*(scale/100n),text:(cents/100n).toString()+'.'+(cents%100n).toString().padStart(2,'0')};
  }
  function object(value){return !!value&&typeof value==='object'&&!Array.isArray(value);}
  function sanitizeConfig(raw){
    if(!object(raw)||Object.keys(raw).sort().join(',')!=='budgets,v'||raw.v!==1||!object(raw.budgets))return null;
    const months=Object.keys(raw.budgets);
    if(months.length>maxMonths)return null;
    const budgets={};
    for(const month of months){
      if(!calendar.calendarMonthParse(month)||!object(raw.budgets[month]))return null;
      const currencies=Object.keys(raw.budgets[month]);
      if(!currencies.length||currencies.some(currency=>currency!=='USD'&&currency!=='CNY'))return null;
      const entries={};
      for(const currency of currencies){
        const parsed=parseAmount(raw.budgets[month][currency]);
        if(!parsed.ok)return null;
        entries[currency]=parsed.text;
      }
      budgets[month]=entries;
    }
    return {v:1,budgets};
  }
  function compute({day,timezoneKnown,range,cost,config,amount}){
    const reasons=[],limit=reason=>{if(!reasons.includes(reason))reasons.push(reason);};
    const result={status:'limited',reasons,month:null,daysInMonth:null,subtotal:null,todayLoaded:null,
      closedSubtotal:null,windowDays:0,futureDays:0,remaining:null,percentTenths:null,scenario:null,threshold:null};
    if(!isoDayValid(day)||!calendar.calendarMonthParse(day.slice(0,7))){limit('date');return result;}
    const month=day.slice(0,7),monthData=calendar.calendarMonthData([],[],month,null);
    const dayNumber=Number(day.slice(8,10)),days=monthData.cells.map(cell=>cell.day);
    result.month=month;result.daysInMonth=monthData.daysInMonth;
    result.windowDays=Math.min(7,dayNumber-1);result.futureDays=monthData.daysInMonth-dayNumber+1;
    if(!timezoneKnown)limit('timezone');
    const boundary=value=>value===null||isoDayValid(value);
    if(!object(range)||!Object.prototype.hasOwnProperty.call(range,'since')||!Object.prototype.hasOwnProperty.call(range,'until')||
      !boundary(range.since)||!boundary(range.until)||(range.since!==null&&range.since>days[0])||
      (range.until!==null&&range.until<day))limit('range');
    const models=new Set(Array.isArray(cost?.models)?cost.models.filter(model=>object(model)&&typeof model.identity==='string').map(model=>model.identity):[]);
    const monthDays=new Set(days.slice(0,dayNumber)),closedDays=new Set(days.slice(0,dayNumber-1));
    const window=new Set(days.slice(Math.max(0,dayNumber-1-result.windowDays),dayNumber-1));
    const view=CostCore.compute(cost,{days:monthDays,models,config});
    if(!view.supported){limit('unsupported');return result;}
    result.subtotal=view.subtotal;
    if(view.invalidRows)limit('invalid');
    if(view.totalIncomplete)limit('incomplete');
    let hasRows=false;
    for(const row of cost.rows){
      if(!Array.isArray(row))continue;
      if(typeof row[0]==='string'&&!isoDayValid(row[0]))limit('invalid');
      if(!monthDays.has(row[0]))continue;
      // CostCore owns row validation and pricing; these flags also cover zero rows
      // that have no cost entry and uncertain rows whose counters are both zero.
      hasRows=true;
      if(row[5]===true)limit('uncertain');
      if(Array.isArray(row[2])&&row[2].every(value=>value===0)&&row[3]>0)limit('incomplete');
    }
    if(view.unknownCalls>0n||view.unknownTokens>0n)limit('uncertain');
    if(!hasRows)limit('no-records');
    if(view.pendingCount)limit('pricing');
    if(result.windowDays<3)limit('sample');
    const selected=days=>CostCore.compute(cost,{days,models,config}).subtotal;
    result.todayLoaded=selected(new Set([day]));result.closedSubtotal=selected(closedDays);
    const parsed=parseAmount(amount);
    if(reasons.length)return result;
    if(!parsed.ok){result.status='unset';return result;}
    const subtotal=result.subtotal;
    result.status='ready';result.remaining=parsed.scaled-subtotal;
    result.percentTenths=(subtotal*1000n*2n+parsed.scaled)/(parsed.scaled*2n);
    result.threshold=subtotal>=parsed.scaled?'over':subtotal*5n>=parsed.scaled*4n?'warning':'normal';
    const count=BigInt(result.windowDays);
    result.scenario={numerator:result.closedSubtotal*count+selected(window)*BigInt(result.futureDays),denominator:count};
    return result;
  }
  function scenarioMoney(value,currency){
    const divisor=value.denominator*(scale/100n),cents=(value.numerator+divisor/2n)/divisor;
    // Currency formatting only: the rational is rounded directly to cents once.
    if(cents===0n&&value.numerator>0n)return (currency==='USD'?'$':'¥')+'<0.01';
    return CostCore.moneyText(cents*(scale/100n),currency);
  }
  function savedEntries(raw){
    const config=sanitizeConfig(raw);if(!config)return [];
    return Object.keys(config.budgets).sort().reverse().flatMap(month=>['USD','CNY'].filter(currency=>Object.prototype.hasOwnProperty.call(config.budgets[month],currency)).map(currency=>({month,currency,amount:config.budgets[month][currency]})));
  }
  function removeEntry(raw,target){
    const config=sanitizeConfig(raw);
    if(!config||!object(target)||!calendar.calendarMonthParse(target.month)||!['USD','CNY'].includes(target.currency)||!parseAmount(target.amount).ok||config.budgets[target.month]?.[target.currency]!==target.amount)return {ok:false};
    delete config.budgets[target.month][target.currency];
    if(!Object.keys(config.budgets[target.month]).length)delete config.budgets[target.month];
    return {ok:true,config};
  }
  return {parseAmount,sanitizeConfig,compute,scenarioMoney,savedEntries,removeEntry,maxMonths};
}
global.BudgetCore={create};
})(globalThis);
