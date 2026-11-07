import { villageSite } from './terrain.js';

// Pure projection of existing aggregate fields. Never invent project costs.
export function stableSlot(id, size = 24) {
  let hash = 2166136261;
  for (const char of String(id)) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  return (hash >>> 0) % size;
}

export function buildSceneModel(payload, { models = payload.models || [], days = null } = {}) {
  const enabled = new Set(models);
  const focus = days === null ? null : new Set(days);
  const rows = (payload.day || []).filter(row => !focus || focus.has(row.period)).map(row => {
    const values = Object.fromEntries(Object.entries(row.models || {}).filter(([model]) => enabled.has(model)));
    return { period: row.period, total: Object.values(values).reduce((sum, value) => sum + value, 0),
      calls: Object.entries(row.model_calls || {}).reduce((sum, [model, value]) => sum + (enabled.has(model) ? value : 0), 0), models: values };
  }).sort((a, b) => a.period.localeCompare(b.period));
  const catalog = new Map();
  for (const [day, detail] of Object.entries(payload.day_details || {})) {
    if (focus && !focus.has(day)) continue;
    for (const row of detail.cwds || detail.top_cwds || []) {
      const id = row[2] || row[0];
      const parts = Object.fromEntries(Object.entries(row[3] || {}).filter(([model]) => enabled.has(model)));
      const total = Object.values(parts).reduce((sum, value) => sum + value, 0);
      if (!id || total <= 0) continue;
      if (!catalog.has(id)) catalog.set(id, { id, label: row[0], total: 0, days: [], rows: [] });
      const project = catalog.get(id);
      project.total += total; project.days.push(day); project.rows.push({ period: day, total, models: parts });
    }
  }
  const projects = [...catalog.values()].map(project => ({ ...project,
    days: [...new Set(project.days)].sort(), rows: project.rows.sort((a, b) => a.period.localeCompare(b.period))
  })).sort((a, b) => b.total - a.total || a.label.localeCompare(b.label));
  // Resolve slots against the unfiltered catalog, so filters cannot move surviving houses.
  const allIds = [...new Set(Object.values(payload.day_details || {}).flatMap(detail =>
    (detail.cwds || detail.top_cwds || []).map(row => row[2] || row[0]).filter(Boolean)))].sort();
  const slots = new Map(), occupied = new Set();
  for (const id of allIds) {
    let slot = stableSlot(id, Math.max(24, allIds.length));
    while (occupied.has(slot)) slot = (slot + 1) % Math.max(24, allIds.length);
    occupied.add(slot); slots.set(id, slot);
  }
  const houses = projects.filter(project => slots.get(project.id) < 24).map(project => {
    const slot = slots.get(project.id);
    return { ...project, id: 'project:' + project.id, projectId: project.id,
      position: [...villageSite(slot).position], rotation: villageSite(slot).rotation };
  });
  const stations = rows.slice(-9).map(row => ({ ...row, id: 'day:' + row.period, label: row.period }));
  const total = rows.reduce((sum, row) => sum + row.total, 0);
  const calls = rows.reduce((sum, row) => sum + row.calls, 0);
  return { total, calls, rows, projects, houses, stations,
    models: models.filter(model => (payload.models || []).includes(model)),
    hotspots: [{ id: 'overview:tokens', label: 'Token', value: total },
      { id: 'overview:calls', label: 'Calls', value: calls },
      { id: 'overview:scope', label: 'Scope', value: rows.length }],
    limited: Object.values(payload.day_details || {}).some(detail => !detail.cwds && detail.top_cwds),
    from: rows[0]?.period || '', until: rows.at(-1)?.period || '' };
}
