#!/usr/bin/env python3
"""Create a safe standalone editable EEG illustration fixture for UI testing."""
import argparse
import shutil
from pathlib import Path

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--out',type=Path,required=True)
    opt=a.parse_args(); dest=opt.out.resolve()/'project'
    if dest.exists():raise SystemExit('Refusing to overwrite existing demo project: '+str(dest))
    shutil.copytree(Path(__file__).resolve().parent/'demo_project',dest,ignore=shutil.ignore_patterns('__pycache__','.v25_history','exports_v25'))
    print('Example project:',dest)
    print('Start: python scripts/interactive_studio.py --project '+str(dest))

if __name__=='__main__':main()
