#!/usr/bin/env python3
"""Save a local checkpoint selection outside the skill/repository directory."""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from sam2_settings import resolve_model_spec,settings_path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',required=True,type=Path)
    p.add_argument('--config',required=True)
    p.add_argument('--device',choices=('auto','cpu','cuda','mps'),default='auto')
    a=p.parse_args()
    spec=resolve_model_spec(config=a.config,checkpoint=a.checkpoint,device=a.device)
    digest=hashlib.sha256()
    with Path(spec['checkpoint']).open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):digest.update(chunk)
    spec['checkpoint_sha256']=digest.hexdigest()
    target=settings_path();target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=target.parent,delete=False) as f:
        json.dump(spec,f,ensure_ascii=False,indent=2);f.write('\n');temp=f.name
    os.replace(temp,target)
    print('Saved local SAM2 configuration: '+str(target))
    print('Device: '+spec['device']+'; weights remain in their original location.')


if __name__=='__main__':main()
