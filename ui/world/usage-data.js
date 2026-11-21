// Report-date and coverage projection. All monetary arithmetic belongs to CostCore.
function count(value) {
  return Number.isSafeInteger(value) && value >= 0 ? BigInt(value) : 0n;
}

export function reportDay(payload) {
  const value = String(payload.generated || '').slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return '';
  const parsed = new Date(value + 'T00:00:00Z');
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value ? value : '';
}

export function buildUsageModel(payload, { core, config, models = payload.models || [] } = {}) {
  const enabled = new Set(models);
  const allDays = [...new Set((payload.day || []).map(row => row.period))].sort();
  const date = reportDay(payload);
  function scope(days) {
    const included = new Set(days), byModel = new Map(), ledgerOnly = new Map();
    let total = 0n, calls = 0n, hasRows = false;
    for (const row of payload.day || []) {
      if (!included.has(row.period)) continue;
      for (const [identity, value] of Object.entries(row.models || {})) {
        if (!enabled.has(identity)) continue;
        hasRows = true;
        if (!byModel.has(identity)) byModel.set(identity, { identity, tokens: 0n, calls: 0n,
          parts: Array(5).fill(0n), unknownTokens: 0n, unknownCalls: 0n, billingCalls: 0n, trustedCalls: 0n });
        const entry = byModel.get(identity);
        entry.tokens += count(value); entry.calls += count(row.model_calls?.[identity]);
        total += count(value); calls += count(row.model_calls?.[identity]);
      }
    }
    const ledger = payload.cost;
    const monetary = core.compute(ledger, { days: included, models: enabled, config });
    if (monetary.supported) {
      const indices = core.parts.map(part => ledger.components.indexOf(part));
      for (const row of ledger.rows) {
        if (!Array.isArray(row) || row.length < 5 || !included.has(row[0]) ||
          typeof row[0] !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(row[0]) ||
          !Number.isInteger(row[1]) || row[1] < 0 || row[1] >= ledger.models.length) continue;
        const descriptor = ledger.models[row[1]];
        if (!descriptor || typeof descriptor.source !== 'string' || typeof descriptor.model !== 'string' || typeof descriptor.identity !== 'string') continue;
        if (!enabled.has(descriptor.identity)) continue;
        let entry = byModel.get(descriptor.identity);
        if (!entry) {
          if (!ledgerOnly.has(descriptor.identity)) ledgerOnly.set(descriptor.identity, { identity: descriptor.identity,
            tokens: 0n, calls: 0n, parts: Array(5).fill(0n), unknownTokens: 0n, unknownCalls: 0n, billingCalls: 0n, trustedCalls: 0n });
          entry = ledgerOnly.get(descriptor.identity);
          entry.tokens += count(row[3]); entry.calls += count(row[4]);
        }
        if (!Number.isSafeInteger(row[4]) || row[4] < 0 || !Number.isSafeInteger(row[3]) || row[3] < 0) continue;
        const valid = Array.isArray(row[2]) && indices.every(i => i < 0 || (Number.isSafeInteger(row[2][i]) && row[2][i] >= 0));
        entry.billingCalls += count(row[4]);
        if (row[5] === true || !valid) {
          entry.unknownTokens += count(row[3]); entry.unknownCalls += count(row[4]); continue;
        }
        entry.trustedCalls += count(row[4]);
        indices.forEach((index, part) => { if (index >= 0) entry.parts[part] += count(row[2][index]); });
      }
    }
    const priced = new Map();
    for (const entry of monetary.entries || []) {
      const identity = entry.model.identity;
      // More than one source can share a display identity: preserve each monetary entry.
      if (!priced.has(identity)) priced.set(identity, []);
      priced.get(identity).push(entry);
    }
    const entries = [...byModel.values()].map(entry => {
      const missingCalls = entry.calls > entry.billingCalls ? entry.calls - entry.billingCalls : 0n;
      entry.unknownCalls += missingCalls;
      const represented = entry.parts.reduce((sum, part) => sum + part, 0n) + entry.unknownTokens;
      if (entry.tokens > represented) entry.unknownTokens += entry.tokens - represented;
      return { ...entry, priced: priced.get(entry.identity) || [],
        share: total ? Number(entry.tokens * 10000n / total) / 100 : 0 };
    }).sort((a, b) => a.tokens === b.tokens ? a.identity.localeCompare(b.identity) : a.tokens > b.tokens ? -1 : 1);
    const costEntries = [...entries, ...[...ledgerOnly.values()].map(entry => ({ ...entry, priced: priced.get(entry.identity) || [] }))];
    return { total, calls, hasRows, entries, costEntries, cost: monetary,
      parts: entries.reduce((sums, entry) => sums.map((value, i) => value + entry.parts[i]), Array(5).fill(0n)),
      unknownTokens: entries.reduce((sum, entry) => sum + entry.unknownTokens, 0n),
      unknownCalls: entries.reduce((sum, entry) => sum + entry.unknownCalls, 0n) };
  }
  return { date, from: allDays[0] || '', until: allDays.at(-1) || '',
    today: scope(date ? [date] : []), loaded: scope(allDays) };
}
