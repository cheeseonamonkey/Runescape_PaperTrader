#!/usr/bin/env python3
import argparse, math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import VERSION, PROFILES
from src.io_utils import DATA, read_json

parser=argparse.ArgumentParser();parser.add_argument('--allow-stale-version',action='store_true');args=parser.parse_args()
doc=read_json(DATA/'latest_snapshot.json',{})
errors=[]
strict=not args.allow_stale_version
if not doc: errors.append('missing latest_snapshot.json')
if strict and doc.get('version')!=VERSION: errors.append(f"snapshot version {doc.get('version')} != {VERSION}")
wallets=doc.get('wallets',{}) if isinstance(doc,dict) else {}
for slug in PROFILES:
    w=wallets.get(slug)
    if not isinstance(w,dict): errors.append(f'missing wallet {slug}');continue
    for key in ('value_gp','cash_gp','return_pct','positions','top_candidates'):
        if key not in w: errors.append(f'{slug} missing {key}')
    if w.get('cash_gp',0)<0 or w.get('value_gp',0)<0: errors.append(f'{slug} negative balance')
    positions=w.get('positions',[])
    ids=[p.get('item_id') for p in positions]
    if len(ids)!=len(set(ids)): errors.append(f'{slug} duplicate holdings ids')
    if len(positions)>w.get('strategy',{}).get('max_positions',10**9): errors.append(f'{slug} over max positions')
    if strict:
        for c in w.get('top_candidates',[]):
            parts=c.get('score_components')
            if not isinstance(parts,dict): errors.append(f'{slug} candidate missing score_components');break
            if abs(sum(float(x) for x in parts.values())-float(c.get('score',0)))>.05:
                errors.append(f'{slug} candidate score attribution mismatch');break
            if abs(float(c.get('spread_capture_ev_gp',0))-float(c.get('inventory_risk_ev_gp',0))-float(c.get('expected_edge_gp',0)))>.05:
                errors.append(f'{slug} candidate EV decomposition mismatch');break
market_doc=doc.get('market',{}) if isinstance(doc,dict) else {}
market=market_doc.get('stats',{})
if market and market.get('tracked_items',0)<1000: errors.append('market coverage implausibly low')
if strict:
    econ=market_doc.get('economy')
    if not isinstance(econ,dict): errors.append('missing economy diagnostics')
    else:
        for key in ('breadth','turnover_weighted_price_pressure','active_share','top10_turnover_share','turnover_hhi'):
            val=econ.get(key)
            if not isinstance(val,(int,float)) or not math.isfinite(val): errors.append(f'economy {key} invalid')
        if not -1<=econ.get('breadth',0)<=1: errors.append('economy breadth out of bounds')
        if not 0<=econ.get('active_share',0)<=1: errors.append('economy active_share out of bounds')
        if not 0<=econ.get('top10_turnover_share',0)<=1: errors.append('economy top10 share out of bounds')
        if not 0<=econ.get('turnover_hhi',0)<=1: errors.append('economy HHI out of bounds')
if errors:
    print('\n'.join('ERROR '+e for e in errors));raise SystemExit(1)
print(f"state ok snapshot=v{doc.get('version')} expected=v{VERSION} wallets={','.join(wallets)} tracked={market.get('tracked_items','?')}")
