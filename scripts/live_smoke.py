#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.market import snapshot, timeseries
from src.strategy import common_features
from src.research import _rss_headlines

latest,five,hourly,mapping=snapshot()
assert len(latest)>2500, f'latest coverage low: {len(latest)}'
assert len(mapping)>2500, f'mapping coverage low: {len(mapping)}'
common=common_features(latest,five,hourly,mapping)
assert len(common)>1000, f'feature coverage low: {len(common)}'
head=common[0]
series=timeseries(head['id'],'1h')
assert len(series)>=4, 'timeseries too short'
rss=_rss_headlines(3)
assert rss and not all(x.get('error') for x in rss), 'Jagex RSS unavailable'
print(f"live smoke ok latest={len(latest)} common={len(common)} timeseries={len(series)} rss={len(rss)}")
