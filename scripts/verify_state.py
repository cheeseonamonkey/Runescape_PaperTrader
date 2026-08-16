#!/usr/bin/env python3
import argparse, json, math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import VERSION, PROFILES
from src.io_utils import DATA, read_json

parser=argparse.ArgumentParser();parser.add_argument('--allow-stale-version',action='store_true');args=parser.parse_args()
doc=read_json(DATA/'latest_snapshot.json',{})
errors=[]
if not doc: errors.append('missing latest_snapshot.json')
if not args.allow_stale_version and doc.get('version')!=VERSION: errors.append(f"snapshot version {doc.get('version')} != {VERSION}")
wallets=doc.get('wallets',{}) if isinstance(doc,dict) else {}
for slug in PROFILES:
    w=wallets.get(slug)
    if not isinstance(w,dict): errors.append(f'missing wallet {slug}');continue
    for key in ('value_gp','cash_gp','return_pct','positions','top_candidates'):
        if key not in w: errors.append(f'{slug} missing {key}')
    if w.get('cash_gp',0)<0 or w.get('value_gp',0)<0: errors.append(f'{slug} negative balance')
    positions=w.get('positions',[])
    ids=[p.get('item_id') for p in positions]
    if len(ids)!=len(set(ids)): errors.append(f'{slug} duplicate inventory ids')
    if len(positions)>w.get('strategy',{}).get('max_positions',10**9): errors.append(f'{slug} over max positions')
market=doc.get('market',{}).get('stats',{}) if isinstance(doc,dict) else {}
if market and market.get('tracked_items',0)<1000: errors.append('market coverage implausibly low')
if errors:
    print('\n'.join('ERROR '+e for e in errors));raise SystemExit(1)
print(f"state ok snapshot=v{doc.get('version')} expected=v{VERSION} wallets={','.join(wallets)} tracked={market.get('tracked_items','?')}")
