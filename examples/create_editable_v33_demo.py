#!/usr/bin/env python3
"""Synthetic editable paths/strokes; no patient or research artwork."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_vector_package import root_svg,build_object,to_xml,render


def create(out):
    out=Path(out).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Demo directory must be empty')
    out.mkdir(parents=True,exist_ok=True)
    specs=[
        ('background','背景','M0 0 H320 V240 H0 Z','#FFFFFF','none',0),
        ('body','主体闭合轮廓','M70 174 C51 142 65 66 125 52 C185 39 213 97 200 151 L175 190 Z','#E7EDF2','#6B8195',2),
        ('contact','独立接触点','M133 107 A14 14 0 1 0 161 107 A14 14 0 1 0 133 107 Z','#C7D9E6','#536E85',2),
        ('wire','独立导线','M148 107 C205 91 238 111 249 158 C254 180 267 187 285 193','none','#405C73',3)]
    objects=[{'id':oid,'name_zh':name,'name_en':oid,'geometry':{'type':'svg_path','d':path},
              'fill':fill,'stroke':stroke,'stroke_width':width} for oid,name,path,fill,stroke,width in specs]
    layers=[{'id':'layer_'+o['id'],'name_zh':o['name_zh'],'objects':[o]} for o in objects]
    root=root_svg(320,240)
    for obj in objects:
        group,_=build_object(obj,out,320,240,0,'polygon');root.append(group)
    render(root,out/'source.png')
    manifest={'schema_version':'1.0','source_image':'source.png','source_sha256':hashlib.sha256((out/'source.png').read_bytes()).hexdigest(),
        'canvas':{'width':320,'height':240},'layers':layers,
        'qa':{'editable_stroke_object_ids':['wire'],'max_geometry_items_per_object':{'wire':1},
              'unresolved_details':['Synthetic illustration only; no anatomical claim.']}}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return out

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    print(create(parser.parse_args().out))
