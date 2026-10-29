"""Per-user local model selection. No weights or machine paths belong in Git."""
import json
import os
from pathlib import Path


def settings_path():
    if os.environ.get('LAYERTRACE_CONFIG_HOME'):
        return Path(os.environ['LAYERTRACE_CONFIG_HOME']).expanduser()/'sam2.json'
    legacy=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'skill-config/illustrator-precision-vectorizer/sam2.json'
    if legacy.is_file():return legacy
    return Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config'))).expanduser()/'layertrace/sam2.json'


def resolve_model_spec(hf_model=None,config=None,checkpoint=None,device=None):
    explicit=any(v is not None for v in (hf_model,config,checkpoint))
    saved={}
    if not explicit and settings_path().is_file():
        saved=json.loads(settings_path().read_text('utf-8'))
        if not isinstance(saved,dict):raise ValueError('Local SAM2 settings must be a JSON object')
    spec={'hf_model':hf_model if explicit else saved.get('hf_model'),
          'config':config if explicit else saved.get('config'),
          'checkpoint':str(checkpoint) if checkpoint is not None else (None if explicit else saved.get('checkpoint')),
          'device':device or (None if explicit else saved.get('device')) or 'auto'}
    if spec['device'] not in ('auto','cpu','cuda','mps'):raise ValueError('Invalid SAM2 device')
    if spec['hf_model'] and (spec['config'] or spec['checkpoint']):raise ValueError('Choose a Hugging Face model OR local config/checkpoint')
    if bool(spec['config'])!=bool(spec['checkpoint']):raise ValueError('Local SAM2 requires both config and checkpoint')
    for key in ('hf_model','config','checkpoint'):
        if spec[key] is not None and not isinstance(spec[key],str):raise ValueError('Invalid SAM2 '+key)
    if spec['checkpoint']:
        p=Path(spec['checkpoint']).expanduser().resolve()
        if not p.is_file():raise FileNotFoundError('SAM2 checkpoint not found: '+str(p))
        spec['checkpoint']=str(p)
    return spec
