const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const num = v => Number.isFinite(Number(v)) ? Number(v) : null;
const gp = v => num(v) == null ? '–' : Math.round(Number(v)).toLocaleString();
const shortGp = v => { const x=num(v); if(x==null)return '–'; const a=Math.abs(x); if(a>=1e12)return `${(x/1e12).toFixed(1)}t`; if(a>=1e9)return `${(x/1e9).toFixed(1)}b`; if(a>=1e6)return `${(x/1e6).toFixed(1)}m`; if(a>=1e3)return `${(x/1e3).toFixed(1)}k`; return Math.round(x).toString(); };
const pct = (v,d=2) => num(v) == null ? '–' : `${Number(v)>=0?'+':''}${(Number(v)*100).toFixed(d)}%`;
const ratio = (v,d=2) => num(v) == null ? '–' : Number(v).toFixed(d);
const cls = v => num(v)==null ? '' : Number(v)>0 ? 'up' : Number(v)<0 ? 'down' : '';
const safeDate = v => { const d=new Date(v); return Number.isNaN(d.getTime()) ? null : d; };
const age = v => { const d=safeDate(v); if(!d)return '–'; const m=Math.max(0,Math.round((Date.now()-d)/60000)); return m<60?`${m}m ago`:m<2880?`${(m/60).toFixed(1)}h ago`:`${(m/1440).toFixed(1)}d ago`; };
const timeLabel = v => { const d=safeDate(v); return d?d.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'–'; };
const dateTime = v => { const d=safeDate(v); return d?d.toLocaleString():'–'; };
const badge = (s,tone='neutral') => `<span class="pill ${tone}">${esc(s??'–')}</span>`;
const help = (label,tip) => `${esc(label)} <button class="help" type="button" aria-label="Explain ${esc(label)}" data-tip="${esc(tip)}">?</button>`;
const signed = (v,d=2) => num(v)==null?'–':`${Number(v)>=0?'+':''}${Number(v).toFixed(d)}`;

let data={}, days={days:[]}, runs={runs:[]}, histories={}, reports=[], advisorHistory=[];
let view='general', trader='', itemQuery='', selectedDay='', mixerOff=new Set();

async function fetchJson(url,fallback={}){try{const r=await fetch(`${url}?t=${Date.now()}`);return r.ok?await r.json():fallback}catch{return fallback}}
async function fetchJsonl(url){try{const r=await fetch(`${url}?t=${Date.now()}`);if(!r.ok)return[];const text=await r.text();return text.split(/\n+/).filter(Boolean).map(line=>{try{return JSON.parse(line)}catch{return null}}).filter(Boolean)}catch{return[]}}
const traderIds = () => Object.keys(data.wallets||{});
const currentTrader = () => (data.wallets||{})[trader] || Object.values(data.wallets||{})[0] || null;

function spark(points,slug='',height=48,baseline=10000000){
  const vals=(points||[]).map(p=>num(p.value_gp??p.net_worth_gp)).filter(v=>v!=null);
  if(vals.length<2)return `<div class="empty">chart after 2 observations</div>`;
  const W=300,H=height,pad=3,min=Math.min(...vals,baseline),max=Math.max(...vals,baseline),range=Math.max(1,max-min);
  const xy=vals.map((v,i)=>`${pad+(W-pad*2)*(i/(vals.length-1))},${pad+(H-pad*2)*(1-(v-min)/range)}`).join(' ');
  const by=pad+(H-pad*2)*(1-(baseline-min)/range);
  return `<svg class="spark ${esc(slug)}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-label="net-worth curve"><line class="base" x1="0" y1="${by}" x2="${W}" y2="${by}"></line><polyline class="line" points="${xy}"></polyline></svg>`;
}
function meter(value,min=-.02,max=.02){const x=Math.max(min,Math.min(max,num(value)||0)),center=50,width=Math.abs(x)/(max-min)*100,left=x>=0?center:center-width;return `<div class="meter"><span class="${x>=0?'up':'down'}" style="left:${left}%;width:${width}%"></span></div>`}
function quick(title,sub,target){return `<button class="quick-link" onclick="goView('${target}')"><b>${esc(title)} →</b><span>${esc(sub)}</span></button>`}
function sectionTitle(title,right=''){return `<div class="section-title"><h2>${esc(title)}</h2>${right}</div>`}

function economyFallback(){
  const rows=data.market?.items||data.market?.top_by_turnover||[]; if(!rows.length)return{};
  const adv=rows.filter(r=>(num(r.momentum_5m_vs_1h)||0)>.0001).length,dec=rows.filter(r=>(num(r.momentum_5m_vs_1h)||0)<-.0001).length,total=rows.reduce((a,r)=>a+(num(r.turnover_gp_1h)||0),0);
  return {advancers:adv,decliners:dec,flat:rows.length-adv-dec,breadth:(adv-dec)/Math.max(1,adv+dec),turnover_weighted_price_pressure:rows.reduce((a,r)=>a+(num(r.momentum_5m_vs_1h)||0)*(num(r.turnover_gp_1h)||0),0)/Math.max(1,total),active_share:rows.filter(r=>(num(r.volume_acceleration)||0)>0).length/rows.length,top10_turnover_share:rows.slice(0,10).reduce((a,r)=>a+(num(r.turnover_gp_1h)||0),0)/Math.max(1,total),total_turnover_gp_1h:total};
}
const economy = () => ({...economyFallback(),...(data.market?.economy||{})});

function statusStrip(){
  const r=data.run||{},adv=data.advisory||data.intelligence?.advisory||{},report=data.intelligence||{};
  const h=r?.health?.status||'unknown';
  return `<div class="status-strip"><span>${badge(h,h==='ok'?'pos':h==='degraded'?'warn':'neutral')} run ${esc(r.run_id||'legacy')}</span><span>prior ${esc(adv.freshness||adv.status||'–')} · report ${esc(report.freshness||report.status||'–')}</span></div>`;
}
function economyCards(){
  const e=economy();
  return `<div class="metric-grid">
    <div class="metric-card"><div class="metric-label">${help('Price pressure','Turnover-weighted 5m-vs-1h midpoint movement. A short-run pressure proxy, not a CPI or inflation series.')}</div><b class="${cls(e.turnover_weighted_price_pressure)}">${pct(e.turnover_weighted_price_pressure)}</b>${meter(e.turnover_weighted_price_pressure,-.015,.015)}</div>
    <div class="metric-card"><div class="metric-label">${help('Weighted breadth','Direction breadth weighted by observed hourly GP turnover. Positive means economically larger items skew upward.')}</div><b class="${cls(e.turnover_weighted_breadth??e.breadth)}">${pct(e.turnover_weighted_breadth??e.breadth)}</b><div class="metric-note">raw ${pct(e.breadth)}</div></div>
    <div class="metric-card"><div class="metric-label">${help('Liquidity stress','Composite 0–100 stress proxy from spreads, stale quotes, liquidity and shock breadth. Higher means worse execution conditions.')}</div><b>${num(e.liquidity_stress)==null?'–':(100*e.liquidity_stress).toFixed(0)}</b><div class="metric-note">0 calm · 100 stressed</div></div>
    <div class="metric-card"><div class="metric-label">${help('Temperature','Composite activity/dislocation index from active share, absolute movement, cross-sectional dispersion and pressure.')}</div><b>${num(e.market_temperature)==null?'–':Number(e.market_temperature).toFixed(0)}</b><div class="metric-note">0 quiet · 100 hot</div></div>
  </div>`;
}
function economicTapeMini(){
  const e=economy();
  const rows=[
    ['Hourly turnover',`${shortGp(e.total_turnover_gp_1h)} gp`],
    ['Median spread',pct(e.median_spread)],
    ['Active share',pct(e.active_share)],
    ['Turnover HHI',ratio(e.turnover_hhi,4)],
    ['Turnover Gini',ratio(e.turnover_gini,3)],
    ['Liquidity stress',num(e.liquidity_stress)==null?'–':`${(100*e.liquidity_stress).toFixed(0)}/100`],
    ['Risk appetite',num(e.risk_appetite_proxy)==null?'–':`${(100*e.risk_appetite_proxy).toFixed(0)}/100`],
    ['Patch risk',pct(e.patch?.risk,0)],
  ];
  return `<div class="table-wrap more-note"><table class="econ-table"><tbody>${rows.map(([k,v])=>`<tr><td>${esc(k)}</td><td>${v}</td></tr>`).join('')}</tbody></table></div>`;
}

function biasStrip(){
  const a=data.advisory||data.intelligence?.advisory||{},b=a.biases||{};
  const keys=['macro','momentum','mean_reversion','liquidity','risk'];
  return `<div class="bias-grid">${keys.map(k=>`<div class="bias"><b class="${cls(b[k])}">${signed(b[k],2)}</b><span>${esc(k.replace('_',' '))}</span></div>`).join('')}</div><div class="tiny more-note">Semantic prior · confidence ${pct(a.confidence,0)} · patch risk ${pct(a.patch_risk,0)} · ${esc(a.freshness||a.status||'–')} ${a.generated_at?'('+age(a.generated_at)+')':''}. It can only add a small bounded score/sizing bias.</div>`;
}

function general(){
  const ai=data.intelligence||{};
  return `${statusStrip()}
  <section>${sectionTitle('Traders','<span class="tiny">10M starting capital each</span>')}<div class="cards">${Object.values(data.wallets||{}).map(w=>`<button class="trader-card ${w.id==='frontier'?'frontier':''}" onclick="openTrader('${w.id}')"><span class="tiny">${esc(w.name)}</span><strong class="${cls(w.return_pct)}">${gp(w.net_worth_gp??w.value_gp)} gp</strong><span class="tiny">net worth · ${pct(w.return_pct)} · liquid ${shortGp(w.liquid_gp??w.cash_gp)}</span>${spark(histories[w.id]||[],w.id)}</button>`).join('')}</div></section>
  <section>${sectionTitle('Economy now','<div class="section-actions"><button onclick="goView(\'economy\')">full table →</button></div>')}${economyCards()}${economicTapeMini()}</section>
  <section>${sectionTitle('Bounded model prior','<span class="tiny">math remains authoritative</span>')}${biasStrip()}</section>
  <section>${sectionTitle('State of the economy',`<span class="tiny">8h cadence · ${ai.generated_at?age(ai.generated_at):'–'}</span>`)}<div class="panel"><p class="brief">${esc(ai.economy_brief||ai.summary||'The next semantic report will summarize the deterministic economy packet.')}</p>${ai.regime?`<div class="tiny more-note">Regime: ${esc(ai.regime)}</div>`:''}</div></section>
  <section>${sectionTitle('Go deeper')}<div class="quick-grid">${quick('Traders','Net worth, holdings, actions & factor attribution','traders')}${quick('Items','Hot item tape; full market still feeds the engine','items')}${quick('Economy','Compact macro/microstructure metric table','economy')}${quick('Reports','Economy-report history & model priors','reports')}${quick('History','Daily trader observations and actions','history')}${quick('Method','Formulae, layers & strategy matrix','method')}</div></section>`;
}

function traderSwitcher(){return `<div class="trader-tabs">${Object.values(data.wallets||{}).map(w=>`<button class="${w.id===trader?'active':''}" onclick="selectTrader('${w.id}')">${esc(w.name)} <span class="${cls(w.return_pct)}">${pct(w.return_pct)}</span></button>`).join('')}</div>`}
function traderHero(){
  const w=currentTrader();if(!w)return'<div class="empty">No trader snapshot.</div>';
  const p=w.portfolio_metrics||{}, liquid=w.liquid_gp??w.cash_gp, net=w.net_worth_gp??w.value_gp;
  return `${traderSwitcher()}<section><div class="panel hero"><div class="row"><div class="stack"><span class="muted">${esc(w.name.toUpperCase())} · NET WORTH / MARK-TO-LIQUIDATION</span><div class="value num">${gp(net)} gp</div></div><b class="${cls(w.return_pct)}">${pct(w.return_pct)}</b></div>${spark(histories[w.id]||[],w.id,68)}<div class="chart-labels"><span>start</span><span>latest</span></div><div class="kpis"><div class="kpi"><b>${gp(liquid)}</b><span>liquid gp</span></div><div class="kpi"><b>${gp(p.gross_exposure_gp)}</b><span>exposure</span></div><div class="kpi"><b class="${cls(w.realized_pnl_gp)}">${gp(w.realized_pnl_gp)}</b><span>realized</span></div><div class="kpi"><b class="${cls(w.unrealized_pnl_gp)}">${gp(w.unrealized_pnl_gp)}</b><span>unrealized</span></div></div><p class="tiny">${esc(w.thesis)}</p><div class="module-strip">${(w.modules||[]).map(x=>`<span class="module">${esc(x.replaceAll('_',' '))}</span>`).join('')}</div></div></section>`;
}
function portfolioTable(){
  const p=currentTrader()?.portfolio_metrics||{};
  const rows=[['Cash share',pct(p.cash_share),'Liquid GP / net worth'],['Gross exposure',gp(p.gross_exposure_gp),'Conservative liquidation-mark inventory'],['Cost basis',gp(p.cost_basis_gp),'Capital paid for current holdings'],['Position HHI',ratio(p.position_hhi,3),'Concentration; higher = fewer/larger bets'],['Largest holding',pct(p.largest_position_share),'Share of net worth in largest position'],['Winning holdings',pct(p.winning_position_share),'Share of open holdings above cost at liquidation mark'],['Mean open ROI',pct(p.mean_unrealized_roi),'Average marked ROI across holdings'],['Mean hold',num(p.mean_holding_hours)==null?'–':`${Number(p.mean_holding_hours).toFixed(1)}h`,'Average age of current positions'],['Exposure share',pct(p.exposure_share),'Marked holdings / net worth'],['Position slots',pct(p.position_slot_utilization),'Open holdings / configured portfolio-position cap']];
  return `<section>${sectionTitle('Portfolio economics')}<div class="table-wrap"><table class="econ-table"><tbody>${rows.map(r=>`<tr><td>${esc(r[0])}<span class="desc">${esc(r[2])}</span></td><td>${r[1]}</td></tr>`).join('')}</tbody></table></div></section>`;
}
function holdings(){
  const w=currentTrader(),rows=w?.positions||[];
  return `<section>${sectionTitle('Holdings',`<span class="tiny">${rows.length}/${w?.strategy?.max_positions??'–'} portfolio positions</span>`)}<div class="list">${rows.length?rows.map(p=>`<details class="list-row"><summary><div class="summary-main"><b>${esc(p.name)}</b><span class="summary-sub">${gp(p.qty)} × ${gp(p.entry_price)} · liq ${gp(p.unit_liquidation)} ea${(p.tranches||1)>1?` · ${p.tranches} tranches`:''}</span></div><div class="summary-value ${cls(p.unrealized_roi)}"><b>${pct(p.unrealized_roi)}</b><span class="tiny">move ${pct(p.market_move_roi)}</span></div></summary><div class="detail-body"><div class="detail-grid"><div class="cell"><div class="label">Cost basis</div><div>${gp((p.qty||0)*(p.entry_price||0))} gp</div></div><div class="cell"><div class="label">Liquidation value</div><div>${gp(p.value_gp)} gp</div></div><div class="cell"><div class="label">Entry EV</div><div>${pct(p.entry_expected_roi)}</div></div><div class="cell"><div class="label">Entry conviction</div><div>${pct(p.entry_conviction)}</div></div><div class="cell"><div class="label">Risk budget</div><div>${pct(p.risk_budget_pct)}</div></div><div class="cell"><div class="label">Opened</div><div>${age(p.opened_at)}</div></div></div></div></details>`).join(''):`<div class="empty">No holdings.</div>`}</div></section>`;
}
const factorHelp={edge:'Expected post-tax microstructure rent.',momentum:'Short-horizon midpoint impulse.',flow:'Volume acceleration.',liquidity:'Turnover-derived execution/liquidity quality.',history:'Cached historical trend signal.',mean_reversion:'Historical z-score reversion lens.',cross_factor:'Interaction/confirmation among momentum, flow, edge and liquidity.',volatility:'Penalty or controlled appetite for noisy history.',crowding:'Penalty for excessive turnover concentration in one item.',patch:'Usual weekly update-window prior.',ai_prior:'Bounded semantic model prior. Never directly changes prices/P&L.',freshness:'Quote-recency bonus.'};
function factorPill(name,value){const v=num(value)||0;return `<span class="factor ${v>0?'pos':v<0?'neg':'zero'}" title="${esc(factorHelp[name]||name)}">${esc(name.replaceAll('_',' '))} ${v>0?'↑':v<0?'↓':'→'} ${v>0?'+':''}${v.toFixed(1)}</span>`}
function topFactors(c){return Object.entries(c.score_components||{}).sort((a,b)=>Math.abs(b[1])-Math.abs(a[1])).slice(0,3).map(([k,v])=>`${k.replaceAll('_',' ')} ${v>=0?'↑':'↓'}${Math.abs(v).toFixed(0)}`).join(' · ')}
function lensPills(c){return Object.entries(c.strategy_lenses||{}).map(([k,v])=>`<span class="factor ${num(v)>0?'pos':num(v)<0?'neg':'zero'}">${esc(k.replaceAll('_',' '))} ${signed(v,2)}</span>`).join('')}
function opportunities(){
  const w=currentTrader(),rows=w?.top_candidates||[];
  return `<section>${sectionTitle('Opportunity book',`<span class="tiny">${gp(w?.eligible_candidates)} eligible · score ≠ probability</span>`)}<div class="list">${rows.length?rows.map((c,i)=>`<details class="list-row"><summary><div class="summary-main"><b>${i+1}. ${esc(c.name)}</b><span class="summary-sub">${topFactors(c)||`fill ${pct(c.fill_probability)}`}</span></div><div class="summary-value"><b class="${cls(c.expected_roi)}">EV ${pct(c.expected_roi)}</b><span class="tiny">score ${num(c.score)?.toFixed(1)??'–'} · conv ${pct(c.conviction,0)}</span></div></summary><div class="detail-body"><div class="callout">EV = completed spread capture − expected inventory/adverse-selection cost. Score then layers deterministic factors plus a bounded semantic prior.</div><div class="factor-wrap">${Object.entries(c.score_components||{}).map(([k,v])=>factorPill(k,v)).join('')}</div>${Object.keys(c.strategy_lenses||{}).length?`<div class="factor-wrap">${lensPills(c)}</div>`:''}<div class="detail-grid"><div class="cell"><div class="label">Spread capture EV</div><div>${gp(c.spread_capture_ev_gp)} gp/unit</div></div><div class="cell"><div class="label">Inventory-risk EV</div><div class="down">−${gp(c.inventory_risk_ev_gp)} gp/unit</div></div><div class="cell"><div class="label">Completion</div><div>${pct(c.fill_probability)}</div></div><div class="cell"><div class="label">Inventory state</div><div>${pct(c.inventory_probability)}</div></div><div class="cell"><div class="label">Momentum</div><div class="${cls(c.momentum_5m_vs_1h)}">${pct(c.momentum_5m_vs_1h)}</div></div><div class="cell"><div class="label">Flow accel</div><div>${signed(c.volume_acceleration,2)}×</div></div><div class="cell"><div class="label">Risk budget</div><div>${pct(c.risk_budget_pct)}</div></div><div class="cell"><div class="label">Capacity</div><div>${gp(c.capacity_qty)} units / ${shortGp(c.capacity_gp)} gp</div></div><div class="cell"><div class="label">Kelly proxy</div><div>${pct(c.kelly_fraction_proxy)}</div></div><div class="cell"><div class="label">AI size multiplier</div><div>${ratio(c.ai_risk_multiplier,3)}×</div></div></div></div></details>`).join(''):'<div class="empty">No eligible opportunities.</div>'}</div></section>`;
}
function prettyKey(k){return String(k).replaceAll('_',' ').replace(/\b\w/g,m=>m.toUpperCase())}
function mathRows(obj){if(!obj||typeof obj!=='object')return'';return Object.entries(obj).map(([k,v])=>`<tr><td>${esc(prettyKey(k))}</td><td>${typeof v==='number'?Number(v).toLocaleString(undefined,{maximumFractionDigits:6}):esc(v)}</td></tr>`).join('')}
function actionLog(){
  const rows=(currentTrader()?.recent_actions||[]).slice().reverse();
  return `<section>${sectionTitle('Action log','<span class="tiny">auditable execution trail</span>')}<div class="list">${rows.length?rows.map(a=>{const buy=a.side==='BUY';const val=buy?-(num(a.cost_gp)||0):(num(a.pnl_gp)||0);return `<details class="list-row ${buy?'action-buy':'action-sell'}"><summary><div class="summary-main"><b>${esc(a.side)} · ${esc(a.name)}</b><span class="summary-sub">${timeLabel(a.at)} · ${gp(a.qty)} units · ${esc(a.reason||'decision')}</span></div><div class="summary-value ${buy?'':cls(val)}"><b>${buy?`−${shortGp(a.cost_gp)}`:`${num(a.pnl_gp)>=0?'+':''}${shortGp(a.pnl_gp)}`}</b><span class="tiny">${buy?`EV ${pct(a.expected_roi)}`:`ROI ${pct(a.roi)}`}</span></div></summary><div class="detail-body"><div class="callout">${esc(a.reasoning||'Deterministic engine action.')}</div>${(a.top_components||[]).length?`<div class="factor-wrap">${a.top_components.map(x=>factorPill(x.factor,x.points)).join('')}</div>`:''}${a.strategy_lenses?`<div class="factor-wrap">${Object.entries(a.strategy_lenses).map(([k,v])=>`<span class="factor">${esc(k.replaceAll('_',' '))} ${signed(v,2)}</span>`).join('')}</div>`:''}<div class="table-wrap more-note"><table><tbody>${mathRows(a.math)}${mathRows({unit_price:a.unit_price,qty:a.qty,held_hours:a.held_hours,market_move_roi:a.market_move_roi,ai_prior_points:a.ai_prior_points})}</tbody></table></div></div></details>`}).join(''):'<div class="empty">No actions recorded yet.</div>'}</div></section>`;
}
function strategyPolicy(){const w=currentTrader(),s=w?.strategy||{};return `<details class="group"><summary>Strategy policy & limits</summary><div class="group-body"><div class="table-wrap"><table><tbody>${mathRows({max_positions:s.max_positions,reserve_pct:s.reserve_pct,max_position_pct:s.max_position_pct,max_participation_rate:s.max_participation_rate,take_profit:s.take_profit,stop_loss:s.stop_loss,soft_rotate_hours:s.soft_rotate_hours,max_hold_hours:s.max_hold_hours,ai_sensitivity:s.ai_sensitivity,ai_score_cap:s.ai_score_cap,allow_scale_in:s.allow_scale_in,max_tranches:s.max_tranches})}</tbody></table></div></div></details>`}
function tradersView(){return `${traderHero()}${portfolioTable()}${holdings()}${opportunities()}${actionLog()}${strategyPolicy()}`}

function itemsView(){
  const rows=(data.market?.items||[]).filter(r=>!itemQuery||String(r.name||'').toLowerCase().includes(itemQuery.toLowerCase())||String(r.id||'').includes(itemQuery));
  return `<section>${sectionTitle('Item tape',`<span class="tiny">showing ${rows.length}/${(data.market?.items||[]).length} published hot rows</span>`)}<div class="callout">The strategies and economy metrics ingest the full valid market snapshot. This browser intentionally publishes only a bounded hot set to keep hourly Git/Pages payloads sane.</div><input class="search" value="${esc(itemQuery)}" oninput="setItemQuery(this.value)" placeholder="Search item or ID"><div class="list">${rows.slice(0,120).map(r=>`<details class="list-row"><summary><div class="summary-main"><b>${esc(r.name)}</b><span class="summary-sub">low ${gp(r.low)} · high ${gp(r.high)} · turnover ${shortGp(r.turnover_gp_1h)} gp/h</span></div><div class="summary-value ${cls(r.momentum_5m_vs_1h)}"><b>${pct(r.momentum_5m_vs_1h)}</b><span class="tiny">spread ${pct(r.spread_roi)}</span></div></summary><div class="detail-body"><div class="detail-grid"><div class="cell"><div class="label">5m midpoint</div><div>${gp(r.mid_5m)}</div></div><div class="cell"><div class="label">1h midpoint</div><div>${gp(r.mid_1h)}</div></div><div class="cell"><div class="label">Volume 5m</div><div>${gp(r.volume_5m)}</div></div><div class="cell"><div class="label">Volume 1h</div><div>${gp(r.volume_1h)}</div></div><div class="cell"><div class="label">Volume accel</div><div>${signed(r.volume_acceleration,2)}×</div></div><div class="cell"><div class="label">High/low flow imbalance</div><div class="${cls(r.high_low_volume_imbalance)}">${signed(r.high_low_volume_imbalance,3)}</div></div><div class="cell"><div class="label">Liquidity proxy</div><div>${ratio(r.liquidity_score,3)}</div></div><div class="cell"><div class="label">Impact proxy</div><div>${num(r.market_impact_proxy)==null?'–':Number(r.market_impact_proxy).toExponential(2)}</div></div><div class="cell"><div class="label">Turnover share</div><div>${pct(r.turnover_share,3)}</div></div><div class="cell"><div class="label">Quote age</div><div>${ratio(r.quote_age_minutes,1)}m</div></div></div></div></details>`).join('')||'<div class="empty">No matching items.</div>'}</div></section>`;
}

const econRows = e => [
  ['Direction',null,null],
  ['Raw breadth',pct(e.breadth),'(advancers − decliners) / directional items'],
  ['Turnover-weighted breadth',pct(e.turnover_weighted_breadth),'Direction weighted by each item’s GP turnover share'],
  ['Price pressure',pct(e.turnover_weighted_price_pressure),'Turnover-weighted short-run midpoint movement; not CPI'],
  ['Median momentum',pct(e.median_momentum),'Median 5m midpoint relative to 1h midpoint'],
  ['Median |momentum|',pct(e.median_abs_momentum),'Typical absolute short-run move'],
  ['Momentum dispersion',pct(e.momentum_dispersion),'Cross-sectional standard deviation of short-run momentum'],
  ['Adv / dec / flat',`${gp(e.advancers)} / ${gp(e.decliners)} / ${gp(e.flat)}`,'Count of tracked directional states'],
  ['Activity & flow',null,null],
  ['Active share',pct(e.active_share),'Share whose 5m pace exceeds the 1h baseline'],
  ['Median volume acceleration',`${signed(e.median_volume_acceleration,2)}×`,'Median annualized 5m volume pace relative to 1h'],
  ['P90 volume acceleration',`${signed(e.p90_volume_acceleration,2)}×`,'90th-percentile activity burst'],
  ['Turnover-weighted flow imbalance',signed(e.turnover_weighted_volume_imbalance,3),'High-price-side versus low-price-side recent transaction volume'],
  ['Shock share',pct(e.shock_share),'Share with |short-run momentum| ≥ 2%'],
  ['Total hourly turnover',`${shortGp(e.total_turnover_gp_1h)} gp`,'Observed aggregate GP notional over 1h'],
  ['Total hourly unit volume',gp(e.total_volume_units_1h),'Aggregate units exchanged in 1h'],
  ['Median item turnover',`${shortGp(e.median_turnover_gp_1h)} gp`,'Median item-level hourly GP turnover'],
  ['Liquidity & friction',null,null],
  ['Median spread',pct(e.median_spread),'Median observed high/low spread'],
  ['Turnover-weighted spread',pct(e.turnover_weighted_spread),'Spread weighted by economic activity'],
  ['Spread dispersion',pct(e.spread_dispersion),'Cross-sectional spread variability'],
  ['Median liquidity',ratio(e.median_liquidity,3),'Turnover-derived liquidity proxy, 0–1'],
  ['Stale quote share',pct(e.stale_share),'Share whose latest quote age exceeds 15m'],
  ['Extreme-spread share',pct(e.extreme_spread_share),'Share with spread ≥ 5%'],
  ['Liquidity stress',num(e.liquidity_stress)==null?'–':`${(100*e.liquidity_stress).toFixed(0)}/100`,'Composite execution-stress proxy'],
  ['Concentration',null,null],
  ['Top-1 turnover share',pct(e.top1_turnover_share),'Largest item’s share of aggregate hourly turnover'],
  ['Top-5 turnover share',pct(e.top5_turnover_share),'Five largest items’ share'],
  ['Top-10 turnover share',pct(e.top10_turnover_share),'Ten largest items’ share'],
  ['Turnover HHI',ratio(e.turnover_hhi,4),'Squared-share concentration index'],
  ['Turnover Gini',ratio(e.turnover_gini,3),'Inequality of item turnover, 0–1'],
  ['Members turnover share',pct(e.members_turnover_share),'Share of tracked turnover in members items'],
  ['Regime & risk',null,null],
  ['Risk appetite proxy',num(e.risk_appetite_proxy)==null?'–':`${(100*e.risk_appetite_proxy).toFixed(0)}/100`,'Pressure + activity composite; descriptive, not sentiment truth'],
  ['Market temperature',num(e.market_temperature)==null?'–':`${Number(e.market_temperature).toFixed(0)}/100`,'Activity/dislocation composite'],
  ['Patch prior',null,null],
  ['Usual update phase',esc(e.patch?.phase||'–'),'Deterministic weekly schedule prior; official news is separate evidence'],
  ['Schedule risk',pct(e.patch?.risk,0),'Proximity-based update-window risk prior'],
  ['Hours to usual update',num(e.patch?.hours_to_usual_update)==null?'–':`${Number(e.patch.hours_to_usual_update).toFixed(1)}h`,'Time to next configured usual weekly update window'],
];
function econTable(){const rows=econRows(economy());return `<div class="table-wrap"><table class="econ-table"><tbody>${rows.map(([name,val,desc])=>val==null?`<tr class="group-row"><td colspan="2">${esc(name)}</td></tr>`:`<tr><td>${esc(name)}<span class="desc">${esc(desc)}</span></td><td>${val}</td></tr>`).join('')}</tbody></table></div>`}
function replay(){
  const s=data.simulation||{},ws=s.wallets||{}; if(!Object.keys(ws).length)return'<div class="panel"><span class="tiny">72h diagnostic replay will populate on its bounded refresh cadence.</span></div>';
  return `<div class="panel"><div class="tiny">Read-only ${s.window_hours||s.requested_hours||72}h diagnostic · ${s.generated_at?age(s.generated_at):'–'} · ${s.universe_items||'–'} items. Hourly bars approximate intrahour queue/fill behavior.</div><div class="table-wrap more-note"><table><thead><tr><th>Trader</th><th>Return</th><th>Max DD</th><th>Trades</th><th>End</th></tr></thead><tbody>${Object.entries(ws).map(([slug,w])=>`<tr><td>${esc(w.name||data.wallets?.[slug]?.name||slug)}</td><td class="${cls(w.return_pct)}">${pct(w.return_pct)}</td><td class="down">${pct(w.max_drawdown)}</td><td>${gp(w.trades)}</td><td>${shortGp(w.end_gp)} gp</td></tr>`).join('')}</tbody></table></div></div>`;
}
function economyView(){return `<section>${sectionTitle('Economics / market structure','<span class="tiny">full valid market cross-section</span>')}${economyCards()}</section><section>${sectionTitle('Compact metric ledger')}${econTable()}</section><section>${sectionTitle('Semantic prior')}${biasStrip()}</section><section>${sectionTitle('72h replay')}${replay()}</section>`}

function researchView(){
  const r=data.deterministic_research||{},ai=data.intelligence||{},aux=ai.auxiliary||[];
  const events=[...(r.official||[]),...(r.search||[])].filter(x=>!x.error);
  return `<section>${sectionTitle('Deterministic research',`<span class="tiny">search ${esc(r.search_status||'–')}</span>`)}<div class="panel">${events.length?events.map(e=>`<div class="event">${e.url?`<a href="${esc(e.url)}" target="_blank" rel="noopener"><b>${esc(e.title||'Untitled')}</b></a>`:`<b>${esc(e.title||'Untitled')}</b>`}<span class="tiny">${esc(e.evidence_class||e.source||'source')} · ${esc(e.source||'')}</span>${e.snippet?`<p>${esc(e.snippet)}</p>`:''}</div>`).join(''):'<div class="empty">No research rows.</div>'}</div></section><section>${sectionTitle('Model peer notes')}<div class="panel">${aux.length?aux.map(a=>`<details class="group"><summary>${esc(a.kind||a.label||'peer')} · ${esc(a.status||'–')}</summary><div class="group-body"><div class="code">${esc(typeof a.result==='string'?a.result:JSON.stringify(a.result||{},null,2))}</div></div></details>`).join(''):'<span class="tiny">Peer critiques are attached to advisory refreshes rather than every hourly trading cycle.</span>'}</div></section>`;
}
function reportsView(){
  const rows=reports.slice().reverse().slice(0,40), priors=advisorHistory.slice().reverse().slice(0,24), current=data.intelligence||{};
  return `<section>${sectionTitle('Economy reports','<span class="tiny">semantic layer · default 8h</span>')}<div class="panel report-card"><time>${current.generated_at?dateTime(current.generated_at):'current'}</time><p class="brief">${esc(current.economy_brief||current.summary||'No report yet.')}</p>${current.regime?`<div class="tiny">${esc(current.regime)}</div>`:''}</div>${rows.map(r=>`<div class="panel report-card"><time>${dateTime(r.generated_at)}</time><p class="brief">${esc(r.economy_brief||r.summary||'')}</p><div class="tiny">${esc(r.regime||'')} · ${esc(r.model||'')}</div></div>`).join('')}</section><section>${sectionTitle('Latest advisory ensemble')}<div class="panel">${biasStrip()}${(data.advisory?.rationale||[]).length?`<ul class="clean-list">${data.advisory.rationale.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}</div></section><section>${sectionTitle('Advisory history','<span class="tiny">default 4h</span>')}<div class="table-wrap"><table><thead><tr><th>At</th><th>Macro</th><th>Mom</th><th>Revert</th><th>Liq</th><th>Risk</th><th>Conf</th></tr></thead><tbody>${priors.map(a=>`<tr><td>${timeLabel(a.generated_at)}</td><td class="${cls(a.biases?.macro)}">${signed(a.biases?.macro,2)}</td><td class="${cls(a.biases?.momentum)}">${signed(a.biases?.momentum,2)}</td><td class="${cls(a.biases?.mean_reversion)}">${signed(a.biases?.mean_reversion,2)}</td><td class="${cls(a.biases?.liquidity)}">${signed(a.biases?.liquidity,2)}</td><td class="${cls(a.biases?.risk)}">${signed(a.biases?.risk,2)}</td><td>${pct(a.confidence,0)}</td></tr>`).join('')}</tbody></table></div></section>`;
}

async function historyView(){
  const ds=days.days||[]; if(!selectedDay)selectedDay=new URLSearchParams(location.search).get('day')||ds[0]||'';
  const idx=Math.max(0,ds.indexOf(selectedDay)); const doc=selectedDay?await fetchJson(`data/days/${selectedDay}.json`,{date:selectedDay,runs:[]}):{runs:[]}; const rows=(doc.runs||[]).slice().reverse();
  return `<section>${sectionTitle('Daily history')}<div class="daynav"><button onclick="moveDay(1)" ${idx>=ds.length-1?'disabled':''}>← older</button><b>${esc(selectedDay||'no day')}</b><button onclick="moveDay(-1)" ${idx<=0?'disabled':''}>newer →</button></div>${rows.map(r=>`<details class="group"><summary>${timeLabel(r.at)} · ${esc(r.version||'')} · ${badge(r.health?.status||'unknown',r.health?.status==='ok'?'pos':'warn')}</summary><div class="group-body"><div class="table-wrap"><table><thead><tr><th>Trader</th><th>Net worth</th><th>Liquid</th><th>Return</th><th>Holdings</th><th>Actions</th></tr></thead><tbody>${Object.entries(r.wallets||{}).map(([slug,w])=>`<tr><td>${esc(data.wallets?.[slug]?.name||slug)}</td><td>${gp(w.net_worth_gp??w.value_gp)}</td><td>${gp(w.liquid_gp??w.cash_gp)}</td><td class="${cls(w.return_pct)}">${pct(w.return_pct)}</td><td>${gp(w.positions)}</td><td>${(w.trades||[]).length}</td></tr>`).join('')}</tbody></table></div>${r.intelligence?.economy_brief?`<p class="brief">${esc(r.intelligence.economy_brief)}</p>`:''}</div></details>`).join('')||'<div class="empty">No observations for this day.</div>'}</section>`;
}
function opsView(){
  const latest=data.run||{},rows=(runs.runs||[]).slice(0,30);
  return `<section>${sectionTitle('Ops / run health')}<div class="panel"><div class="row"><b>${esc(latest.health?.status||'unknown')}</b><span class="tiny">${esc(latest.run_id||'legacy')} · ${latest.at?age(latest.at):'–'}</span></div>${(latest.health?.warnings||[]).length?`<ul class="clean-list">${latest.health.warnings.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:'<div class="tiny more-note">No current warnings.</div>'}</div><div class="table-wrap"><table><thead><tr><th>Run</th><th>Health</th><th>AI cost</th><th>Advisory</th><th>Report</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${r.url?`<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.run_id)}</a>`:esc(r.run_id)}</td><td>${esc(r.health?.status||'–')}</td><td>${num(r.intelligence?.total_cost)==null?(num(r.intelligence?.cost)==null?'–':`$${Number(r.intelligence.cost).toFixed(5)}`):`$${Number(r.intelligence.total_cost).toFixed(5)}`}</td><td>${esc(r.intelligence?.advisory?.freshness||r.intelligence?.advisory_status||'–')}</td><td>${esc(r.intelligence?.report?.freshness||r.intelligence?.freshness||'–')}</td></tr>`).join('')}</tbody></table></div></section>`;
}

function strategyMixer(){
  const w=currentTrader(),c=w?.top_candidates?.[0],parts=c?.score_components||{};
  if(!c||!Object.keys(parts).length)return '<div class="empty">Mixer populates from the selected trader’s top scored candidate after a v0.5 cycle.</div>';
  const active=Object.entries(parts).filter(([k])=>!mixerOff.has(k));
  const whatif=active.reduce((a,[,v])=>a+(num(v)||0),0);
  return `<div class="panel"><div class="row"><div class="stack"><b>${esc(w.name)} · ${esc(c.name)}</b><span class="tiny">client-side what-if only; live strategy/state is untouched</span></div><b>${whatif.toFixed(1)}</b></div><div class="module-strip">${Object.entries(parts).map(([k,v])=>`<button class="module ${mixerOff.has(k)?'off':''}" onclick="toggleMixer('${esc(k)}')">${esc(k.replaceAll('_',' '))} ${signed(v,1)}</button>`).join('')}</div><div class="tiny more-note">Toggle factor contributions on/off to inspect how this candidate’s current score is assembled. This does not re-fit fill probabilities, EV or position sizing.</div></div>`;
}
function strategyMatrix(){
  const ws=Object.values(data.wallets||{}),mods=[...new Set(ws.flatMap(w=>w.modules||[]))];
  if(!mods.length)return'<div class="empty">Module map will appear after the first v0.5 trading cycle.</div>';
  return `<div class="table-wrap"><table class="matrix"><thead><tr><th>Layer</th>${ws.map(w=>`<th>${esc(w.name)}</th>`).join('')}</tr></thead><tbody>${mods.map(m=>`<tr><td>${esc(m.replaceAll('_',' '))}</td>${ws.map(w=>`<td class="${(w.modules||[]).includes(m)?'check':'dash'}">${(w.modules||[]).includes(m)?'✓':'—'}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function methodView(){return `<section>${sectionTitle('Execution math')}<div class="code">passive entry ≈ observed low × (1 + entry penalty)\npassive exit net ≈ observed high × (1 − exit penalty) − GE tax\nliquidation mark ≈ observed low × (1 − slippage) − GE tax\n\ncompletion = P(entry fill) × P(exit fill)\ninventory state = P(entry fill) × [1 − P(exit fill)]\nspread-capture EV = completion × quoted post-tax edge\ninventory-risk EV = inventory state × adverse-selection cost\nexpected edge = spread-capture EV − inventory-risk EV</div></section><section>${sectionTitle('Layered score')}<div class="code">score = edge + momentum + flow + liquidity + history\n      + mean reversion + cross-factor interaction\n      − volatility/crowding controls + patch term\n      + bounded AI prior + freshness\n\nconviction = deterministic consensus/quality composite\nsize = base risk × deterministic conviction × bounded AI risk multiplier\nsize ≤ profile cap and observed-volume participation capacity</div><div class="callout more-note">Score is an ordinal opportunity objective, not a calibrated probability. “Kelly” is explicitly a Kelly-inspired sizing proxy because the simulator does not possess a calibrated outcome distribution.</div></section><section>${sectionTitle('Bounded semantic prior')}<div class="code">models receive the same derived economy + market + historical + research packet\npaid anchor + free peers → confidence-weighted bounded biases\n\nnormal traders: AI score contribution only a few points\nFrontier Lab: larger but still capped contribution\nLLM never writes prices, tax, P&L, fills, cash or position state</div></section><section>${sectionTitle('Weekly update prior')}<div class="code">usual weekly update schedule → deterministic proximity risk\nofficial RSS/news → separate evidence layer\nmodels may interpret catalysts; schedule proximity itself is deterministic</div></section><section>${sectionTitle('Strategy stack')}${strategyMatrix()}</section><section>${sectionTitle('What-if factor mixer')}${strategyMixer()}</section><section>${sectionTitle('Composable idea')}<div class="panel"><p class="brief">The strategies are already built from orthogonal lenses rather than one monolithic equation. A future what-if mixer can cross compatible modules client-side without silently changing the live paper funds; production execution should remain versioned and auditable.</p></div></section>`}
function moreView(){return `<section>${sectionTitle('More')}<div class="quick-grid">${quick('Research','Official/news evidence and peer critique','research')}${quick('Reports','State-of-economy report history','reports')}${quick('History','Daily snapshots','history')}${quick('Ops','Run health, cost and CI audit','ops')}${quick('Method','Formulae, priors and strategy layers','method')}${quick('Economy','Full compact metric ledger','economy')}</div></section>`}

function activeNav(){document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===(['research','reports','history','ops','method'].includes(view)?'more':view)))}
function bindHelp(){document.querySelectorAll('.help').forEach(b=>b.onclick=e=>{e.stopPropagation();b.classList.toggle('open')})}
async function render(){activeNav();let html='';if(view==='general')html=general();else if(view==='traders')html=tradersView();else if(view==='items')html=itemsView();else if(view==='economy')html=economyView();else if(view==='research')html=researchView();else if(view==='reports')html=reportsView();else if(view==='history')html=await historyView();else if(view==='ops')html=opsView();else if(view==='method')html=methodView();else html=moreView();$('#app').innerHTML=html;bindHelp()}
function goView(v){view=v;render();window.scrollTo({top:0,behavior:'auto'})}
function openTrader(id){trader=id;view='traders';render();window.scrollTo({top:0,behavior:'auto'})}
function selectTrader(id){trader=id;render()}
function setItemQuery(v){itemQuery=v;render()}
function toggleMixer(k){if(mixerOff.has(k))mixerOff.delete(k);else mixerOff.add(k);render()}
function moveDay(delta){const ds=days.days||[],idx=ds.indexOf(selectedDay),next=ds[idx+delta];if(!next)return;selectedDay=next;const u=new URL(location.href);u.searchParams.set('day',selectedDay);history.replaceState({},'',u);render()}

document.querySelectorAll('#nav button').forEach(b=>b.onclick=()=>goView(b.dataset.view));

(async()=>{
  try{
    [data,days,runs,reports,advisorHistory]=await Promise.all([
      fetchJson('data/latest_snapshot.json',{}),
      fetchJson('data/days/index.json',{days:[]}),
      fetchJson('data/runs/index.json',{runs:[]}),
      fetchJsonl('data/intelligence/history.jsonl'),
      fetchJsonl('data/intelligence/advisory_history.jsonl'),
    ]);
    if(!data.wallets)throw new Error('No trader snapshot');
    const ids=traderIds(); trader=ids.includes('velocity')?'velocity':ids[0]||'';
    const series=await Promise.all(ids.map(id=>fetchJsonl(`data/wallets/${id}/equity_history.jsonl`)));
    ids.forEach((id,i)=>histories[id]=series[i]);
    $('#updated').textContent=data.updated_at?age(data.updated_at):'no snapshot time';
    await render();
  }catch(err){$('#app').innerHTML=`<div class="loading">Unable to load paper-trader data: ${esc(err?.message||err)}</div>`}
})();
