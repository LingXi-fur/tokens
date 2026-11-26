// Data-first layer. Never persists prices or computes monetary amounts itself.
import { buildUsageModel } from './usage-data.js';

export function createUsagePanel(payload, { element, table, text, number, name, selected, dark, changed = () => {} }) {
  const core = globalThis.CostCore, $ = id => document.getElementById(id);
  let config = core.defaultConfig(), filtered = false, draft = null, focus = null;
  const partLabels = () => [text('输入', 'Input'), text('输出', 'Output'), text('缓存读', 'Cache read'), text('缓存写', 'Cache write'), text('思考', 'Thoughts')];
  const money = value => 'USD ' + core.moneyText(value, 'USD', true).replace(/^\$/, '');
  const views = () => ({ all: buildUsageModel(payload, { core, config }),
    detail: buildUsageModel(payload, { core, config, models: filtered ? selected() : payload.models }) });
  function partial(view, usage) {
    return !view.supported || view.totalIncomplete || view.invalidRows > 0 || view.unknownCalls > 0n ||
      usage?.unknownCalls > 0n || usage?.unknownTokens > 0n || (view.entries || []).some(entry => !entry.fullPriced);
  }
  function amount(view) {
    if (!view.supported) return text('账本不可用', 'Ledger unavailable');
    if (!view.anyPriced) return text('暂无可计价金额', 'No priced amount');
    // The subtotal is furnished by the shared core, not recomputed in this UI.
    return money(view.subtotal);
  }
  function coverage(view, usage) {
    const pending = (view.entries || []).filter(entry => !entry.fullPriced);
    const unknownCalls = usage?.unknownCalls > (view.unknownCalls || 0n) ? usage.unknownCalls : view.unknownCalls || 0n;
    const unknownTokens = usage?.unknownTokens > (view.unknownTokens || 0n) ? usage.unknownTokens : view.unknownTokens || 0n;
    const bits = [];
    if (pending.length) bits.push(number(pending.length) + ' ' + text('项待定价', 'unpriced entries'));
    if (unknownCalls > 0n || unknownTokens > 0n) bits.push(number(unknownCalls) + ' ' + text('次口径未知', 'unknown calls') + ' / ' + number(unknownTokens) + ' Token');
    if (view.invalidRows) bits.push(text('存在无效账本行', 'Invalid ledger rows'));
    if (view.totalIncomplete) bits.push(text('载入量不完整', 'Loaded totals incomplete'));
    return bits.join(' · ') || text('载入账本计价完整', 'Loaded ledger fully priced');
  }
  function render() {
    const { all, detail } = views();
    $('report-date').textContent = text('合成示例 · 报告日 ', 'Synthetic · Report day ') + (all.date || '—') + ' · UTC';
    $('today-tokens').textContent = all.today.hasRows ? number(all.today.total) : text('无记录', 'No records');
    $('today-calls').textContent = number(all.today.calls) + ' ' + text('次调用 · 全部模型', 'calls · all models');
    $('cost-label').textContent = partial(all.loaded.cost, all.loaded) ? text('累计 · 已定价小计', 'Loaded · priced subtotal') : text('累计 · 估算总额', 'Loaded · estimated total');
    $('loaded-cost').textContent = amount(all.loaded.cost);
    $('cost-coverage').textContent = coverage(all.loaded.cost, all.loaded);
    $('rail-range').textContent = (all.from || '—') + ' — ' + (all.until || '—') + ' · ' + text('仅载入区间', 'loaded range only');
    $('scope-all').setAttribute('aria-pressed', String(!filtered));
    $('scope-filtered').setAttribute('aria-pressed', String(filtered));
    $('usage-scope').textContent = (filtered ? text('当前场景筛选', 'Selected scene models') : text('全部模型', 'All models')) + ' · ' + (detail.date || '—') + ' · UTC';
    $('today-summary').textContent = detail.today.hasRows ? number(detail.today.total) + ' Token · ' + number(detail.today.calls) + ' ' + text('次调用', 'calls') :
      (all.today.hasRows ? text('当前筛选无记录。', 'No records for selected models.') : text('报告日无记录；不回落到其他日期。', 'No report-day records; no fallback to another day.'));
    $('today-models').replaceChildren(table(detail.today.entries,
      [text('模型', 'Model'), 'Token', text('占比', 'Share'), ...partLabels(), text('口径未知 Token', 'Unknown tokens')],
      entry => [modelLabel(entry.identity), number(entry.tokens), entry.share.toFixed(2) + '%',
        ...entry.parts.map(value => entry.trustedCalls > 0n || value > 0n ? number(value) : '—'), number(entry.unknownTokens)]));
    const ledger = detail.loaded.cost;
    $('cost-summary').textContent = (detail.from || '—') + ' — ' + (detail.until || '—') + ' · ' +
      (partial(ledger, detail.loaded) ? text('已定价小计 ', 'Priced subtotal ') : text('估算总额 ', 'Estimated total ')) + amount(ledger) + ' · ' + coverage(ledger, detail.loaded);
    $('reference-note').textContent = text('官方 USD 参考价核验：', 'USD reference rates checked: ') + core.reference.date + text('；非账单实付、不自动换汇。单价调整仅当前页面有效。', '; not actual billed cost, no currency conversion. Edits last only for this page.');
    const rows = detail.loaded.costEntries.flatMap(entry => [
      ...entry.priced.map(price => ({ entry, price })),
      ...(entry.unknownCalls > 0n || entry.unknownTokens > 0n || !entry.priced.length ? [{ entry, price: null }] : [])
    ]);
    $('cost-models').replaceChildren(table(rows, [text('模型 / 计数来源', 'Model / counting source'), 'Token', ...partLabels(), text('估算 USD', 'Estimated USD'), text('状态 / 来源', 'Status / rate source')], ({ entry, price }) => {
      if (!price) return [name(entry.identity) + ' / ' + text('未知口径汇总', 'Unknown coverage'), number(entry.unknownTokens),
        ...core.parts.map(() => '—'), '—', text('不计价 · ', 'Not priced · ') + number(entry.unknownCalls) + ' ' + text('次未知调用', 'unknown calls')];
      const effective = core.effectivePrice(price.model, config);
      const state = price.fullPriced ? text('已定价', 'Priced') : text('待定价', 'Unpriced');
      const source = price.reference ? text('官方参考', 'Official reference') : effective.entry ? text('页面内单价', 'Page rates') : text('未设单价', 'No rates set');
      return [name(entry.identity) + ' / ' + price.model.source, number(price.tokens), ...price.partSums.map(number),
        price.fullPriced ? money(price.costScaled) : '—', state + ' · ' + source];
    }));
    changed();
  }
  function modelLabel(identity) {
    const node = element('span', undefined, 'usage-model'), mark = element('span', undefined, 'model-dot');
    mark.style.background = payload.colors?.[dark() ? 'dark' : 'light']?.[identity] || '#888888';
    node.append(mark, element('span', name(identity))); return node;
  }
  function close() { draft = null; $('prices').close(); }
  function fields() {
    $('price-fields').replaceChildren(); $('price-error').textContent = '';
    for (const descriptor of payload.cost?.models || []) {
      if (descriptor.hidden) continue;
      const key = core.modelKey(descriptor), effective = core.effectivePrice(descriptor, draft);
      const group = element('fieldset'), legend = element('legend', descriptor.model + ' / ' + descriptor.source);
      group.append(legend);
      const grid = element('div', undefined, 'price-grid');
      core.parts.forEach((part, index) => {
        const label = element('label', partLabels()[index]), input = element('input');
        input.type = 'text'; input.inputMode = 'decimal'; input.autocomplete = 'off';
        input.value = String(effective.entry?.rates[index] ?? ''); input.dataset.priceKey = key; input.dataset.part = index;
        input.addEventListener('input', () => {
          if (!Object.hasOwn(draft.prices, key)) draft.prices[key] = { rates: core.parts.map((_, i) => String(effective.entry?.rates[i] ?? '')), note: '' };
          draft.prices[key].rates[index] = input.value;
        });
        label.append(input); grid.append(label);
      });
      group.append(grid); $('price-fields').append(group);
    }
  }
  $('scope-all').addEventListener('click', () => { filtered = false; render(); });
  $('scope-filtered').addEventListener('click', () => { filtered = true; render(); });
  $('prices-open').addEventListener('click', () => { focus = $('prices-open'); draft = structuredClone(config); fields(); $('prices').showModal(); $('prices-close').focus(); });
  $('prices-close').addEventListener('click', close); $('prices-cancel').addEventListener('click', close);
  $('prices').addEventListener('close', () => { draft = null; if (focus?.isConnected) focus.focus(); });
  $('prices-reset').addEventListener('click', () => {
    if (confirm(text('恢复全部官方参考价？仅修改当前草稿，保存后才生效。', 'Restore all reference rates? This changes the draft only, until applied.'))) { draft = core.defaultConfig(); fields(); }
  });
  $('price-form').addEventListener('submit', event => {
    event.preventDefault();
    for (const entry of Object.values(draft.prices)) for (const rate of entry.rates) if (!core.parseRate(rate).ok) {
      $('price-error').textContent = text('单价须为非负数，最多 6 位小数，最大 1000000000；可留空。', 'Rates must be nonnegative, at most 6 decimals and 1000000000; blank is allowed.'); return;
    }
    config = core.sanitizeConfig(draft); close(); render();
  });
  return { render, model: () => views(), close };
}
