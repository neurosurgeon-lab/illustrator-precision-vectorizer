#!/usr/bin/env python3
"""Prepare per-object SVGs and a guarded Illustrator ExtendScript import bundle.

This prepares but does not create/verify an AI document. Use locally in desktop
Illustrator. Each object remains a separate named import group and layer.
"""
import argparse
import copy
import json
from pathlib import Path
from build_vector_package import build_object,root_svg,to_xml
from illustrator_native import prepare as prepare_native
from occlusion_layers import resolve_stack

HERE=Path(__file__).resolve().parent

def prepare(project,out,require_exported=True):
    project=Path(project).resolve(strict=True);out=Path(out).resolve()
    manifest=json.loads((project/'manifest.json').read_text('utf8'))
    w,h=int(manifest['canvas']['width']),int(manifest['canvas']['height'])
    ordered,_,_=resolve_stack(manifest)
    byid={o['id']:(layer,o) for layer in manifest['layers'] for o in layer['objects']}
    if not ordered:raise ValueError('No vector objects')
    if out.exists() and any(out.iterdir()):raise ValueError('Illustrator staging output must be empty')
    out.mkdir(parents=True,exist_ok=True)
    items=[]
    combined=root_svg(w,h)
    for i,oid in enumerate(ordered):
        layer,o=byid[oid]
        group,info=build_object(o,project,w,h,0,'polygon')
        combined.append(copy.deepcopy(group))
        doc=root_svg(w,h)
        doc.append(copy.deepcopy(group))
        name=f'object_{i+1:04d}.svg'
        (out/name).write_bytes(to_xml(doc))
        items.append({'id':oid,'name':o.get('name_zh',oid),'layer_name':layer.get('name_zh',layer['id']),
                      'source_layer':layer['id'],'svg':name,'visible_bbox':info['bbox'],
                      'semantic_object_count':1})
    configuration={'version':'3.0','native_ai_created':False,'needs_illustrator_execution':True,
                   'canvas':{'width':w,'height':h},'order':'back_to_front',
                   'object_count':len(items),'objects':items,
                   'limitations':['Illustrator import and saving cannot be verified without desktop Illustrator.',
                       'Imported SVG object may need visual and coordinate inspection.',
                       'SVG filled variable-width outline is not a native Width Tool profile.']}
    (out/'illustrator_import_manifest.json').write_text(json.dumps(configuration,ensure_ascii=False,indent=2),encoding='utf8')
    (out/'Combined_Editable.svg').write_bytes(to_xml(combined))
    prepare_native(out/'Combined_Editable.svg',out/'Native_Editable')
    (out/'import_v30.jsx').write_text("$.evalFile(new File(new File($.fileName).parent.fsName+'/Native_Editable/run_in_illustrator.jsx'));\n",encoding='utf-8')
    (out/'README_IMPORT.txt').write_text('LayerTrace Illustrator editable import package\n\nRun import_v30.jsx using File > Scripts > Other Script in desktop Illustrator.\nThe compatibility entry point calls Native_Editable/run_in_illustrator.jsx.\nIt saves native Color/Linework AI files, reopens them, checks counts and canvas,\nand tests stroke width plus anchor editing when an open stroke is expected.\nRead *_verified.json before claiming success; visual review remains required.\nPreparation alone creates no AI. Existing output files are never overwritten.\n',encoding='utf-8')
    return configuration

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    args=p.parse_args()
    info=prepare(args.project,args.out)
    print(json.dumps({'staging':str(args.out),'native_ai_created':False,'objects':info['object_count']},ensure_ascii=False))

if __name__=='__main__':main()
