#!/usr/bin/env python3
"""True SAM2 prompt adapter + conservative illustration postprocessing + project import.

SAM2 model/checkpoint NOT bundled. No actual SAM2 inference occurs in mock
regression tests. Intended only for visible *illustration* structures, not CT/MRI
clinical segmentation, diagnosis or treatment planning.
"""
from __future__ import annotations
import argparse
from contextlib import nullcontext
import hashlib
import json
import re
from pathlib import Path
import numpy as np
import cv2
from PIL import Image,ImageDraw
from medical_mask_postprocess import refine_mask, bbox_mask
from sam2_settings import resolve_model_spec

SAFE=re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_-]*$')

def load_sam2_predictor(hf_model=None, config=None, checkpoint=None, device='auto'):
    """Use upstream Meta SAM2 build_sam2(_hf) APIs; only called for real inference."""
    try:
        import torch
        from sam2.build_sam import build_sam2,build_sam2_hf
        from sam2.sam2_image_predictor import SAM2ImagePredictor
    except ImportError as exc:
        raise RuntimeError('SAM2 not installed. Follow references/sam2-medical-postprocessing.md; no model shipped in ZIP') from exc
    if device=='auto':
        device='cuda' if torch.cuda.is_available() else ('mps' if hasattr(torch.backends,'mps') and torch.backends.mps.is_available() else 'cpu')
    if device not in ('cuda','mps','cpu'):raise ValueError('device must be auto/cuda/mps/cpu')
    if hf_model and (config or checkpoint):raise ValueError('Choose --hf-model OR --config with --checkpoint')
    if hf_model:
        model=build_sam2_hf(hf_model,device=device)
    elif config and checkpoint:
        if not Path(checkpoint).is_file():raise FileNotFoundError(f'Checkpoint not found: {checkpoint}')
        model=build_sam2(config,checkpoint,device=device)
    else:
        raise ValueError('Provide --hf-model or both --config and --checkpoint')
    return SAM2ImagePredictor(model),device

def _load_project(project,annotations,append):
    root=Path(project).resolve(); mp=root/'manifest.json'
    man=json.loads(mp.read_text('utf8'))
    rel=man['source_image'];src=(root/rel).resolve()
    if not src.is_relative_to(root) or not src.is_file():raise ValueError('Source outside project or not found')
    rgba=np.asarray(Image.open(src).convert('RGBA'))
    h,w=rgba.shape[:2]
    if [w,h]!=[int(man['canvas']['width']),int(man['canvas']['height'])]:raise ValueError('Canvas mismatch')
    a=json.loads(Path(annotations).read_text('utf8'))
    instances=a.get('instances',[])
    if not isinstance(instances,list) or not instances:raise ValueError('Need annotation instances')
    if man.get('layers') and not append:raise ValueError('Manifest has layers: use --append to protect existing work')
    ids={o['id'] for layer in man.get('layers',[]) for o in layer.get('objects',[])}
    mods={m['id'] for m in man.get('modules',[])}
    for ob in instances:
        iid=ob.get('id','')
        if not isinstance(iid,str) or not SAFE.fullmatch(iid) or iid in ids:
            raise ValueError(f'Unsafe or duplicate instance ID: {iid}')
        ids.add(iid)
        if 'module_'+iid in mods:raise ValueError(f'Duplicate module ID: {iid}')
        lid=ob.get('layer_id','01_sam2_instances')
        if not isinstance(lid,str) or not SAFE.fullmatch(lid):raise ValueError(f'Invalid layer ID {lid}')
        if not ob.get('fg_points') and not ob.get('bbox'):raise ValueError(f'{iid}: needs points or box')
        # Pre-validate annotations to avoid partial output from invalid prompts.
        bbox_mask(ob.get('bbox'),w,h)
        for key in ('fg_points','bg_points'):
            for p in ob.get(key,[]):
                if len(p)!=2 or not 0<=float(p[0])<w or not 0<=float(p[1])<h:
                    raise ValueError(f'{iid}: bad {key}')
    return root,mp,man,src,rgba,a,instances

def _prompts(ob):
    points=ob.get('fg_points',[])+ob.get('bg_points',[])
    coords=np.asarray(points,dtype=np.float32).reshape(-1,2) if points else None
    labels=np.asarray([1]*len(ob.get('fg_points',[]))+[0]*len(ob.get('bg_points',[])),dtype=np.int32) if points else None
    b=ob.get('bbox')
    box=np.asarray([b[0],b[1],b[0]+b[2],b[1]+b[3]],dtype=np.float32) if b else None
    return coords,labels,box

def select_prediction(rgba,ob,masks,scores,min_score=.0):
    masks=np.asarray(masks)
    if masks.ndim==2:masks=masks[np.newaxis,:,:]
    scores=np.asarray(scores).reshape(-1)
    if masks.ndim!=3 or len(masks)!=len(scores):raise ValueError('SAM2 predictor output dimensions mismatch')
    candidates=[];reject=[]
    for j,(mask,score) in enumerate(zip(masks,scores)):
        if not np.isfinite(score) or float(score)<min_score:
            reject.append({'candidate':j,'reason':'predicted IoU below min_score'});continue
        try:
            cleaned,qa=refine_mask(mask,rgba,ob)
        except ValueError as exc:
            reject.append({'candidate':j,'reason':str(exc)});continue
        # Primary ranking follows *model predicted score*, not ground-truth Dice.
        candidates.append((float(score),j,cleaned,qa))
    if not candidates:
        raise ValueError(f"{ob['id']}: no SAM2 candidate satisfied prompts/postprocess: {reject}")
    score,j,mask,qa=max(candidates,key=lambda a:(a[0],-a[1]))
    qa.update({'sam_predicted_iou':round(score,6),'chosen_candidate':int(j),
               'rejected_candidates':reject,
               'ground_truth_iou':None,'medical_anatomy_verified':False})
    return mask,qa

def _sample_color(rgba,mask):
    rgb=np.median(rgba[:,:,:3][mask],axis=0).round().astype(np.uint8)
    return '#'+''.join(f'{int(v):02X}' for v in rgb)

def _preview(rgba,mask,ob):
    base=Image.fromarray(rgba[:,:,:3].copy(),'RGB').convert('RGBA')
    overlay=np.zeros_like(rgba);overlay[mask]=[0,195,110,100]
    base=Image.alpha_composite(base,Image.fromarray(overlay,'RGBA'))
    a=np.array(base.convert('RGB'));contours,_=cv2.findContours(mask.astype(np.uint8),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(a,contours,-1,(15,115,50),2)
    preview=Image.fromarray(a);d=ImageDraw.Draw(preview)
    b=ob.get('bbox')
    if b:d.rectangle([b[0],b[1],b[0]+b[2]-1,b[1]+b[3]-1],outline=(238,151,50),width=1)
    for x,y in ob.get('fg_points',[]):
        d.ellipse((x-4,y-4,x+4,y+4),fill=(45,185,65),outline='white',width=1)
    for x,y in ob.get('bg_points',[]):
        d.line([(x-4,y-4),(x+4,y+4)],fill='red',width=2)
        d.line([(x+4,y-4),(x-4,y+4)],fill='red',width=2)
    return preview

def run(project,annotations,predictor=None,append=False,hf_model=None,config=None,checkpoint=None,device='auto',min_score=.4):
    """Inject predictor only for explicitly labelled mock regression tests."""
    root,mp,man,src,rgba,ann,instances=_load_project(project,annotations,append)
    if not 0<=min_score<=1:raise ValueError('min_score outside [0,1]')
    dev='external_test_predictor' if predictor is not None else None
    if predictor is None:
        predictor,dev=load_sam2_predictor(hf_model,config,checkpoint,device)
    # Load image only once. Inference_mode avoids allocating gradient buffers.
    import importlib.util
    import_context=nullcontext()
    if dev!='external_test_predictor':
        import torch
        import_context=torch.inference_mode()
    with import_context:
        predictor.set_image(np.array(rgba[:,:,:3],copy=True))
        masks_out=[];entries=[];previews=[]
        for ob in instances:
            coords,labels,box=_prompts(ob)
            masks,scores,_=predictor.predict(point_coords=coords,point_labels=labels,box=box,
                                               multimask_output=True,normalize_coords=True)
            mask,qa=select_prediction(rgba,ob,masks,scores,min_score)
            qa['id']=ob['id'];qa['sampled_fill']=_sample_color(rgba,mask)
            masks_out.append(mask);entries.append(qa);previews.append(_preview(rgba,mask,ob))
    # Check all overlaps before any writes. SAM2 masks represent visible layers;
    # overlapping pixels would otherwise create false composite and misleading QA.
    conflicts=[]
    for i in range(len(masks_out)):
        for j in range(i+1,len(masks_out)):
            overlap=int(np.sum(masks_out[i]&masks_out[j]))
            if overlap:conflicts.append({'a':instances[i]['id'],'b':instances[j]['id'],'pixels':overlap})
    if conflicts and not ann.get('allow_visible_overlap',False):
        raise ValueError(f'SAM2 predicted overlapping visible instances; revise annotations: {conflicts}')
    maskdir=root/'masks';previewdir=root/'sam2_previews'
    # Unused IDs were checked before inference; don't overwrite any existing files.
    for ob in instances:
        if (maskdir/(ob['id']+'.png')).exists() or (previewdir/(ob['id']+'.png')).exists():
            raise ValueError(f"Output mask/preview already exists for {ob['id']}")
    layers={layer['id']:layer for layer in man.get('layers',[])}
    for ob,qa in zip(instances,entries):
        lid=ob.get('layer_id','01_sam2_instances')
        if lid not in layers:
            layers[lid]={'id':lid,'name_zh':ob.get('layer_name_zh','SAM2 辅助实例'),
                         'name_en':ob.get('layer_name_en','SAM2 guided instances'),'objects':[]}
        layers[lid]['objects'].append({'id':ob['id'],'name_zh':ob.get('name_zh',ob['id']),
           'name_en':ob.get('name_en',ob['id']),
           'geometry':{'type':'mask_png','file':'masks/'+ob['id']+'.png'},
           'fill':ob.get('fill',qa['sampled_fill']),'stroke':'none',
           'notes':'SAM2 visual segmentation + conservative refinement; requires visual anatomical review'})
        man.setdefault('modules',[]).append({'id':'module_'+ob['id'],
                'name_zh':ob.get('name_zh',ob['id']),'object_ids':[ob['id']]})
    man['layers']=list(layers.values())
    man.setdefault('qa',{}).setdefault('unresolved_details',[]).append(
        'SAM2 模型估计分数不是原图真值 IoU；神经、导线交叉、局部遮挡、形状及编辑图层须人工逐项复核。')
    report={'method':'sam2_image_predictor','actual_sam2_inference':dev!='external_test_predictor',
            'model_source':hf_model or checkpoint or 'external_test_predictor',
            'device':dev,'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),
            'instance_count':len(entries),'instances':entries,'overlap_pairs':conflicts,
            'medical_semantics_inferred':False,'all_instances_review_required':True}
    maskdir.mkdir(exist_ok=True);previewdir.mkdir(exist_ok=True)
    for ob,mask,pv in zip(instances,masks_out,previews):
        Image.fromarray(mask.astype(np.uint8)*255).save(maskdir/(ob['id']+'.png'))
        pv.save(previewdir/(ob['id']+'.png'))
    mp.write_text(json.dumps(man,indent=2,ensure_ascii=False),encoding='utf8')
    (root/'sam2_annotations.json').write_text(json.dumps(ann,indent=2,ensure_ascii=False),encoding='utf8')
    (root/'sam2_segmentation_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    return report

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project',type=Path,required=True)
    ap.add_argument('--annotations',type=Path,required=True)
    src=ap.add_mutually_exclusive_group()
    src.add_argument('--hf-model',help='Hugging Face SAM2/SAM2.1 repository (may download weights)')
    src.add_argument('--checkpoint',type=Path,help='Local Meta SAM2.1 checkpoint')
    ap.add_argument('--config',help='Required with --checkpoint: configs/sam2.1/sam2.1_hiera_t.yaml etc')
    ap.add_argument('--device',default=None,choices=['auto','cpu','mps','cuda'])
    ap.add_argument('--min-score',type=float,default=.4,help='SAM2 predicted IoU minimum, NOT ground truth')
    ap.add_argument('--append',action='store_true')
    a=ap.parse_args()
    try:spec=resolve_model_spec(a.hf_model,a.config,a.checkpoint,a.device)
    except (ValueError,OSError) as exc:ap.error(str(exc))
    if not (spec['hf_model'] or spec['checkpoint']):ap.error('Configure a local model or supply --hf-model / --checkpoint with --config')
    r=run(a.project,a.annotations,append=a.append,min_score=a.min_score,**spec)
    print(json.dumps({'instances':r['instance_count'],'device':r['device'],
          'actual_sam2_inference':r['actual_sam2_inference'],'needs_human_review':True},ensure_ascii=False))
if __name__=='__main__':main()
