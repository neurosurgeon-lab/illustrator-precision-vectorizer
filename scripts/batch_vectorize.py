#!/usr/bin/env python3
"""Sequential folder processing with separate outputs and per-item failure reports.

Raster images require per-image instance annotations. Missing annotations produce
an initialized project marked needs_annotations, never a fake completed vector.
"""
import argparse
from collections import Counter
import csv
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
IMAGE_SUFFIXES={'.png','.jpg','.jpeg','.tif','.tiff','.webp','.bmp','.svg'}


def run_step(script,args,log):
    command=[sys.executable,str(HERE/script),*map(str,args)]
    with log.open('a',encoding='utf-8') as f:
        result=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT)
    if result.returncode:
        tail=log.read_text('utf-8',errors='replace')[-1800:]
        raise RuntimeError(f'{script} exited {result.returncode}: {tail}')


def discover(source,projects=False,mixed=False,recursive=False):
    inputs=[]
    for folder,dirs,files in os.walk(source,followlinks=False):
        current=Path(folder)
        dirs[:]=sorted(d for d in dirs if not (current/d).is_symlink())
        if 'manifest.json' in files:
            if projects or mixed:inputs.append(current)
            dirs[:]=[]  # Project masks, sources and old exports are not new inputs.
            continue
        if not projects:
            inputs.extend(current/f for f in sorted(files) if Path(f).suffix.lower() in IMAGE_SUFFIXES)
        if not recursive:
            if projects or mixed:
                inputs.extend(current/d for d in dirs if (current/d/'manifest.json').is_file())
            dirs[:]=[]
    for item in inputs:
        if not item.resolve().is_relative_to(source):raise ValueError('Input symlink escapes source directory')
    return sorted(inputs)


def process_batch(source,out,*,projects=False,mixed=False,recursive=False,annotations=None,checkpoint=None,config=None,device=None,allow_draft=False,
                  ocr=False,ocr_language='eng',completion_annotations=None):
    source=Path(source).expanduser().resolve(strict=True)
    out=Path(out).expanduser().resolve()
    if not source.is_dir():raise ValueError('Input must be a directory')
    if out==source or out.is_relative_to(source):raise ValueError('Output must be outside the input directory')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):raise ValueError('Output directory must be empty')
    if annotations is not None:
        annotations=Path(annotations).expanduser().resolve(strict=True)
        if not annotations.is_dir():raise ValueError('Annotations must be a directory')
    if completion_annotations is not None:
        completion_annotations=Path(completion_annotations).expanduser().resolve(strict=True)
        if not completion_annotations.is_dir():raise ValueError('Completion annotations must be a directory')
    inputs=discover(source,projects=projects,mixed=mixed,recursive=recursive)
    if not inputs:raise ValueError('No supported projects/images found')
    out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for item in inputs:
        relative=item.relative_to(source) if item!=source else Path(item.name)
        dest=out/relative
        is_project=item.is_dir()
        row={'input':str(item),'output':str(dest),'status':'failed','stage':'initialize','error':'','sam2_executed':False,'quality_gates_passed':False,'ocr':'not_requested','ocr_error':''}
        start=time.monotonic()
        try:
            dest.mkdir(parents=True)
            log=dest/'process.log'
            if is_project:
                project=item
                if ocr or completion_annotations:
                    # Keep source projects read-only when optional stages need review files.
                    for entry in item.rglob('*'):
                        if entry.is_symlink() and not entry.resolve().is_relative_to(item.resolve()):
                            raise ValueError('Project symlink escapes project')
                    project=dest/'project'
                    shutil.copytree(item,project)
            else:
                project=dest/'project'
                run_step('init_project.py',['--image',item,'--out',project],log)
                manifest=json.loads((project/'manifest.json').read_text('utf-8'))
                if not manifest.get('layers'):
                    annotation=(annotations or source)/Path(str(relative)+'.annotations.json')
                    if not annotation.is_file():
                        row.update(status='needs_annotations',stage='annotations',error='Missing per-image annotations: '+str(annotation))
                    else:
                        row['stage']='sam2'
                        row['sam2_executed']=None
                        command=['--project',project,'--annotations',annotation]
                        for flag,value in [('--checkpoint',checkpoint),('--config',config),('--device',device)]:
                            if value is not None:command.extend([flag,value])
                        # ponytail: reload per image to isolate memory; reuse a predictor if startup dominates.
                        run_step('sam2_medical_segment.py',command,log)
                        segmentation=json.loads((project/'sam2_segmentation_report.json').read_text('utf-8'))
                        row['sam2_executed']=segmentation['actual_sam2_inference']
                        spec=json.loads(annotation.read_text('utf-8'))
                        if spec.get('background') is not None:
                            from build_vector_package import color
                            fill=color(spec['background'])
                            manifest=json.loads((project/'manifest.json').read_text('utf-8'))
                            reserved={'batch_background','batch_background_layer','batch_background_module'}
                            ids={o['id'] for l in manifest['layers'] for o in l['objects']}|{l['id'] for l in manifest['layers']}|{m['id'] for m in manifest.get('modules',[])}
                            if ids&reserved:raise ValueError('Annotations use reserved batch background IDs')
                            w,h=manifest['canvas']['width'],manifest['canvas']['height']
                            manifest['layers'].insert(0,{'id':'batch_background_layer','name_zh':'已确认背景','name_en':'Confirmed background','objects':[
                                {'id':'batch_background','name_zh':'背景','name_en':'Background','geometry':{'type':'svg_path','d':f'M 0 0 H {w} V {h} H 0 Z'},'fill':fill,'stroke':'none'}]})
                            manifest.setdefault('modules',[]).insert(0,{'id':'batch_background_module','name_zh':'背景','layer_ids':['batch_background_layer']})
                            (project/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
            if completion_annotations is not None:
                annotation=completion_annotations/Path(str(relative)+'.completion.json')
                if annotation.is_file():shutil.copyfile(annotation,project/'completion_annotations.json')
            if ocr:
                row['stage']='ocr'
                if (project/'text_review.json').exists():
                    row['ocr']='existing_review_preserved'
                else:
                    try:
                        run_step('text_recognition.py',['--project',project,'--languages',ocr_language],log)
                        row['ocr']='review_required'
                    except Exception as exc:
                        row['ocr']='failed';row['ocr_error']=str(exc)
            if row['status']=='needs_annotations':continue
            row['stage']='export'
            command=['--project',project,'--out',dest/'export']
            if allow_draft:command.append('--allow-draft')
            run_step('build_vector_package.py',command,log)
            quality=json.loads((dest/'export/quality_report.json').read_text('utf-8'))
            row['quality_gates_passed']=quality['quality_gates_passed']
            row['status']='success' if quality['quality_gates_passed'] else 'draft'
            row['stage']='complete'
        except Exception as exc:
            row['error']=str(exc)
        finally:
            row['seconds']=round(time.monotonic()-start,3);rows.append(row)
            summary={'input':str(source),'mode':'mixed' if mixed else ('projects' if projects else 'images'),'counts':dict(Counter(r['status'] for r in rows)),'items':rows}
            # Persist after each item so completed results survive interruption.
            (out/'batch_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
            with (out/'batch_summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=list(row));writer.writeheader();writer.writerows(rows)
            print(f"{len(rows)}/{len(inputs)} {item.name}: {row['status']}",flush=True)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--images',type=Path,help='Directory of raster images or simple SVGs')
    mode.add_argument('--projects',type=Path,help='Directory containing project folders')
    mode.add_argument('--input-dir',type=Path,help='Mixed images and existing projects')
    p.add_argument('--recursive',action='store_true')
    p.add_argument('--ocr',action='store_true')
    p.add_argument('--ocr-language',default='eng')
    p.add_argument('--completion-annotations-dir',type=Path,help='Mirrored relative paths with .completion.json suffix')
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--annotations','--annotations-dir',type=Path,help='image.png uses image.png.annotations.json; defaults to image directory')
    p.add_argument('--checkpoint',type=Path)
    p.add_argument('--config')
    p.add_argument('--device',choices=('auto','cpu','cuda','mps'))
    p.add_argument('--allow-draft',action='store_true')
    a=p.parse_args()
    if a.projects is not None and any(v is not None for v in (a.annotations,a.checkpoint,a.config,a.device)):
        p.error('Annotation/model options apply only to --images')
    try:
        result=process_batch(a.projects or a.images or a.input_dir,a.out,projects=a.projects is not None,annotations=a.annotations,
                             checkpoint=a.checkpoint,config=a.config,device=a.device,allow_draft=a.allow_draft,mixed=a.input_dir is not None,recursive=a.recursive,
                             ocr=a.ocr,ocr_language=a.ocr_language,completion_annotations=a.completion_annotations_dir)
    except (ValueError,OSError) as exc:p.error(str(exc))
    print(json.dumps(result['counts'],ensure_ascii=False))
    if any(r['status'] in ('failed','needs_annotations') for r in result['items']):raise SystemExit(1)


if __name__=='__main__':main()
