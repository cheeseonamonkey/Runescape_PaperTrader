#!/usr/bin/env python3
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.intelligence import free_quality_critique
path=Path(sys.argv[1] if len(sys.argv)>1 else 'build/quality/report.json')
report=json.loads(path.read_text())
out=free_quality_critique(report)
Path('build/quality').mkdir(parents=True,exist_ok=True)
Path('build/quality/free-critic.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(json.dumps(out,indent=2))
