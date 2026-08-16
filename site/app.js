const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const n = v => Number.isFinite(Number(v)) ? Number(v) : null;
const gp = v => n(v) == null ? '–' : Math.round(Number(v)).toLocaleString();
const pct = v => n(v) == null ? '–' : `${Number(v) >= 0 ? '+' : ''}${(Number(v) * 100).toFixed(2)}%`;
const shortGp = v => { const x=n(v); if(x==null)return '–'; const a=Math.abs(x); if(a>=1e9)return `${(x/1e9).toFixed(1)}b`; if(a>=1e6)return `${(x/1e6).toFixed(1)}m`; if(a>=1e3)return `${(x/1e3).toFixed(1)}k`; return Math.round(x).toString(); };
const cls = v => n(v) == null ? '' : Number(v) > 0 ? 'up' : Number(v) < 0 ? 'down' : '';
const safeDate = v => { const d=new Date(v); return Number.isNaN(d.getTime()) ? null : d; };
const age = v => { const d=safeDate(v); if(!d)return '–'; const m=Math.max(0,Math.round((Date.now()-d)/60000)); return m<60?`${m}m ago`:`${(m/60).toFixed(1)}h ago`; };
const timeLabel = v => { const d=safeDate(v); return d ? d.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}) : '–'; };
const badge = s => `<span class="pill neutral">${esc(s ?? '–')}</span>`;
const help = (label, tip) => `${esc(label)} <button class="help" type="button" aria-label="Explain ${esc(label)}" data-tip="${esc(tip)}">?</button>`;
const runHealth = r => r?.health?.status || 'unknown';

let data, days={days:[]}, runs={runs:[]}, histories={velocity:[],market_maker:[]};
let view='general', wallet='velocity', itemQuery='';

async function fetchJson(url, fallback={}) {
  try { const r=await fetch(`${url}?t=${Date.now()}`); return r.ok ? await r.json() : fallback; } catch { return fallback; }
}
async function fetchJsonl(url) {
  try { const r=await fetch(`${url}?t=${Date.now()}`); if(!r.ok)return []; const text=await r.text(); return text.split(/\n+/).filter(Boolean).map(line=>{try{return JSON.parse(line)}catch{return null}}).filter(Boolean); } catch { return []; }
}

function spark(points, slug='', height=48, baseline=10000000) {
  const vals=(points||[]).map(p=>n(p.value_gp)).filter(v=>v!=null);
  if(vals.length<2)return `<div class="empty">chart after 2 observations</div>`;
  const W=300,H=height,pad=3,min=Math.min(...vals,baseline),max=Math.max(...vals,baseline),range=Math.max(1,max-min);
  const xy=vals.map((v,i)=>`${pad+(W-pad*2)*(i/(vals.length-1))},${pad+(H-pad*2)*(1-(v-min)/range)}`).join(' ');
  const by=pad+(H-pad*2)*(1-(baseline-min)/range);
  return `<svg class="spark ${esc(slug)}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-label="equity curve"><line class="base" x1="0" y1="${by}" x2="${W}" y2="${by}"></line><polyline class="line" points="${xy}"></polyline></svg>`;
}

function meter(value,min=-.02,max=.02) {
  const x=Math.max(min,Math.min(max,n(value)||0)); const center=50; const width=Math.abs(x)/(max-min)*100; const left=x>=0?center:center-width;
  return `<div class="meter"><span class="${x>=0?'up':'down'}" style="left:${left}%;width:${width}%"></span></div>`;
}

function walletSwitcher() {
  return `<div class="wallet-tabs">${Object.values(data.wallets||{}).map(w=>`<button class="${w.id===wallet?'active':''}" onclick="selectWallet('${w.id}')">${esc(w.name)} <span class="${cls(w.return_pct)}">${pct(w.return_pct)}</span></button>`).join('')}</div>`;
}

function economyFallback() {
  const rows=data.market?.items || data.market?.top_by_turnover || [];
  if(!rows.length)return {};
  const adv=rows.filter(r=>(n(r.momentum_5m_vs_1h)||0)>.0001).length, dec=rows.filter(r=>(n(r.momentum_5m_vs_1h)||0)<-.0001).length;
  const total=rows.reduce((a,r)=>a+(n(r.turnover_gp_1h)||0),0);
  return {
    advancers:adv,decliners:dec,flat:rows.length-adv-dec,breadth:(adv-dec)/Math.max(1,adv+dec),
    turnover_weighted_price_pressure:rows.reduce((a,r)=>a+(n(r.momentum_5m_vs_1h)||0)*(n(r.turnover_gp_1h)||0),0)/Math.max(1,total),
    active_share:rows.filter(r=>(n(r.volume_acceleration)||0)>0).length/rows.length,
    top10_turnover_share:rows.slice(0,10).reduce((a,r)=>a+(n(r.turnover_gp_1h)||0),0)/Math.max(1,total),
    median_spread:null,median_liquidity:null,turnover_hhi:null,momentum_dispersion:null
  };
}
const economy = () => ({...economyFallback(),...(data.market?.economy||{})});

function economyMetrics() {
  const e=economy();
  return `<div class="metric-grid">
    <div class="metric-card"><div class="metric-label">${help('Price pressure','Turnover-weighted short-run price change: 5-minute average midpoint versus 1-hour average midpoint. This is a pressure proxy, not a true inflation index.')}</div><b class="${cls(e.turnover_weighted_price_pressure)}">${pct(e.turnover_weighted_price_pressure)}</b>${meter(e.turnover_weighted_price_pressure,-.015,.015)}</div>
    <div class="metric-card"><div class="metric-label">${help('Breadth','Advancing minus declining items divided by all directional items. +100% means broad gains; -100% means broad declines.')}</div><b class="${cls(e.breadth)}">${pct(e.breadth)}</b><div class="breadth"><span class="a" style="width:${100*(e.advancers||0)/Math.max(1,(e.advancers||0)+(e.decliners||0)+(e.flat||0))}%"></span><span class="f" style="width:${100*(e.flat||0)/Math.max(1,(e.advancers||0)+(e.decliners||0)+(e.flat||0))}%"></span><span class="d" style="width:${100*(e.decliners||0)/Math.max(1,(e.advancers||0)+(e.decliners||0)+(e.flat||0))}%"></span></div></div>
    <div class="metric-card"><div class="metric-label">${help('Activity','Share of tracked items whose recent volume pace is above their one-hour baseline.')}</div><b>${pct(e.active_share)}</b><div class="metric-note">volume acceleration</div></div>
    <div class="metric-card"><div class="metric-label">${help('Top-10 concentration','Share of total observed hourly GP turnover concentrated in the ten busiest tracked items. Higher means activity is more top-heavy.')}</div><b>${pct(e.top10_turnover_share)}</b><div class="metric-note">turnover share</div></div>
  </div>`;
}

function statusStrip() {
  const r=data.run||{}, ai=data.intelligence||{};
  return `<div class="status-strip"><span>${badge(runHealth(r))} run ${esc(r.run_id||'legacy')}</span><span>AI ${esc(ai.freshness||ai.status||'–')} · ${age(ai.generated_at)}</span></div>`;
}

function general() {
  const ai=data.intelligence||{};
  return `${statusStrip()}
    <section><div class="section-title"><h2>Wallets</h2><span class="tiny">same 10M starting GP</span></div><div class="cards2">${Object.values(data.wallets||{}).map(w=>`<button class="wallet-card" onclick="openWallet('${w.id}')"><span class="tiny">${esc(w.name)}</span><strong class="${cls(w.return_pct)}">${gp(w.value_gp)} gp</strong><span class="tiny">${pct(w.return_pct)} · ${(w.positions||[]).length} holdings</span>${spark(histories[w.id],w.id)}</button>`).join('')}</div></section>
    <section><div class="section-title"><h2>Economy now</h2><div class="section-actions"><button onclick="goView('economy')">details →</button></div></div>${economyMetrics()}</section>
    <section><div class="section-title"><h2>State of the economy</h2><span class="tiny">${esc(ai.model||'deterministic')} · ${ai.generated_at?age(ai.generated_at):'–'}</span></div><div class="panel"><p class="brief">${esc(ai.economy_brief || ai.summary || 'A semantic economy brief will appear after the next research refresh.')}</p>${ai.regime?`<div class="tiny more-note">Regime: ${esc(ai.regime)}</div>`:''}</div></section>
    <section><div class="section-title"><h2>Go deeper</h2></div><div class="quick-grid">
      ${quick('Wallet','Holdings, trades & opportunity attribution',"wallet")}
      ${quick('Items','Active commodities & live tape',"items")}
      ${quick('Economy','Breadth, pressure, concentration & replay',"economy")}
      ${quick('Research','Catalysts, critiques & evidence',"research")}
      ${quick('History','Daily observations & past runs',"history")}
      ${quick('Ops','Workflow health & run audit',"ops")}
    </div></section>`;
}
function quick(title,sub,target){return `<button class="quick-link" onclick="goView('${target}')"><b>${esc(title)} →</b><span>${esc(sub)}</span></button>`;}

function walletHero() {
  const w=data.wallets[wallet]; if(!w)return '';
  return `${walletSwitcher()}<section><div class="panel hero"><div class="row"><div class="stack"><span class="muted">${esc(w.name.toUpperCase())} · MARK-TO-LIQUIDATION</span><div class="value num">${gp(w.value_gp)} gp</div></div><b class="${cls(w.return_pct)}">${pct(w.return_pct)}</b></div>${spark(histories[wallet],wallet,68)}<div class="chart-labels"><span>start</span><span>latest</span></div><div class="kpis"><div class="kpi"><b>${gp(w.cash_gp)}</b><span>cash</span></div><div class="kpi"><b class="${cls(w.realized_pnl_gp)}">${gp(w.realized_pnl_gp)}</b><span>realized</span></div><div class="kpi"><b class="${cls(w.unrealized_pnl_gp)}">${gp(w.unrealized_pnl_gp)}</b><span>unrealized</span></div></div><p class="tiny">${esc(w.thesis)}</p></div></section>`;
}

function holdings() {
  const w=data.wallets[wallet], rows=w?.positions||[];
  return `<section><div class="section-title"><h2>Holdings</h2><span class="tiny">${rows.length}/${w?.strategy?.max_positions??'–'} slots</span></div><div class="list">${rows.length?rows.map(p=>`<details class="list-row"><summary><div class="summary-main"><b>${esc(p.name)}</b><span class="summary-sub">${gp(p.qty)} × ${gp(p.entry_price)} · liq ${gp(p.unit_liquidation)} ea</span></div><div class="summary-value ${cls(p.unrealized_roi)}"><b>${pct(p.unrealized_roi)}</b><span class="tiny">move ${pct(p.market_move_roi)}</span></div></summary><div class="detail-body"><div class="detail-grid"><div class="cell"><div class="label">Cost basis</div><div>${gp((p.qty||0)*(p.entry_price||0))} gp</div></div><div class="cell"><div class="label">Liquidation value</div><div>${gp(p.value_gp)} gp</div></div><div class="cell"><div class="label">Entry EV</div><div>${pct(p.entry_expected_roi)}</div></div><div class="cell"><div class="label">Risk budget</div><div>${pct(p.risk_budget_pct)}</div></div></div></div></details>`).join(''):`<div class="empty">No holdings.</div>`}</div></section>`;
}

const factorHelp={edge:'Post-tax expected spread capture after fill/completion assumptions.',momentum:'Short-run price impulse. Positive helps Velocity more than Market Maker.',flow:'Volume acceleration versus the recent baseline.',liquidity:'Turnover-derived liquidity proxy; higher improves fill quality.',history:'Cached historical trend/z-score contribution.',freshness:'Small bonus for recent quotes.'};
function factorPill(name,value){const v=n(value)||0;return `<span class="factor ${v>0?'pos':v<0?'neg':'zero'}" title="${esc(factorHelp[name]||name)}">${esc(name)} ${v>0?'↑':v<0?'↓':'→'} ${v>0?'+':''}${v.toFixed(1)}</span>`;}
function topFactors(c){const entries=Object.entries(c.score_components||{}).sort((a,b)=>Math.abs(b[1])-Math.abs(a[1])).slice(0,2);return entries.map(([k,v])=>`${k} ${v>=0?'↑':'↓'}${Math.abs(v).toFixed(0)}`).join(' · ');}

function opportunities() {
  const w=data.wallets[wallet], rows=w?.top_candidates||[];
  return `<section><div class="section-title"><h2>Opportunity book</h2><span class="tiny">${gp(w?.eligible_candidates)} eligible</span></div><div class="list">${rows.length?rows.map((c,i)=>`<details class="list-row"><summary><div class="summary-main"><b>${i+1}. ${esc(c.name)}</b><span class="summary-sub">${topFactors(c)||`fill ${pct(c.fill_probability)} · flow ${n(c.volume_acceleration)?.toFixed(1)??'–'}×`}</span></div><div class="summary-value"><b class="${cls(c.expected_roi)}">EV ${pct(c.expected_roi)}</b><span class="tiny">score ${n(c.score)?.toFixed(1)??'–'}</span></div></summary><div class="detail-body"><div class="callout">Expected value = completed spread capture − expected inventory/adverse-selection cost.</div><div class="factor-wrap">${Object.entries(c.score_components||{}).map(([k,v])=>factorPill(k,v)).join('') || '<span class="tiny">score attribution available after the next v0.4 cycle</span>'}</div><div class="detail-grid"><div class="cell"><div class="label">Spread capture EV</div><div>${gp(c.spread_capture_ev_gp)} gp</div></div><div class="cell"><div class="label">Inventory-risk EV</div><div class="down">−${gp(c.inventory_risk_ev_gp)} gp</div></div><div class="cell"><div class="label">Two-leg completion</div><div>${pct(c.fill_probability)}</div></div><div class="cell"><div class="label">Inventory state</div><div>${pct(c.inventory_probability)}</div></div><div class="cell"><div class="label">Momentum</div><div class="${cls(c.momentum_5m_vs_1h)}">${pct(c.momentum_5m_vs_1h)}</div></div><div class="cell"><div class="label">Risk budget</div><div>${pct(c.risk_budget_pct)}</div></div></div></div></details>`).join(''):'<div class="empty">No eligible opportunities.</div>'}</div></section>`;
}

function walletView(){return `${walletHero()}${holdings()}${opportunities()}<details class="group"><summary>Strategy policy & thresholds</summary><div class="group-body tiny">${strategyPolicy(data.wallets[wallet])}</div></details>`;}
function strategyPolicy(w){const s=w?.strategy||{};return `Max ${s.max_positions??'–'} holdings · reserve ${pct(s.reserve_pct)} · TP ${pct(s.take_profit)} · market-move SL ${pct(s.stop_loss)} · soft rotation ${s.soft_rotate_hours??'–'}h · max hold ${s.max_hold_hours??'–'}h · max position ${pct(s.max_position_pct)}`;}

function itemRows() {
  const rows=(data.market?.items||data.market?.top_by_turnover||[]).filter(r=>!itemQuery||String(r.name||'').toLowerCase().includes(itemQuery.toLowerCase())).slice(0,80);
  return `<section><div class="section-title"><h2>Active item tape</h2><span class="tiny">${rows.length} shown</span></div><input class="search" placeholder="Filter item names…" value="${esc(itemQuery)}" oninput="filterItems(this.value)"><div class="table-wrap"><table><thead><tr><th>item</th><th>low</th><th>high</th><th>spread</th><th>mom</th><th>1h gp</th></tr></thead><tbody>${rows.map(r=>`<tr><td title="${esc(r.name)}">${esc(r.name)}</td><td>${gp(r.low)}</td><td>${gp(r.high)}</td><td>${pct(r.spread_roi)}</td><td class="${cls(r.momentum_5m_vs_1h)}">${pct(r.momentum_5m_vs_1h)}</td><td>${shortGp(r.turnover_gp_1h)}</td></tr>`).join('')}</tbody></table></div></section>`;
}
function turnoverBars(){const rows=(data.market?.top_by_turnover||[]).slice(0,10),max=Math.max(1,...rows.map(r=>n(r.turnover_gp_1h)||0));return `<section><div class="section-title"><h2>Turnover leaders</h2><span class="tiny">observed 1h GP</span></div><div class="bar-list">${rows.map(r=>`<div class="bar-row"><div class="bar-name"><div class="bar-fill" style="width:${100*(n(r.turnover_gp_1h)||0)/max}%"></div><span>${esc(r.name)}</span></div><div class="bar-value">${shortGp(r.turnover_gp_1h)}</div></div>`).join('')}</div></section>`;}
function itemsView(){return `${turnoverBars()}${itemRows()}`;}

function simulation() {
  const sim=data.simulation||{}, ws=sim.wallets||{};
  if(!Object.keys(ws).length)return `<section><div class="section-title"><h2>72h replay</h2></div><div class="panel tiny">Historical replay will populate on its periodic calibration cycle.</div></section>`;
  return `<section><div class="section-title"><h2>${sim.window_hours||sim.requested_hours||72}h replay</h2><span class="tiny">${sim.universe_items||'–'}-item diagnostic universe · ${age(sim.generated_at)}</span></div><div class="cards2">${Object.entries(ws).map(([slug,w])=>`<div class="panel"><span class="tiny">${esc(w.name||slug)}</span><b class="${cls(w.return_pct)}" style="display:block;font-size:1rem">${gp(w.end_gp)} gp · ${pct(w.return_pct)}</b>${spark(w.points||[],slug,54)}<div class="tiny">max DD ${pct(w.max_drawdown)} · ${w.trades||0} trades</div></div>`).join('')}</div><details class="group"><summary>Replay assumptions / limitations</summary><div class="group-body"><ul class="clean-list">${(sim.assumptions||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div></details></section>`;
}

function historicalCalibration(){const h=data.market?.historical||{},rows=Object.values(h.items||{});return `<details class="group"><summary>Historical calibration · ${esc(h.status||'unavailable')} ${h.age_hours!=null?`· ${h.age_hours}h old`:''}</summary><div class="group-body">${rows.length?rows.map(x=>`<div class="event"><b>${esc(x.name)}</b><p>z ${x.zscore??'–'} · σ ${pct(x.volatility_1h)} · 6h trend ${pct(x.trend_6h)} · max DD ${pct(x.max_drawdown)} · projection ${pct(x.projected_6h_pct)} (${Math.round((x.projection_confidence||0)*100)}% confidence)</p></div>`).join(''):'<div class="tiny">No historical sample.</div>'}</div></details>`;}

function economyView(){const e=economy(),ai=data.intelligence||{};return `<section><div class="section-title"><h2>Economy</h2><span class="tiny">cross-sectional OSRS market conditions</span></div>${economyMetrics()}</section><section><div class="section-title"><h2>State of the economy</h2><span class="tiny">semantic brief every ~2h</span></div><div class="panel"><p class="brief">${esc(ai.economy_brief||ai.summary||'No current semantic brief.')}</p><div class="tiny">${esc(ai.market_mood||'')} ${ai.generated_at?`· ${age(ai.generated_at)}`:''}</div></div></section><section><div class="section-title"><h2>Market structure</h2></div><div class="panel"><div class="detail-grid"><div class="cell"><div class="label">Momentum dispersion</div><div>${pct(e.momentum_dispersion)}</div></div><div class="cell"><div class="label">Median spread</div><div>${pct(e.median_spread)}</div></div><div class="cell"><div class="label">Median liquidity</div><div>${n(e.median_liquidity)?.toFixed(2)??'–'}</div></div><div class="cell"><div class="label">Turnover HHI</div><div>${n(e.turnover_hhi)?.toFixed(3)??'–'}</div></div></div><div class="tiny more-note">Price pressure is deliberately not labeled “inflation.” A defensible inflation index needs a stable basket observed over a much longer window.</div></div></section>${simulation()}${historicalCalibration()}`;}

function auxHuman(x){
  if(x.status!=='ok')return `<div class="event"><b>${esc(x.kind)} unavailable</b><p>${esc(x.error||'supplementary model unavailable')}</p></div>`;
  const r=x.result||{};
  if(x.kind==='analyst_critique')return `<div class="event"><b>Analyst critique</b><p>${esc(r.summary||'')}</p>${r.concerns?.length?`<ul class="clean-list">${r.concerns.map(v=>`<li>${esc(v)}</li>`).join('')}</ul>`:''}</div>`;
  if(x.kind==='wallet_red_team')return `<div class="event"><b>Wallet red team</b><p><strong>Velocity:</strong> ${(r.velocity||[]).map(esc).join(' · ')||'–'}</p><p><strong>Market Maker:</strong> ${(r.market_maker||[]).map(esc).join(' · ')||'–'}</p></div>`;
  if(x.kind==='news_triage')return `<div class="event"><b>News triage</b>${r.important?.length?`<p><strong>Worth attention:</strong> ${r.important.map(esc).join(' · ')}</p>`:''}${r.probably_noise?.length?`<p><strong>Probably noise:</strong> ${r.probably_noise.map(esc).join(' · ')}</p>`:''}</div>`;
  return `<div class="event"><b>${esc(x.kind)}</b><p>Supplementary analysis available.</p></div>`;
}
function researchView(){const a=data.intelligence||{},r=data.deterministic_research||{};return `<section><div class="section-title"><h2>Research & interpretation</h2><span class="tiny">${esc(a.model||a.status||'')}</span></div><div class="panel"><b>${esc(a.market_mood||'Current read')}</b><p class="brief">${esc(a.economy_brief||a.summary||'')}</p>${(a.wallet_notes||[]).length?`<ul class="clean-list">${a.wallet_notes.map(v=>`<li>${esc(v)}</li>`).join('')}</ul>`:''}</div></section><section><div class="section-title"><h2>Notable evidence</h2></div><div class="panel">${(a.notable_events||[]).length?(a.notable_events||[]).map(e=>`<div class="event">${e.url?`<a href="${esc(e.url)}" target="_blank" rel="noopener"><b>${esc(e.title)}</b></a>`:`<b>${esc(e.title)}</b>`}<div>${badge(e.evidence_class||'MODEL_INFERENCE')} ${e.source?badge(e.source):''}</div>${e.explanation?`<p>${esc(e.explanation)}</p>`:''}</div>`).join(''):'<div class="tiny">No notable events.</div>'}</div></section><section><div class="section-title"><h2>Independent critiques</h2><span class="tiny">free router · nonbinding</span></div><div class="panel">${(a.auxiliary||[]).map(auxHuman).join('')||'<div class="tiny">No supplementary critique this cycle.</div>'}</div></section><section><div class="section-title"><h2>Deterministic wire</h2><span class="tiny">official + scout · ${esc(r.search_status||'')}</span></div><div class="panel">${[...(r.official||[]).filter(x=>!x.error),...(r.search||[]).filter(x=>!x.error)].slice(0,12).map(x=>`<div class="event"><a href="${esc(x.url)}" target="_blank" rel="noopener"><b>${esc(x.title)}</b></a><p>${esc(x.source||'web')} ${x.snippet?`· ${esc(x.snippet)}`:''}</p></div>`).join('')||'<div class="tiny">No deterministic research rows.</div>'}</div></section>`;}

function opsView(){const latest=data.run||{},rows=runs.runs||[];return `<section><div class="section-title"><h2>Latest run</h2><span class="tiny">${esc(latest.run_id||'legacy')}</span></div><div class="panel"><div class="row"><b>${badge(runHealth(latest))} v${esc(data.version)}</b>${latest.url?`<a href="${esc(latest.url)}" target="_blank">Actions ↗</a>`:''}</div><div class="detail-grid"><div class="cell"><div class="label">Duration</div><div>${latest.duration_seconds??'–'}s</div></div><div class="cell"><div class="label">Scheduler lag</div><div>${latest.schedule_delay_minutes==null?'–':`+${latest.schedule_delay_minutes}m`}</div></div><div class="cell"><div class="label">AI</div><div>${esc(latest.intelligence?.status||data.intelligence?.status||'–')}</div></div><div class="cell"><div class="label">AI freshness</div><div>${esc(latest.intelligence?.freshness||data.intelligence?.freshness||'–')}</div></div></div>${latest.health?.warnings?.length?`<div class="tiny more-note">warnings: ${latest.health.warnings.map(esc).join(' · ')}</div>`:'<div class="tiny more-note">no run-health warnings</div>'}</div></section><section><div class="section-title"><h2>Recent hourly cycles</h2><span class="tiny">${rows.length} retained</span></div><div class="table-wrap"><table><thead><tr><th>time</th><th>health</th><th>AI</th><th>Velocity</th><th>Maker</th><th>trades</th></tr></thead><tbody>${rows.slice(0,36).map(r=>{const v=r.wallets?.velocity||{},m=r.wallets?.market_maker||{},tr=(v.trades||0)+(m.trades||0);return `<tr><td>${r.url?`<a href="${esc(r.url)}" target="_blank">${timeLabel(r.at)}</a>`:timeLabel(r.at)}</td><td>${esc(r.health?.status||'?')}</td><td>${esc(r.intelligence?.freshness||r.intelligence?.status||'?')}</td><td class="${cls(v.return_pct)}">${pct(v.return_pct)}</td><td class="${cls(m.return_pct)}">${pct(m.return_pct)}</td><td>${tr}</td></tr>`}).join('')}</tbody></table></div></section>`;}

async function historyView(){const requested=new URLSearchParams(location.search).get('day'),day=requested&&days.days.includes(requested)?requested:days.days[0];if(!day)return '<div class="panel tiny">No archive yet.</div>';const i=days.days.indexOf(day),d=await fetchJson(`data/days/${day}.json`,{date:day,runs:[]});const points=(d.runs||[]).map(r=>({at:r.at,value_gp:r.wallets?.[wallet]?.value_gp})).filter(p=>n(p.value_gp)!=null);return `${walletSwitcher()}<section><div class="section-title"><h2>Daily tape</h2><span class="tiny">${d.runs.length} observations</span></div><div class="panel daynav"><button ${i>=days.days.length-1?'disabled':''} onclick="goDay('${days.days[i+1]||day}')">← older</button><b>${day}</b><button ${i<=0?'disabled':''} onclick="goDay('${days.days[i-1]||day}')">newer →</button></div><div class="panel">${spark(points,wallet,74)}<div class="chart-labels"><span>day start</span><span>latest</span></div></div><div class="list">${d.runs.slice().reverse().map(r=>{const w=r.wallets?.[wallet];if(!w)return `<div class="empty">${timeLabel(r.at)} · legacy ${esc(r.version||'run')}</div>`;return `<details class="list-row"><summary><div class="summary-main"><b>${timeLabel(r.at)}</b><span class="summary-sub">cash ${gp(w.cash_gp)} · ${w.positions||0} holdings · ${w.trades?.length||0} trades</span></div><div class="summary-value ${cls(w.return_pct)}"><b>${gp(w.value_gp)} gp</b><span class="tiny">${pct(w.return_pct)}</span></div></summary><div class="detail-body tiny">${esc(r.intelligence?.economy_brief||r.intelligence?.summary||'No brief for this observation.')}</div></details>`}).join('')}</div></section>`;}

function methodView(){return `<section><div class="section-title"><h2>How it works</h2></div><div class="panel"><p class="brief">One shared market/economy layer feeds two independent strategy wallets. Market facts are common; preferences, execution policies, holdings and P&L are isolated.</p></div><details class="group" open><summary>Candidate expected value</summary><div class="group-body"><div class="code">completion = entry_fill × exit_fill\ninventory_state = entry_fill × (1 − exit_fill)\nspread_capture_EV = completion × post-tax edge\ninventory_risk_EV = inventory_state × adverse-selection cost\nexpected_value = spread_capture_EV − inventory_risk_EV</div></div></details><details class="group"><summary>Ranking score attribution</summary><div class="group-body"><div class="code">score = edge + momentum + flow + liquidity + history + freshness\n\nEach term is stored separately for every candidate.\nThe Wallet tab shows the exact signed point contribution.</div></div></details><details class="group"><summary>Accounting & exits</summary><div class="group-body"><div class="code">liquidation = observed low × (1 − slippage) − GE tax\nwallet equity = cash + Σ(qty × liquidation)\n\nreported ROI uses mark-to-liquidation\nstop-loss uses movement from the entry liquidation baseline</div></div></details><details class="group"><summary>Research boundary</summary><div class="group-body tiny">LLMs interpret catalysts, regime, narratives and counterarguments. They do not calculate prices, P&L, scores, fills, sizing or mutate wallet state. The primary semantic brief refreshes less often than the deterministic hourly engine.</div></details>`;}

function moreView(){return `<section><div class="section-title"><h2>Reference & diagnostics</h2></div><div class="quick-grid">${quick('Research','Economy brief, catalysts & critiques','research')}${quick('History','Daily wallet tape','history')}${quick('Ops','Run health & observability','ops')}${quick('Method','Maths, assumptions & architecture','method')}</div></section><section><div class="panel subtle"><b>Useful distinction</b><p class="tiny">Items is commodity-level market data. Economy is the aggregate market structure: breadth, price pressure, activity, concentration and longer-run calibration.</p></div></section>`;}

window.goView=v=>{view=v;render();window.scrollTo({top:0,behavior:'instant'});};
window.openWallet=w=>{wallet=w;view='wallet';render();window.scrollTo({top:0,behavior:'instant'});};
window.selectWallet=w=>{wallet=w;render();};
window.filterItems=q=>{itemQuery=q;$('#app').innerHTML=itemsView();bindHelp();};
window.goDay=d=>{const u=new URL(location);u.searchParams.set('day',d);history.replaceState(null,'',u);render();};

function activeNav(){const top=['general','wallet','items','economy'].includes(view)?view:'more';document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===top));}
function bindHelp(){document.querySelectorAll('.help').forEach(b=>{b.onclick=e=>{e.stopPropagation();document.querySelectorAll('.help.open').forEach(x=>x!==b&&x.classList.remove('open'));b.classList.toggle('open');};});}
document.addEventListener('click',()=>document.querySelectorAll('.help.open').forEach(x=>x.classList.remove('open')));

async function render(){activeNav();let html='';if(view==='general')html=general();else if(view==='wallet')html=walletView();else if(view==='items')html=itemsView();else if(view==='economy')html=economyView();else if(view==='research')html=researchView();else if(view==='history')html=await historyView();else if(view==='ops')html=opsView();else if(view==='method')html=methodView();else html=moreView();$('#app').innerHTML=html;bindHelp();}

(async()=>{
  try{
    [data,days,runs,histories.velocity,histories.market_maker]=await Promise.all([
      fetchJson('data/latest_snapshot.json',{}),fetchJson('data/days/index.json',{days:[]}),fetchJson('data/runs/index.json',{runs:[]}),
      fetchJsonl('data/wallets/velocity/equity_history.jsonl'),fetchJsonl('data/wallets/market_maker/equity_history.jsonl')
    ]);
    if(!data.wallets)throw new Error('No wallet snapshot');
    $('#updated').textContent=data.updated_at?age(data.updated_at):'no snapshot time';
    document.querySelectorAll('#nav button').forEach(b=>b.onclick=()=>goView(b.dataset.view));
    await render();
  }catch(err){$('#app').innerHTML=`<div class="panel"><b>Could not load terminal state.</b><p class="tiny">${esc(err.message)}</p></div>`;}
})();
