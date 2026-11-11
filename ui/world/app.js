import { createWorld } from './scene.js';
import { buildSceneModel } from './scene-data.js';
import { createUsagePanel } from './usage-panel.js';

const $ = id => document.getElementById(id);
let language = 'zh', dark = matchMedia('(prefers-color-scheme: dark)').matches;
let lessMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
let model, world = null, hovered = null, returnFocus = null, view = 'world', disposed = false;
const enabled = new Set(WORLD_DATA.models || []);
const labels = new Map();
const number = value => new Intl.NumberFormat(language === 'zh' ? 'zh-CN' : 'en-US').format(value);
const text = (zh, en) => language === 'zh' ? zh : en;
const name = id => WORLD_DATA.pretty?.[id] || id;
const chapters = ['summit','meadow','village'];
let chapter = 0;
function element(tag, content, className) {
  const node = document.createElement(tag);
  if (content !== undefined) node.textContent = content;
  if (className) node.className = className;
  return node;
}
function action(content, id, className) {
  const node = element('button', content, className);
  node.type = 'button'; node.dataset.object = id;
  node.addEventListener('click', () => inspect(id, node));
  node.addEventListener('focus', () => preview(id));
  node.addEventListener('blur', () => preview(null));
  node.addEventListener('pointerenter', () => preview(id));
  node.addEventListener('pointerleave', () => preview(null));
  return node;
}
function itemById(id) {
  if (!id) return null;
  if (id.startsWith('project:')) return model.projects.find(p => 'project:' + p.id === id);
  if (id.startsWith('day:')) return model.rows.find(p => 'day:' + p.period === id);
  return model.hotspots.find(p => p.id === id);
}
function itemLabel(id) {
  if(id==='overview:tokens')return text('载入 Token','Loaded tokens');
  if(id==='overview:calls')return text('调用次数','Calls');
  if(id==='overview:scope')return text('观察范围','Loaded range');
  const item=itemById(id); return item?.label || item?.period || '';
}
function preview(id) {
  hovered=id; world?.select(id);
  const item=itemById(id);
  $('tooltip').hidden=!item || $('detail').open;
  if(!item)return;
  $('tooltip').replaceChildren(element('strong',itemLabel(id)),element('span',
    id==='overview:scope'?model.from+' — '+model.until:
      number(item.total ?? item.value)+' '+(id==='overview:calls'?text('次调用','calls'):'Token')));
  if(id.startsWith('project:'))$('tooltip').append(element('div',number(item.days.length)+' '+text('个活跃日 · 点击查看','active days · click to inspect')));
}
function table(rows, headings, render) {
  const node=element('table'), head=element('thead'), line=element('tr'), body=element('tbody');
  headings.forEach(label=>{const th=element('th',label);th.scope='col';line.append(th);});head.append(line);
  rows.forEach(row=>{const tr=element('tr');render(row).forEach(value=>{const td=element('td');typeof value==='string'?td.textContent=value:td.append(value);tr.append(td);});body.append(tr);});
  node.append(head,body);return node;
}
function inspect(id, origin) {
  const item=itemById(id);if(!item)return;
  returnFocus=origin || document.activeElement;
  $('detail-title').textContent=itemLabel(id);$('detail-body').replaceChildren();
  $('tooltip').hidden=true;
  if(id==='overview:scope') {
    $('detail-body').append(element('p',model.from+' — '+model.until),element('p',text('仅载入合成数据。高度是导航，不是用量坐标。','Synthetic loaded data only. Elevation is navigation, not a usage axis.')));
  } else {
    $('detail-body').append(element('p',number(item.total ?? item.value),'detail-stat'));
    if(id.startsWith('project:')) {
      $('detail-body').append(element('p',number(item.days.length)+' '+text('个活跃日；不推算项目费用。','active days; no project cost estimates.')));
      $('detail-body').append(table(item.rows,[text('日期','Date'),'Token'],row=>[row.period,number(row.total)]));
    } else if(id.startsWith('day:')) {
      $('detail-body').append(element('p',number(item.calls)+' '+text('次调用','calls')));
      for(const [m,value] of Object.entries(item.models)) {
        const row=element('div',undefined,'contribution'), dot=element('span',undefined,'model-dot');
        dot.style.background=WORLD_DATA.colors?.[dark?'dark':'light']?.[m] || '#888888';
        row.append(dot,element('span',name(m)),element('b',number(value)));$('detail-body').append(row);
      }
    } else $('detail-body').append(element('p',text('当前模型筛选下的载入聚合，不代表完整账单。','Loaded aggregates for selected models, not a complete bill.')));
  }
  if(!$('detail').open)$('detail').showModal();
  $('detail-close').focus();world?.select(id);
}
function renderProjects() {
  const query=$('project-search').value.trim().toLocaleLowerCase();
  const items=model.projects.filter(p=>p.label.toLocaleLowerCase().includes(query));
  $('project-list').replaceChildren();
  for(const p of items){const row=element('div',undefined,'project-row');row.append(action(p.label,'project:'+p.id),element('span',number(p.total)+' Token'));$('project-list').append(row);}
  if(!items.length)$('project-list').append(element('p',text('当前范围没有匹配项目。','No matching projects in this range.')));
}
function layoutRail(){
  const top=document.querySelector('.bar').getBoundingClientRect().bottom+12;
  $('core-stats').style.top=top+'px';
  document.documentElement.style.setProperty('--rail-bottom',($('core-stats').getBoundingClientRect().bottom+16)+'px');
}
function render() {
  model=buildSceneModel(WORLD_DATA,{models:[...enabled]});
  $('total').textContent=number(model.total);$('calls').textContent=number(model.calls);
  $('range').textContent=model.from?model.from+' — '+model.until:text('没有载入日期','No loaded dates');
  $('project-count').textContent=number(model.projects.length)+' '+text('个可用项目 · 村庄展示 ','available projects · village shows ')+number(model.houses.length);
  $('summit-actions').replaceChildren(...model.hotspots.map(item=>action(itemLabel(item.id),item.id)));
  $('station-list').replaceChildren(...model.stations.map(item=>action(item.period.slice(5),item.id)));
  $('model-filters').replaceChildren();
  for(const m of WORLD_DATA.models || []) {
    const button=element('button'),dot=element('span',undefined,'model-dot');button.type='button';
    button.setAttribute('aria-pressed',String(enabled.has(m)));
    dot.style.background=WORLD_DATA.colors?.[dark?'dark':'light']?.[m] || '#888888';
    button.append(dot,element('span',name(m)));button.addEventListener('click',()=>{
      const focusIndex=[...$('model-filters').children].indexOf(button);
      enabled.has(m)?enabled.delete(m):enabled.add(m);render();$('model-filters').children[focusIndex]?.focus();
    });$('model-filters').append(button);
  }
  $('day-table').replaceChildren(table(model.rows,[text('日期','Date'),'Token',text('调用','Calls')],row=>[action(row.period,'day:'+row.period),number(row.total),number(row.calls)]));
  renderProjects();usagePanel.render();
  const labelItems=[...model.hotspots,...model.stations,...model.houses];
  const nextIds=new Set(labelItems.map(item=>item.id));
  for(const [id,node] of labels)if(!nextIds.has(id)){node.remove();labels.delete(id);}
  for(const item of labelItems){
    if(!labels.has(item.id)){const node=action(itemLabel(item.id),item.id,'world-label');node.hidden=true;labels.set(item.id,node);$('labels').append(node);}
    labels.get(item.id).textContent=itemLabel(item.id);
  }
  world?.update(model);scroll();
}
function projectLabels(points) {
  const visible=new Map(points.map(p=>[p.id,p]));
  const occupied=[];
  const rail=$('core-stats').getBoundingClientRect();
  for(const [id,node] of labels){
    const point=visible.get(id),match=chapter===0?id.startsWith('overview:'):chapter===1?id.startsWith('day:'):id.startsWith('project:');
    // Suppress labels behind the reading column and above the fixed navigation.
    const readingBottom=document.querySelectorAll('.chapter-copy')[chapter]?.getBoundingClientRect().bottom || 0;
    const blocked=point && point.x<(innerWidth<700?innerWidth*0.93:innerWidth*0.39)&&point.y<readingBottom&&point.y>0;
    const collides=point&&occupied.some(p=>Math.abs(p.x-point.x)<140&&Math.abs(p.y-point.y)<38);
    const underRail=point&&point.x>rail.left-90&&point.x<rail.right+90&&point.y>rail.top-20&&point.y<rail.bottom+40;
    node.hidden=!point||!match||blocked||underRail||point.y<135||collides||view!=='world';
    if(!node.hidden){node.style.left=point.x+'px';node.style.top=point.y+'px';occupied.push(point);}
    node.classList.toggle('active',id===hovered);
  }
}
function scroll() {
  const end=Math.max(1,$('village').offsetTop-96);
  const progress=Math.min(1,Math.max(0,scrollY/end));
  chapter=progress<0.3?0:progress<0.7?1:2;
  world?.scroll(progress);
  $('progress').style.width=(progress*100)+'%';$('chapter-number').textContent='0'+(chapter+1);
  document.querySelectorAll('[data-chapter]').forEach(node=>{Number(node.dataset.chapter)===chapter?node.setAttribute('aria-current','location'):node.removeAttribute('aria-current');});
  $('labels').hidden=scrollY >= $('data-view').offsetTop;
  // Data section covers the scene and must not leave floating controls above it.
  if($('data-view').getBoundingClientRect().top<innerHeight*0.6)$('labels').hidden=true;
}
function fallback(reason) {
  world?.dispose();world=null;document.body.classList.add('fallback');$('labels').hidden=true;
  $('status').textContent=reason==='context'?text('3D 场景中断，数据与操作仍可用。','3D context interrupted. Data and controls remain available.'):
    text('当前环境使用完整数据视图；3D 未启用。','Full data view active. 3D is unavailable here.');
  view='data';$('view-toggle').textContent=text('数据视图','Data view');
}
function setLanguage() {
  document.documentElement.lang=language==='zh'?'zh-CN':'en';
  document.querySelectorAll('[data-i18n]').forEach(node=>{
    const value=node.dataset.i18n.split('|')[language==='zh'?0:1];
    const lines=value.split('<br>');node.replaceChildren();lines.forEach((line,i)=>{if(i)node.append(element('br'));node.append(document.createTextNode(line));});
  });$('language').textContent=language==='zh'?'EN':'中文';render();
}
$('detail-close').addEventListener('click',()=>$('detail').close());
$('detail').addEventListener('close',()=>{world?.select(null);returnFocus?.isConnected&&returnFocus.focus();});
$('theme').addEventListener('click',()=>{dark=!dark;document.body.classList.toggle('dark',dark);world?.theme();render();});
$('language').addEventListener('click',()=>{language=language==='zh'?'en':'zh';setLanguage();});
$('motion').setAttribute('aria-pressed',String(lessMotion));
$('motion').addEventListener('click',()=>{lessMotion=!lessMotion;$('motion').setAttribute('aria-pressed',String(lessMotion));world?.motion();});
matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change',event=>{lessMotion=event.matches;$('motion').setAttribute('aria-pressed',String(lessMotion));world?.motion();});
matchMedia('(forced-colors: active)').addEventListener('change',event=>{if(event.matches)fallback('forced');});
$('view-toggle').addEventListener('click',()=>{
  if(!world){$('data-view').scrollIntoView();return;}
  view=view==='world'?'data':'world';document.body.classList.toggle('data-mode',view==='data');
  $('view-toggle').textContent=view==='world'?text('数据视图','Data view'):text('返回世界','Back to world');
  view==='data'?$('data-view').scrollIntoView():$(chapters[chapter]).scrollIntoView();world?.leave();scroll();
});
$('projects-open').addEventListener('click',()=>{$('data-view').scrollIntoView();$('project-search').focus({preventScroll:true});});
$('project-search').addEventListener('input',renderProjects);
window.addEventListener('scroll',scroll,{passive:true});
window.addEventListener('resize',()=>{layoutRail();scroll();});
window.addEventListener('pointermove',event=>{
  if(event.target.closest('button,a,input,dialog,.chapter-copy,.data-view,.bar,.core-stats')){
    world?.leave();
    const object=event.target.closest('[data-object]');
    if(object)preview(object.dataset.object);
    return;
  }
  if(view==='world')world?.move(event);
});
window.addEventListener('pointerout',event=>{if(event.pointerType!=='touch'&&!event.relatedTarget)world?.leave();});
let down=null;
window.addEventListener('pointerdown',event=>{down={x:event.clientX,y:event.clientY,id:event.pointerId};});
window.addEventListener('pointerup',event=>{
  if(!down||event.pointerId!==down.id||Math.hypot(event.clientX-down.x,event.clientY-down.y)>8)return;
  down=null;if(event.target.closest('button,a,input,dialog,.chapter-copy,.data-view,.bar,.core-stats')||view!=='world')return;
  const id=world?.pick(event);if(id)event.pointerType==='touch'&&hovered!==id?preview(id):inspect(id,event.target);
});
const usagePanel=createUsagePanel(WORLD_DATA,{element,table,text,number,name,selected:()=>[...enabled],dark:()=>dark,changed:layoutRail});
document.body.classList.toggle('dark',dark);
render();
// Let the exact-value HTML paint before expensive WebGL initialization.
async function initializeWorld(){
  if(disposed){window.TokensWorld.ready=true;return;}
  try {
    if(!matchMedia('(forced-colors: active)').matches){
      world=createWorld($('world'),{dark:()=>dark,reduced:()=>lessMotion,hover:preview,project:projectLabels,fail:fallback});
      const initializing=world;
      initializing.update(model);scroll();
      await initializing.initialize?.();
    }else fallback('forced');
  }catch(error){fallback('unavailable');}
  window.TokensWorld.ready=true;
}
// Small synthetic-only inspection surface for repeatable tests; no private values/logging.
window.TokensWorld={model:()=>model,usage:()=>usagePanel.model(),metrics:()=>world?.metrics()||null,view:()=>view,ready:false,
  dispose:()=>{disposed=true;world?.dispose();world=null;},project:id=>labels.get(id)?.getBoundingClientRect().toJSON(),
  probes:()=>world?.probes()||[],pick:(x,y)=>world?.pick({clientX:x,clientY:y})||null};
requestAnimationFrame(()=>setTimeout(initializeWorld,0));
