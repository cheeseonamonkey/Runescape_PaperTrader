const $ = s => document.querySelector(s);
const gp = n => Number(n || 0).toLocaleString();
const pct = n => `${Number(n) >= 0 ? '+' : ''}${(Number(n || 0) * 100).toFixed(2)}%`;
const esc = s => String(s ?? '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const cls = n => Number(n) >= 0 ? 'up' : 'down';
const age = d => { const m = Math.max(0, Math.round((Date.now() - new Date(d)) / 60000)); return m < 60 ? `${m}m ago` : `${(m / 60).toFixed(1)}h ago`; };
let data, days = {days: []}, runs = {runs: []}, view = 'now', wallet = 'velocity';

const badge = s => `<span class="pill">${esc(s)}</span>`;
const runHealth = r => r?.health?.status || 'unknown';

function switcher() {
  return `<div class="wallet-tabs">${Object.values(data.wallets).map(w => `<button class="${w.id === wallet ? 'active' : ''}" onclick="selectWallet('${w.id}')">${esc(w.name)} <span class="${cls(w.return_pct)}">${pct(w.return_pct)}</span></button>`).join('')}</div>`;
}

function comparison() {
  const ws = Object.values(data.wallets);
  return `<section><div class="section-title"><h2>Wallet scoreboard</h2><span class="tiny">same 10M starting GP</span></div><div class="compare">${ws.map(w => `<div><b>${esc(w.name)}</b><strong class="${cls(w.return_pct)}">${gp(w.value_gp)} gp</strong><span>${pct(w.return_pct)} · ${w.positions.length} positions</span></div>`).join('')}</div></section>`;
}

function hero() {
  const w = data.wallets[wallet];
  const r = data.run || {};
  return `${switcher()}<section><div class="panel hero"><div class="row"><span class="muted">${esc(w.name.toUpperCase())} · MARK-TO-LIQUIDATION</span><b class="${cls(w.return_pct)}">${pct(w.return_pct)}</b></div><div class="value num">${gp(w.value_gp)} gp</div><p class="tiny thesis">${esc(w.thesis)}</p><div class="kpis"><div class="kpi"><b>${gp(w.cash_gp)}</b><span>cash</span></div><div class="kpi"><b class="${cls(w.realized_pnl_gp)}">${gp(w.realized_pnl_gp)}</b><span>realized</span></div><div class="kpi"><b class="${cls(w.unrealized_pnl_gp)}">${gp(w.unrealized_pnl_gp)}</b><span>unrealized</span></div></div><div class="tiny">run ${esc(r.run_id || 'legacy')} · ${badge(runHealth(r))}${r.schedule_delay_minutes != null ? ` · scheduler +${r.schedule_delay_minutes}m` : ''}</div></div></section>`;
}

function positions() {
  const w = data.wallets[wallet], ps = w.positions || [];
  return `<section><div class="section-title"><h2>Open inventory</h2><span class="tiny">${ps.length}/${w.strategy.max_positions} slots</span></div>${ps.length ? ps.map(p => `<div class="panel"><div class="row"><span class="item">${esc(p.name)}</span><b class="${cls(p.unrealized_roi)} num">${pct(p.unrealized_roi)}</b></div><div class="grid2"><div class="metric"><div class="label">position</div><div>${gp(p.qty)} × ${gp(p.entry_price)}</div></div><div class="metric"><div class="label">liquidation</div><div>${gp(p.unit_liquidation)} ea</div></div><div class="metric"><div class="label">market move</div><div class="${cls(p.market_move_roi)}">${pct(p.market_move_roi || 0)}</div></div><div class="metric"><div class="label">entry EV</div><div>${pct(p.entry_expected_roi)}</div></div></div></div>`).join('') : `<div class="panel tiny">No open inventory.</div>`}</section>`;
}

function candidates() {
  const w = data.wallets[wallet], cs = w.top_candidates || [];
  return `<section><div class="section-title"><h2>${esc(w.name)} opportunity book</h2><span class="tiny">${gp(w.eligible_candidates)} eligible</span></div><div class="panel scroll"><table class="table"><thead><tr><th># / item</th><th>EV</th><th>mom</th><th>flow</th><th>liq</th><th>hist</th><th>score</th></tr></thead><tbody>${cs.map((c,i) => `<tr><td><span class="rank">${i+1}</span> ${esc(c.name)}</td><td class="${cls(c.expected_roi)}">${pct(c.expected_roi)}</td><td class="${cls(c.momentum_5m_vs_1h)}">${pct(c.momentum_5m_vs_1h)}</td><td>${Number(c.volume_acceleration || 0).toFixed(1)}</td><td>${Math.round((c.liquidity_score || 0) * 100)}</td><td>${Number(c.historical_signal || 0).toFixed(2)}</td><td>${Number(c.score || 0).toFixed(1)}</td></tr>`).join('')}</tbody></table></div></section>`;
}

function market() {
  const m = data.market || {}, hs = m.historical?.items || {};
  return `${comparison()}<section><div class="section-title"><h2>Common economy tape</h2><span class="tiny">${gp(m.stats?.tracked_items)} items</span></div><div class="panel scroll"><table class="table"><thead><tr><th>item</th><th>spread</th><th>mom</th><th>5m vol</th><th>1h turnover</th></tr></thead><tbody>${(m.top_by_turnover || []).slice(0,22).map(x => `<tr><td>${esc(x.name)}</td><td>${pct(x.spread_roi)}</td><td class="${cls(x.momentum_5m_vs_1h)}">${pct(x.momentum_5m_vs_1h)}</td><td>${gp(x.volume_5m)}</td><td>${gp(x.turnover_gp_1h)}</td></tr>`).join('')}</tbody></table></div></section><section><div class="section-title"><h2>Historical calibration</h2><span class="tiny">${esc(m.historical?.status || '')}${m.historical?.age_hours != null ? ` · ${m.historical.age_hours}h old` : ''}</span></div>${Object.values(hs).length ? Object.values(hs).map(h => `<div class="panel"><div class="row"><b>${esc(h.name)}</b><span class="${cls(h.projected_6h_pct)}">${pct(h.projected_6h_pct)}</span></div><div class="tiny">z ${h.zscore ?? '–'} · 1h σ ${pct(h.volatility_1h || 0)} · 6h trend ${pct(h.trend_6h || 0)} · max DD ${pct(h.max_drawdown || 0)} · projection confidence ${Math.round((h.projection_confidence || 0) * 100)}%</div></div>`).join('') : '<div class="panel tiny">Historical sample unavailable.</div>'}</section>`;
}

function intelligence() {
  const a = data.intelligence || {};
  return `<section><div class="section-title"><h2>Intelligence & critiques</h2><span class="tiny">${esc(a.model || a.status || '')}</span></div><div class="panel"><div class="row"><b>${esc(a.market_mood || 'unknown')}</b><span>${badge(a.regime || 'unknown')} ${badge(a.status || 'unknown')}</span></div><p class="explain">${esc(a.summary || '')}</p>${(a.notable_events || []).slice(0,5).map(e => `<div class="event"><b>${esc(e.title)}</b><div>${badge(e.evidence_class || 'MODEL_INFERENCE')} ${e.source ? badge(e.source) : ''}</div><div class="tiny">${esc(e.explanation || '')}</div></div>`).join('')}${(a.auxiliary || []).map(x => `<details class="details"><summary>free-router ${esc(x.kind)} · ${esc(x.status)}</summary><div class="code">${esc(JSON.stringify(x.result || x.error || {}, null, 2))}</div></details>`).join('')}</div></section>`;
}

function research() {
  const r = data.deterministic_research || {};
  return `<section><div class="section-title"><h2>Economy wire</h2><span class="tiny">official + deterministic scout · ${esc(r.search_status || 'unknown')}</span></div><div class="panel">${(r.official || []).filter(x => !x.error).slice(0,6).map(x => `<div class="event"><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a><div class="tiny">Jagex · official</div></div>`).join('')}${(r.search || []).filter(x => !x.error).slice(0,5).map(x => `<div class="event"><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a><div class="tiny">${esc(x.snippet || '')}</div></div>`).join('')}</div></section>`;
}

function method() {
  const ws = Object.values(data.wallets);
  return `${comparison()}<section><div class="section-title"><h2>Architecture</h2></div><div class="panel"><div class="code">market snapshot → common feature vector → cached historical context\n                              ↙                 ↘\n                       Velocity score      Market Maker score\n                              ↓                 ↓\n                         wallet engine       wallet engine\n                              ↘                 ↙\n                     shared research / public terminal\n\nP&L and execution remain deterministic. AI is commentary + critique only.\nStop-losses reference market movement from the entry liquidation baseline; accounting remains mark-to-liquidation.</div></div>${ws.map(w => `<div class="panel"><b>${esc(w.name)}</b><p class="explain">${esc(w.thesis)}</p><div class="tiny">max ${w.strategy.max_positions} · reserve ${pct(w.strategy.reserve_pct)} · TP ${pct(w.strategy.take_profit)} · SL ${pct(w.strategy.stop_loss)} · rotate ${w.strategy.soft_rotate_hours}h · max hold ${w.strategy.max_hold_hours}h</div></div>`).join('')}</section>`;
}

function ops() {
  const latest = data.run || {}, rows = runs.runs || [];
  return `<section><div class="section-title"><h2>Run observability</h2><span class="tiny">latest ${esc(latest.run_id || 'legacy')}</span></div><div class="panel"><div class="row"><b>${badge(runHealth(latest))} v${esc(data.version)}</b>${latest.url ? `<a href="${esc(latest.url)}" target="_blank" rel="noopener">GitHub Actions ↗</a>` : ''}</div><div class="grid2"><div class="metric"><div class="label">duration</div><div>${latest.duration_seconds ?? '–'}s</div></div><div class="metric"><div class="label">scheduler lag</div><div>${latest.schedule_delay_minutes == null ? '–' : `+${latest.schedule_delay_minutes}m`}</div></div><div class="metric"><div class="label">AI</div><div>${esc(latest.intelligence?.status || data.intelligence?.status || '–')}</div></div><div class="metric"><div class="label">AI cost</div><div>${latest.intelligence?.cost == null ? '–' : `$${Number(latest.intelligence.cost).toFixed(4)}`}</div></div></div>${(latest.health?.warnings || []).length ? `<div class="tiny">warnings: ${(latest.health.warnings || []).map(esc).join(' · ')}</div>` : '<div class="tiny">no run-health warnings</div>'}</div></section><section><div class="section-title"><h2>Recent hourly cycles</h2><span class="tiny">${rows.length} retained summaries</span></div><div class="panel scroll"><table class="table"><thead><tr><th>time</th><th>health</th><th>AI</th><th>Velocity</th><th>Maker</th><th>trades</th><th>lag</th></tr></thead><tbody>${rows.slice(0,30).map(r => { const v=r.wallets?.velocity||{}, m=r.wallets?.market_maker||{}, trades=(v.trades||0)+(m.trades||0); return `<tr><td>${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${new Date(r.at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</a>` : new Date(r.at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</td><td>${esc(r.health?.status || '?')}</td><td>${esc(r.intelligence?.status || '?')}</td><td class="${cls(v.return_pct)}">${pct(v.return_pct || 0)}</td><td class="${cls(m.return_pct)}">${pct(m.return_pct || 0)}</td><td>${trades}</td><td>${r.schedule_delay_minutes == null ? '–' : `+${r.schedule_delay_minutes}m`}</td></tr>`; }).join('')}</tbody></table></div></section>`;
}

async function renderHistory() {
  const q = new URLSearchParams(location.search), requested = q.get('day');
  const day = requested && days.days.includes(requested) ? requested : days.days[0];
  if (!day) return '<div class="panel tiny">No archive yet.</div>';
  const i = days.days.indexOf(day), d = await fetch(`data/days/${day}.json?t=${Date.now()}`).then(r => r.json());
  return `${switcher()}<section><div class="section-title"><h2>Daily wallet tape</h2><span class="tiny">${d.runs.length} observations</span></div><div class="panel daynav"><button ${i >= days.days.length - 1 ? 'disabled' : ''} onclick="goDay('${days.days[i+1] || day}')">← older</button><b>${day}</b><button ${i <= 0 ? 'disabled' : ''} onclick="goDay('${days.days[i-1] || day}')">newer →</button></div>${d.runs.slice().reverse().map(r => { const w=r.wallets?.[wallet]; if(!w) return `<div class="panel"><div class="row"><b>${new Date(r.at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</b><span class="tiny">legacy ${esc(r.version || 'v0.2')} run</span></div><div class="explain">${esc(r.intelligence?.summary || 'Pre-multi-wallet observation preserved in the archive.')}</div></div>`; return `<div class="panel"><div class="row"><b>${new Date(r.at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</b><span class="${cls(w.return_pct)}">${gp(w.value_gp)} gp · ${pct(w.return_pct)}</span></div><div class="tiny">cash ${gp(w.cash_gp)} · ${w.positions || 0} positions · ${w.trades?.length || 0} trades · ${esc(r.intelligence?.regime || 'unknown')} · ${esc(r.health?.status || 'legacy')}</div><div class="explain">${esc(r.intelligence?.summary || '')}</div></div>`; }).join('')}</section>`;
}

window.selectWallet = w => { wallet = w; render(); };
window.goDay = d => { const u = new URL(location); u.searchParams.set('day', d); window.history.replaceState(null, '', u); renderHistory().then(h => $('#app').innerHTML = h); };

async function render() {
  if (view === 'history') { $('#app').innerHTML = await renderHistory(); return; }
  $('#app').innerHTML = view === 'market' ? market() + research() : view === 'method' ? method() + market() : view === 'ops' ? ops() : comparison() + hero() + intelligence() + positions() + candidates() + research();
}

(async () => {
  try {
    [data, days, runs] = await Promise.all([
      fetch(`data/latest_snapshot.json?t=${Date.now()}`).then(r => r.json()),
      fetch(`data/days/index.json?t=${Date.now()}`).then(r => r.ok ? r.json() : {days: []}).catch(() => ({days: []})),
      fetch(`data/runs/index.json?t=${Date.now()}`).then(r => r.ok ? r.json() : {runs: []}).catch(() => ({runs: []})),
    ]);
    $('#updated').textContent = age(data.updated_at);
    document.querySelectorAll('nav button').forEach(b => b.onclick = () => { view = b.dataset.view; document.querySelectorAll('nav button').forEach(x => x.classList.toggle('active', x === b)); render(); });
    render();
  } catch (e) {
    $('#app').innerHTML = '<div class="loading">No usable market snapshot yet.</div>';
  }
})();
