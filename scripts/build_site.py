#!/usr/bin/env python3
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1];out=ROOT/"public"
if out.exists():shutil.rmtree(out)
shutil.copytree(ROOT/"site",out);shutil.copytree(ROOT/"data",out/"data");print(out)
