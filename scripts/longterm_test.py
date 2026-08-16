#!/usr/bin/env python3
import argparse, json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import STARTING_GP, PROFILES, VERSION
from src.strategy import wallet_candidates, liquidation_unit
from src.portfolio import fresh_wallet, open_positions
import random
from src.io_utils import DATA, read_json, write_json


def parse_jsonl(path):
    rows=[];errors=[]
    if not path.exists(): return rows,errors
    for i,line in enumerate(path.read_text().splitlines(),1):
        if not line.strip(): continue
        try: rows.append(json.loads(line))
        except json.JSONDecodeError as exc: errors.append(f'{path}:{i}: {exc.msg}')
    return rows,errors


def wallet_audit(slug):
    base=DATA/'wallets'/slug
    portfolio=read_json(base/'portfolio.json',{})
    journal,parse_errors=parse_jsonl(base/'journal.jsonl')
    equity,equity_errors=parse_jsonl(base/'equity_history.jsonl')
    errors=list(parse_errors)+list(equity_errors);warnings=[]
    cash=STARTING_GP;inventory=defaultdict(int);realized=0;reasons=Counter();immediate_stops=0
    last_at=None
    for trade in journal:
        try:
            at=datetime.fromisoformat(trade['at'])
            if last_at and at < last_at: errors.append(f'{slug}: journal timestamp regression')
            last_at=at
            qty=int(trade['qty']); item=int(trade['item_id'])
            if qty<=0: errors.append(f'{slug}: non-positive qty in journal')
            if trade.get('side')=='BUY':
                cost=int(trade.get('cost_gp',qty*int(trade['unit_price'])));cash-=cost;inventory[item]+=qty
            elif trade.get('side')=='SELL':
                if inventory[item] < qty: errors.append(f'{slug}: sold {item} below reconstructed inventory')
                inventory[item]-=qty;cash+=qty*int(trade['unit_price']);realized+=int(trade.get('pnl_gp',0));reasons[trade.get('reason','unknown')]+=1
                if trade.get('reason')=='stop_loss' and float(trade.get('held_hours',99))<.25: immediate_stops+=1
            else: errors.append(f'{slug}: unknown side {trade.get("side")}')
        except (KeyError,TypeError,ValueError) as exc: errors.append(f'{slug}: malformed trade {type(exc).__name__}')
    state_inventory=defaultdict(int)
    for p in portfolio.get('positions',[]): state_inventory[int(p['item_id'])]+=int(p['qty'])
    if dict((k,v) for k,v in inventory.items() if v) != dict((k,v) for k,v in state_inventory.items() if v): errors.append(f'{slug}: journal inventory != portfolio inventory')
    if portfolio:
        if cash != int(portfolio.get('cash_gp',-1)): errors.append(f'{slug}: reconstructed cash {cash} != state {portfolio.get("cash_gp")}')
        if realized != int(portfolio.get('realized_pnl_gp',0)): errors.append(f'{slug}: reconstructed realized {realized} != state {portfolio.get("realized_pnl_gp")}')
        ids=[p.get('item_id') for p in portfolio.get('positions',[])]
        if len(ids)!=len(set(ids)): errors.append(f'{slug}: duplicate item positions')
        if len(ids)>PROFILES[slug].max_positions: errors.append(f'{slug}: max positions exceeded')
    if immediate_stops: warnings.append(f'{slug}: {immediate_stops} historical stop-loss exits occurred within 15 minutes; v0.4 regression tests prevent new friction-only stops')
    eq_times=[]
    for row in equity:
        try:
            eq_times.append(datetime.fromisoformat(row['at']))
            if row.get('value_gp',0)<0 or row.get('cash_gp',0)<0: errors.append(f'{slug}: negative equity-history balance')
        except Exception: errors.append(f'{slug}: malformed equity history row')
    if any(b<a for a,b in zip(eq_times,eq_times[1:])): errors.append(f'{slug}: equity history timestamp regression')
    return {
        'slug':slug,'journal_rows':len(journal),'equity_points':len(equity),'open_positions':len(portfolio.get('positions',[])),
        'cash_gp':portfolio.get('cash_gp'),'realized_pnl_gp':portfolio.get('realized_pnl_gp'),'exit_reasons':dict(reasons),
        'historical_immediate_stops':immediate_stops,'errors':errors,'warnings':warnings,
    }


def archive_audit():
    errors=[];warnings=[];days=0;runs=0
    days_dir=DATA/'days'
    for path in sorted(days_dir.glob('????-??-??.json')):
        doc=read_json(path,None)
        if not isinstance(doc,dict) or not isinstance(doc.get('runs'),list): errors.append(f'{path}: malformed day archive');continue
        days+=1;runs+=len(doc['runs'])
        times=[]
        for row in doc['runs']:
            try: times.append(datetime.fromisoformat(row['at']))
            except Exception: errors.append(f'{path}: malformed run timestamp')
        if any(b<a for a,b in zip(times,times[1:])): errors.append(f'{path}: run timestamp regression')
    intel,ie=parse_jsonl(DATA/'intelligence'/'history.jsonl');errors.extend(ie)
    return {'days':days,'archived_runs':runs,'intelligence_rows':len(intel),'errors':errors,'warnings':warnings}


def strategy_divergence():
    latest=read_json(DATA/'latest_snapshot.json',{})
    wallets=latest.get('wallets',{})
    a=[x.get('id') for x in wallets.get('velocity',{}).get('top_candidates',[])[:10]]
    b=[x.get('id') for x in wallets.get('market_maker',{}).get('top_candidates',[])[:10]]
    if not a or not b:return {'overlap':None,'warning':'candidate books unavailable'}
    overlap=len(set(a)&set(b))/max(1,min(len(a),len(b)))
    return {'overlap':round(overlap,3),'warning':'wallet rankings are unusually similar' if overlap>.9 else None}



def synthetic_stress(cases=500):
    rng=random.Random(404)
    errors=[];eligible={slug:0 for slug in PROFILES};rankings={slug:[] for slug in PROFILES}
    rows=[]
    for item_id in range(1,cases+1):
        low=rng.randint(100,2_000_000); spread=rng.uniform(.002,.14); high=max(low+1,int(low*(1+spread)))
        v1=rng.randint(20,20_000); v5=rng.randint(0,max(1,v1//3)); momentum=rng.uniform(-.08,.16); accel=max(-1,min(5,(v5*12/max(v1,1))-1))
        rows.append({'id':item_id,'name':f'synthetic-{item_id}','members':True,'limit':rng.choice([None,8,70,100,1000]),'highalch':None,'high':high,'low':low,'spread_roi':(high-low)/low,'momentum_5m_vs_1h':momentum,'volume_5m':v5,'volume_1h':v1,'volume_acceleration':accel,'turnover_gp_1h':v1*low,'liquidity_score':rng.uniform(.25,1),'quote_age_minutes':rng.uniform(0,25)})
    for slug,profile in PROFILES.items():
        candidates=wallet_candidates(rows,profile,{'items':{}});eligible[slug]=len(candidates);rankings[slug]=[c['id'] for c in candidates[:20]]
        for c in candidates:
            for key in ('expected_roi','entry_fill_probability','exit_fill_probability','fill_probability','risk_budget_pct','score'):
                if not math.isfinite(float(c[key])):errors.append(f'{slug}: non-finite {key}')
            if not (0<=c['entry_fill_probability']<=1 and 0<=c['exit_fill_probability']<=1 and 0<=c['fill_probability']<=1):errors.append(f'{slug}: invalid probability')
            if not (0<c['risk_budget_pct']<=profile.max_position_pct):errors.append(f'{slug}: invalid risk budget')
        wallet=fresh_wallet(profile);latest={str(r['id']):{'low':r['low']} for r in rows};open_positions(wallet,candidates,latest,profile)
        if wallet['cash_gp']<0:errors.append(f'{slug}: synthetic overspend')
        if len(wallet['positions'])>profile.max_positions:errors.append(f'{slug}: synthetic max positions exceeded')
        if len({p['item_id'] for p in wallet['positions']})!=len(wallet['positions']):errors.append(f'{slug}: synthetic duplicate positions')
    overlap=len(set(rankings['velocity'])&set(rankings['market_maker']))/max(1,min(len(rankings['velocity']),len(rankings['market_maker'])))
    if eligible['velocity']==0 or eligible['market_maker']==0:errors.append('synthetic matrix produced no eligible candidates')
    return {'cases':cases,'eligible':eligible,'top20_overlap':round(overlap,3),'errors':errors}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['fast','deep'],default='fast');parser.add_argument('--report-dir',default='build/quality');args=parser.parse_args()
    report_dir=Path(args.report_dir);report_dir.mkdir(parents=True,exist_ok=True)
    wallets=[wallet_audit(slug) for slug in PROFILES]
    archive=archive_audit();divergence=strategy_divergence()
    errors=[e for wallet in wallets for e in wallet['errors']]+archive['errors']
    warnings=[w for wallet in wallets for w in wallet['warnings']]+archive['warnings']
    if divergence.get('warning'):warnings.append(divergence['warning'])
    stress=synthetic_stress(500 if args.mode=='deep' else 180);errors.extend(stress['errors'])
    latest=read_json(DATA/'latest_snapshot.json',{})
    if latest and latest.get('version') not in {'0.3',VERSION}:warnings.append(f"unexpected persisted snapshot version {latest.get('version')}")
    report={'version':VERSION,'mode':args.mode,'status':'fail' if errors else ('warn' if warnings else 'ok'),'errors':errors,'warnings':warnings,'wallets':wallets,'archive':archive,'strategy_divergence':divergence,'synthetic_stress':stress}
    write_json(report_dir/'report.json',report)
    lines=[f"# PaperTrader long-term quality report",'',f"**Status:** {report['status'].upper()} · **suite:** v{VERSION} · **mode:** {args.mode}", '', '## Wallet ledger reconciliation']
    for w in wallets:lines += [f"- **{w['slug']}** — {w['journal_rows']} journal rows, {w['equity_points']} equity points, {w['open_positions']} open positions, reconstructed ledger {'OK' if not w['errors'] else 'FAILED'}"]
    lines += ['',f"Archive: {archive['days']} day files / {archive['archived_runs']} observations / {archive['intelligence_rows']} intelligence rows.",f"Top-10 strategy overlap: {divergence.get('overlap') if divergence.get('overlap') is not None else 'n/a'}.",f"Synthetic stress: {stress['cases']} regimes/cases · eligible {stress['eligible']} · top-20 overlap {stress['top20_overlap']}."]
    if warnings:lines += ['','## Warnings']+[f'- {w}' for w in warnings]
    if errors:lines += ['','## Errors']+[f'- {e}' for e in errors]
    (report_dir/'report.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
