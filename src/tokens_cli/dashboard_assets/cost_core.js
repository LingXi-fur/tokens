/* ---- 共享费用纯核心 Shared CostCore ----
   Dashboard 费用数学的唯一纯核心，由 dashboard.js 薄包装调用。
   classic script IIFE，先于使用方加载，只暴露 globalThis.CostCore。
   纯核心边界：不读 DATA/state/localStorage/DOM/i18n，不做日期范围展开；
   compute() 只接收账本 cost、日期集合 days、模型 identity 集合 models 与
   已净化的价格 config。所有公式与 dashboard.js 抽取前逐字一致：
   BigInt×10^6 单价、金额分母 10^12、安全整数行、拆分累计、uncertain 整行
   不计价、hidden 不猜价、用户 entry 整条优先、未知 schema 不支持、
   total_incomplete 合同、half-up 舍入。 */
(function(global){
'use strict';
const COST_PARTS=['input','output','cache_read','cache_write','thoughts'];
const COST_SAFE_MAX=9007199254740991; // 2^53-1，单行 parts/total/calls 必须是 JS 安全整数；多行总和用 BigInt 精确累加
const COST_VERSION=1,COST_MAX_ENTRIES=4000;
/* 官方公开参考价（USD／百万 Token，2026-10-12 核对）：只读叠加层，非渠道实际扣费。
   key=精确模型名整串匹配；rates 顺序同 COST_PARTS；''=官网未公布不得填 0；
   tier/limit 仅溯源展示。页面不主动请求 vendor URL。 */
const COST_REFERENCE={
  date:'2026-10-12',currency:'USD',
  vendors:{
    openai:{label:'OpenAI',url:'https://developers.openai.com/api/docs/pricing'},
    deepseek:{label:'DeepSeek',url:'https://api-docs.deepseek.com/quick_start/pricing'},
    zai:{label:'Z.ai',url:'https://docs.z.ai/guides/overview/pricing'}
  },
  prices:{
    'gpt-6.1-sol':{vendor:'openai',rates:['2','10','0.10','2.50',''],tier:'Standard 短上下文档 ≤272K'},
    'gpt-6-sol':{vendor:'openai',rates:['2','10','0.20','2.50',''],tier:'Standard 短上下文档 ≤272K'},
    'gpt-5.6-sol':{vendor:'openai',rates:['4','20','0.40','5',''],tier:'Standard 短上下文档 ≤272K'},
    'gpt-5.6-luna':{vendor:'openai',rates:['0.20','1.20','0.02','0.25',''],tier:'Standard 短上下文档 ≤272K'},
    'gpt-5.6-terra':{vendor:'openai',rates:['2','12','0.20','2.50',''],tier:'Standard 短上下文档 ≤272K'},
    'deepseek-flash':{vendor:'deepseek',rates:['0.30','1.20','0.006','',''],tier:'峰时基准（off-peak 五折）'},
    'deepseek-v4-flash':{vendor:'deepseek',rates:['0.30','1.20','0.006','',''],tier:'峰时基准（off-peak 五折；官网注明由 V4.1-Flash 按同价服务）'},
    'deepseek-v4-pro':{vendor:'deepseek',rates:['1.32','3.96','0.044','',''],tier:'峰时基准（off-peak 五折）'},
    'glm-5.2':{vendor:'zai',rates:['1.40','4.40','0.26','',''],tier:'Z.ai 国际美元参考，非国内智谱同价'},
    'glm-5.3':{vendor:'zai',rates:['1.40','4.40','0.26','',''],tier:'Z.ai 国际美元参考，非国内智谱同价'}
  }
};
function costCurrencySymbol(currency){return currency==='USD'?'$':'¥';}
/* 价格：非负十进制字符串，最多 6 位小数，上限 1e9；BigInt 缩放 10^6；''=待定价，0=免费 */
function costParseRate(value){
  const s=String(value===null||value===undefined?'':value).trim();
  if(s==='')return {ok:true,empty:true};
  if(!/^\d{1,12}(\.\d{1,6})?$/.test(s))return {ok:false};
  const [int,frac='']=s.split('.');
  const scaled=BigInt((int+frac).padEnd(int.length+6,'0'));
  if(scaled>1000000000000000n)return {ok:false};
  return {ok:true,scaled};
}
function costSanitizeEntryRates(rates){
  if(!Array.isArray(rates)||rates.length!==COST_PARTS.length)return null;
  const clean=[];
  for(const value of rates){
    if(value===''||value===null||value===undefined){clean.push('');continue;}
    const parsed=costParseRate(value);
    if(!parsed.ok)return null;
    clean.push(parsed.empty?'':String(value).trim());
  }
  return clean;
}
function costSanitizeConfig(raw){
  if(!raw||typeof raw!=='object'||Array.isArray(raw))return null;
  if(raw.v!==COST_VERSION||(raw.currency!=='CNY'&&raw.currency!=='USD'))return null;
  if(Object.prototype.hasOwnProperty.call(raw,'reference')&&typeof raw.reference!=='boolean')return null;
  const prices=raw.prices;
  if(!prices||typeof prices!=='object'||Array.isArray(prices))return null;
  const keys=Object.keys(prices);
  if(keys.length>COST_MAX_ENTRIES)return null;
  const out={};
  for(const key of keys){
    let tuple;try{tuple=JSON.parse(key);}catch(e){return null;}
    if(!Array.isArray(tuple)||tuple.length!==2||typeof tuple[0]!=='string'||!tuple[0]||typeof tuple[1]!=='string'||!tuple[1])return null;
    const entry=prices[key];
    if(!entry||typeof entry!=='object'||Array.isArray(entry))return null;
    const rates=costSanitizeEntryRates(entry.rates);
    if(!rates)return null;
    const note=entry.note==null?'':String(entry.note).replace(/[\u0000-\u001f\u007f]/g,'').slice(0,120);
    out[key]={rates,note};
  }
  return {v:COST_VERSION,currency:raw.currency,reference:raw.reference===true,prices:out};
}
function costDefaultConfig(){return {v:COST_VERSION,currency:'USD',reference:true,prices:{}};}
/* scaled 以 10^12 为分母；half-up 取整显示 */
function costMoneyText(scaled,currency,precise){
  const symbol=costCurrencySymbol(currency);
  if(scaled<=0n)return symbol+'0'+(precise?'.0000':'.00');
  const places=precise?4:2,divisor=10n**BigInt(12-places);
  const units=(scaled+divisor/2n)/divisor;
  if(units===0n)return symbol+'<0.'+(precise?'0001':'01');
  const whole=units/10n**BigInt(places),frac=units%10n**BigInt(places);
  const group=bi=>bi.toString().replace(/\B(?=(\d{3})+(?!\d))/g,',');
  return symbol+group(whole)+'.'+frac.toString().padStart(places,'0');
}
function costSafeInt(value){return typeof value==='number'&&Number.isInteger(value)&&value>=0&&value<=COST_SAFE_MAX?value:null;}
/* 精确金额：10^12 定标 BigInt 转十进制字符串，最多 12 位小数、去尾零；免费为 '0'，绝不走 Number */
function costExactMoney(scaled){
  if(scaled<=0n)return '0';
  const digits=scaled.toString().padStart(13,'0'),whole=digits.slice(0,-12),frac=digits.slice(-12).replace(/0+$/,'');
  return frac?whole+'.'+frac:whole;
}
function costModelKey(entry){return JSON.stringify([entry.source,entry.model]);}
function costReferenceFor(model){
  if(model.hidden||!Object.prototype.hasOwnProperty.call(COST_REFERENCE.prices,model.model))return null;
  return COST_REFERENCE.prices[model.model];
}
function costEffectivePrice(model,config){
  if(model.hidden)return {entry:null,reference:null};
  const key=costModelKey(model);
  if(Object.prototype.hasOwnProperty.call(config.prices,key))return {entry:config.prices[key],reference:null};
  const reference=config.currency==='USD'&&config.reference===true?costReferenceFor(model):null;
  return {entry:reference?{rates:reference.rates,note:''}:null,reference};
}
/* 纯计算：cost=账本（DATA.cost 形状）；days=Set('YYYY-MM-DD')；models=Set(identity)；
   config=已净化价格（costSanitizeConfig 输出形状）。范围由调用方展开。 */
function costCompute(cost,scope){
  const days=scope.days,models=scope.models,config=scope.config;
  if(!cost||typeof cost!=='object'||Array.isArray(cost))return {supported:false};
  if(cost.schema!==1||!Array.isArray(cost.components)||!Array.isArray(cost.models)||!Array.isArray(cost.rows))return {supported:false};
  const partIndex=COST_PARTS.map(name=>cost.components.indexOf(name));
  const totalIncomplete=cost.total_incomplete===true; // 可选：部分日志总量不可用，不显示完整 Token 总量
  const byIndex=new Map();
  let totalCalls=0n,totalTokens=0n,unknownCalls=0n,unknownTokens=0n,invalidRows=0;
  const addUnknown=(calls,tokens)=>{unknownCalls+=BigInt(calls);unknownTokens+=BigInt(tokens);};
  // 非法行不丢覆盖：可读 calls/total 计入未知（读不出按 1 次调用保守计），绝不计费
  const invalidUnknown=(calls,tokens)=>{totalCalls+=BigInt(calls);totalTokens+=BigInt(tokens);addUnknown(calls,tokens);};
  for(const row of cost.rows){
    if(!Array.isArray(row)||row.length<5){invalidRows++;invalidUnknown(1,0);continue;}
    const day=row[0],idx=row[1],parts=row[2],reported=row[3],calls=row[4],uncertain=row[5];
    const safeCalls=costSafeInt(calls),safeTotal=costSafeInt(reported);
    const partsValid=Array.isArray(parts)&&partIndex.every(i=>i<0||costSafeInt(parts[i])!==null);
    if(typeof day!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(day)||!Number.isInteger(idx)||idx<0||idx>=cost.models.length||safeCalls===null||safeTotal===null||!partsValid){
      invalidRows++;
      invalidUnknown(safeCalls===null?1:safeCalls,safeTotal===null?0:safeTotal);
      continue;
    }
    const model=cost.models[idx];
    if(!model||typeof model!=='object'||typeof model.source!=='string'||typeof model.model!=='string'||typeof model.identity!=='string'){invalidRows++;invalidUnknown(safeCalls,safeTotal);continue;}
    if(!days.has(day)||!models.has(model.identity))continue;
    totalCalls+=BigInt(safeCalls);totalTokens+=BigInt(safeTotal);
    if(uncertain===true){addUnknown(safeCalls,safeTotal);continue;} // 口径未确认：整行不计费，不猜
    // 后端可把同桶拆成多行：不假设 day/index/mask 唯一，全部行求和；BigInt 累加，总和可超 2^53-1 且精确
    let acc=byIndex.get(idx);
    if(!acc){acc={partSums:[0n,0n,0n,0n,0n],calls:0n,tokens:0n};byIndex.set(idx,acc);}
    for(let c=0;c<COST_PARTS.length;c++){const i=partIndex[c];if(i>=0)acc.partSums[c]+=BigInt(parts[i]||0);}
    acc.calls+=BigInt(safeCalls);acc.tokens+=BigInt(safeTotal);
  }
  const entries=[];
  for(const [idx,acc] of byIndex){
    const model=cost.models[idx];
    const hasUsage=acc.partSums.some(v=>v>0n);
    if(!hasUsage)continue;
    const key=costModelKey(model);
    const effective=costEffectivePrice(model,config),configured=effective.entry;
    const rates=COST_PARTS.map((name,c)=>{
      if(model.hidden||!configured)return null;
      const parsed=costParseRate(configured.rates[c]);
      return parsed.ok&&!parsed.empty?parsed.scaled:null;
    });
    const rateTexts=COST_PARTS.map((name,c)=>configured&&!model.hidden?String(configured.rates[c]||''):'');
    const activeParts=acc.partSums.map(v=>v>0n);
    const fullPriced=!model.hidden&&activeParts.every((on,c)=>!on||rates[c]!==null);
    let costScaled=0n;
    if(fullPriced)for(let c=0;c<COST_PARTS.length;c++)if(activeParts[c])costScaled+=acc.partSums[c]*rates[c];
    entries.push({key,model,partSums:acc.partSums.slice(),activeParts,rates,rateTexts,costScaled,fullPriced,hidden:!!model.hidden,calls:acc.calls,tokens:acc.tokens,note:configured?configured.note:'',reference:effective.reference});
  }
  const tokenSum=e=>e.partSums.reduce((a,b)=>a+b,0n);
  entries.sort((a,b)=>{const d=a.costScaled>b.costScaled?-1:a.costScaled<b.costScaled?1:tokenSum(b)>tokenSum(a)?1:tokenSum(b)<tokenSum(a)?-1:0;return d||a.model.model.localeCompare(b.model.model);});
  let subtotal=0n,pricedCount=0,pendingCount=0,pendingTokens=0n,hasCacheWrite=false,maxCost=0n;
  entries.forEach(e=>{
    if(e.partSums[3]>0n)hasCacheWrite=true;
    if(e.costScaled>maxCost)maxCost=e.costScaled;
    if(e.fullPriced){subtotal+=e.costScaled;pricedCount++;}
    else {pendingCount++;pendingTokens+=tokenSum(e);}
  });
  const anyPriced=pricedCount>0;
  const fullEstimate=!totalIncomplete&&entries.length>0&&pendingCount===0&&unknownCalls===0n&&unknownTokens===0n&&invalidRows===0;
  const referenceCount=entries.filter(e=>e.reference).length;
  return {supported:true,currency:config.currency,referenceCount,totalIncomplete,entries,subtotal,anyPriced,fullEstimate,pricedCount,pendingCount,pendingTokens,totalCalls,totalTokens,unknownCalls,unknownTokens,invalidRows,hasCacheWrite,maxCost};
}
global.CostCore={
  parts:COST_PARTS,
  reference:COST_REFERENCE,
  VERSION:COST_VERSION,
  maxEntries:COST_MAX_ENTRIES,
  parseRate:costParseRate,
  sanitizeEntryRates:costSanitizeEntryRates,
  sanitizeConfig:costSanitizeConfig,
  defaultConfig:costDefaultConfig,
  modelKey:costModelKey,
  referenceFor:costReferenceFor,
  effectivePrice:costEffectivePrice,
  moneyText:costMoneyText,
  moneyExact:costExactMoney,
  compute:costCompute
};
})(globalThis);
