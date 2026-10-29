#!/usr/bin/env python3
"""Prompt-guided *instance* masks for medical illustrations, not automatic diagnosis.

Provides two local methods: LAB seed-connected components (flat colors) and
GrabCut with required foreground marks/bbox (complex bounded objects). Labels
and anatomy come ONLY from user-reviewed annotations. Shared colors, occlusion,
branch crossings, transparent edges and anti-aliasing still need manual QA.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

SAFE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_-]*$')

def check_point(p, w, h, iid):
    if len(p)!=2 or not all(isinstance(x,(int,float)) for x in p):
        raise ValueError(f'{iid}: point requires [x,y]')
    x,y = map(int,p)
    if not (0<=x<w and 0<=y<h): raise ValueError(f'{iid}: point outside canvas')
    return x,y

def box_of(a,w,h,iid):
    if a is None: return (0,0,w,h)
    if len(a)!=4 or not all(isinstance(z,int) for z in a): raise ValueError(f'{iid}: bbox must be integer [x,y,w,h]')
    x,y,bw,bh=a
    if bw<=0 or bh<=0 or x<0 or y<0 or x+bw>w or y+bh>h: raise ValueError(f'{iid}: invalid bbox')
    return x,y,bw,bh

def roi_mask(box, w, h):
    x,y,bw,bh=box
    out=np.zeros((h,w),dtype=bool); out[y:y+bh,x:x+bw]=True
    return out

def paint_points(arr, pts, color, radius, w,h,iid):
    for p in pts:
        x,y=check_point(p,w,h,iid)
        cv2.circle(arr,(x,y),int(radius),int(color),-1,lineType=cv2.LINE_8)

def seed_connected(rgba, instance, allow):
    h,w=rgba.shape[:2]; iid=instance['id']
    fg=instance.get('fg_points',[])
    if not fg:raise ValueError(f'{iid}: provide fg_points')
    for p in fg:check_point(p,w,h,iid)
    tol=float(instance.get('lab_tolerance',13))
    if not 0<=tol<=85:raise ValueError(f'{iid}: lab_tolerance must be 0..85')
    lab=cv2.cvtColor(rgba[:,:,:3],cv2.COLOR_RGB2LAB).astype(np.float32)
    refs=np.array([lab[int(y),int(x)] for x,y in fg])
    # Multiple foreground marks must belong to the SAME designed material;
    # clicking an overlaid red electrode while tracing a teal nerve would
    # otherwise silently contaminate the nerve mask with entire red regions.
    if len(refs)>1 and not instance.get('allow_multicolor',False):
        max_separation=float(np.max(np.linalg.norm(refs[:,None,:]-refs[None,:,:],axis=-1)))
        if max_separation>max(3.0,2*tol):
            raise ValueError(f'{iid}: inconsistent foreground seed colors (LAB distance {max_separation:.1f}); '
                             'move seed marks away from overlap/antialiasing or explicitly allow_multicolor')
    # Union, not average; preserves genuinely varying colors when explicitly allowed.
    mindist=np.full(lab.shape[:2],np.inf,dtype=np.float32)
    for ref in refs:
        delta=lab-ref
        dist=np.sqrt(np.sum(delta*delta,axis=-1))
        np.minimum(mindist,dist,out=mindist)
    candidate=(mindist<=tol)&allow
    # Every foreground seed is included independently, then merged into ONE
    # instance mask. Prevents same-color disconnected structures merging.
    n,labels,stats,_=cv2.connectedComponentsWithStats(candidate.astype(np.uint8),8)
    valid=set()
    for x,y in fg:
        if not candidate[int(y),int(x)]:raise ValueError(f'{iid}: foreground seed fails color match / bbox / alpha')
        valid.add(int(labels[int(y),int(x)]))
    valid.discard(0)
    result=np.isin(labels,list(valid)) & candidate
    if not result.any():raise ValueError(f'{iid}: no component at seeds')
    return result

def grabcut_mask(rgba,instance,allowed,box):
    h,w=rgba.shape[:2];iid=instance['id']
    fg=instance.get('fg_points',[])
    bg=instance.get('bg_points',[])
    if not fg:raise ValueError(f'{iid}: GrabCut requires at least one foreground point')
    x,y,bw,bh=box
    if bw==w and bh==h and not bg:
        raise ValueError(f'{iid}: GrabCut on full-frame bbox requires background points')
    # The entirety of bbox begins probable background. Inner region is probable foreground
    # only where supported by color similarity; this reduces bleed for thin nerves.
    mask=np.full((h,w),cv2.GC_BGD,dtype=np.uint8)
    mask[allowed]=cv2.GC_PR_BGD
    lab=cv2.cvtColor(rgba[:,:,:3],cv2.COLOR_RGB2LAB).astype(np.float32)
    for pt in fg: check_point(pt,w,h,iid)
    colors=np.array([lab[int(y0),int(x0)] for x0,y0 in fg])
    if len(colors)>1 and not instance.get('allow_multicolor',False):
        max_separation=float(np.max(np.linalg.norm(colors[:,None,:]-colors[None,:,:],axis=-1)))
        if max_separation>max(10.0,2*float(instance.get('lab_tolerance',28))):
            raise ValueError(f'{iid}: GrabCut foreground seed colors inconsistent; inspect ROI overlaps')
    mindist=np.full(lab.shape[:2],np.inf,dtype=np.float32)
    for ref in colors:
        delta=lab-ref
        dist=np.sqrt(np.sum(delta*delta,axis=-1))
        np.minimum(mindist,dist,out=mindist)
    tol=float(instance.get('lab_tolerance',28))
    mask[allowed&(mindist<=tol)] = cv2.GC_PR_FGD
    radius=int(instance.get('brush_radius',2))
    if not 0<=radius<=30: raise ValueError(f'{iid}: brush_radius must be 0..30')
    paint_points(mask,fg,cv2.GC_FGD,radius,w,h,iid)
    paint_points(mask,bg,cv2.GC_BGD,radius,w,h,iid)
    mask[~allowed]=cv2.GC_BGD
    for pt in fg:
        x0,y0=check_point(pt,w,h,iid)
        if mask[y0,x0]!=cv2.GC_FGD:raise ValueError(f'{iid}: foreground point overlaps background or outside bbox')
    it=int(instance.get('iterations',5))
    if not 1<=it<=15:raise ValueError(f'{iid}: iterations must be 1..15')
    img=cv2.cvtColor(rgba[:,:,:3],cv2.COLOR_RGB2BGR)
    bgmodel=np.zeros((1,65),np.float64);fgmodel=np.zeros((1,65),np.float64)
    try:
        cv2.grabCut(img,mask,None,bgmodel,fgmodel,it,cv2.GC_INIT_WITH_MASK)
    except cv2.error as exc:
        raise ValueError(f'{iid}: GrabCut failed (add distinct foreground and background scribbles): {exc}') from exc
    result=np.isin(mask,[cv2.GC_FGD,cv2.GC_PR_FGD])&allowed
    # Keep only connected components covering foreground marks (not remote matching areas).
    n,labels,_,_=cv2.connectedComponentsWithStats(result.astype(np.uint8),8)
    valid={int(labels[int(y0),int(x0)]) for x0,y0 in fg if labels[int(y0),int(x0)]>0}
    result=np.isin(labels,list(valid))&result
    if not result.any():raise ValueError(f'{iid}: no foreground retained')
    return result

def segment_one(rgba, instance):
    h,w=rgba.shape[:2];iid=instance['id']
    method=instance.get('method','seed_lab')
    box=box_of(instance.get('bbox'),w,h,iid)
    allowed=roi_mask(box,w,h) & (rgba[:,:,3]>=int(instance.get('min_alpha',128)))
    # User background scribbles can also veto a seed-LAB region.
    if method=='seed_lab':
        mask=seed_connected(rgba,instance,allowed)
        bg=instance.get('bg_points',[])
        if bg:
            veto=np.zeros((h,w),np.uint8)
            paint_points(veto,bg,255,int(instance.get('brush_radius',2)),w,h,iid)
            mask &= ~veto.astype(bool)
    elif method=='grabcut':mask=grabcut_mask(rgba,instance,allowed,box)
    else:raise ValueError(f'{iid}: method must be seed_lab or grabcut')
    pix=int(mask.sum())
    if pix<max(1,int(instance.get('min_pixels',1))):raise ValueError(f'{iid}: too few pixels in mask ({pix})')
    if pix>float(instance.get('max_area_fraction',.65))*w*h:
        raise ValueError(f'{iid}: mask covers {pix/(w*h):.1%} of whole canvas; likely background')
    num,cc,stats,_=cv2.connectedComponentsWithStats(mask.astype(np.uint8),8)
    x,y,bw,bh=box
    edge=np.zeros(mask.shape,bool)
    edge[y:y+bh,x]=True; edge[y:y+bh,x+bw-1]=True
    edge[y,x:x+bw]=True; edge[y+bh-1,x:x+bw]=True
    rgb=rgba[:,:,:3][mask]
    med=np.median(rgb,axis=0).round().astype(np.uint8)
    color='#'+''.join(f'{int(v):02X}' for v in med)
    ys,xs=np.where(mask)
    return mask,{'id':iid,'method':method,'pixel_count':pix,'component_count':int(num-1),
        'bbox_visible':[int(xs.min()),int(ys.min()),int(xs.max()-xs.min()+1),int(ys.max()-ys.min()+1)],
        'roi_boundary_pixel_count':int((mask&edge).sum()),'sampled_fill':color,
        'review_required':bool((mask&edge).any() or num>2),
        'caution':'Guided visual instance only; not an automatically recognized medical anatomy'}

def process(project,annotations,append=False):
    root=Path(project).resolve();manpath=root/'manifest.json'
    man=json.loads(manpath.read_text('utf-8'))
    src=(root/man['source_image']).resolve()
    if not src.is_relative_to(root) or not src.is_file():raise ValueError('Unsafe source image')
    rgba=np.asarray(Image.open(src).convert('RGBA'))
    h,w=rgba.shape[:2]
    if [w,h]!=[int(man['canvas']['width']),int(man['canvas']['height'])]:raise ValueError('Canvas mismatch')
    annotations=json.loads(Path(annotations).read_text('utf-8'))
    instances=annotations.get('instances',[])
    if not instances:raise ValueError('No instances in annotation file')
    if man.get('layers') and not append:raise ValueError('Manifest already has layers; use --append after inspection')
    ids={o['id'] for l in man.get('layers',[]) for o in l.get('objects',[])}
    newmasks=[]; entries=[]
    for ob in instances:
        iid=ob['id']
        if not SAFE.fullmatch(iid) or iid in ids:raise ValueError(f'Unsafe/duplicate ID: {iid}')
        ids.add(iid)
        mask,record=segment_one(rgba,ob)
        newmasks.append(mask); entries.append(record)
    overlap=[]
    for i in range(len(newmasks)):
        for j in range(i+1,len(newmasks)):
            n=int((newmasks[i]&newmasks[j]).sum())
            if n:
                overlap.append({'a':entries[i]['id'],'b':entries[j]['id'],'overlap_pixels':n})
                entries[i]['review_required']=True;entries[j]['review_required']=True
    # Do not write partial project on segmentation error, IDs errors etc.
    # Reject ID collisions before writing any masks or replacing user files.
    old_modules={m['id'] for m in man.get('modules',[])}
    for ob in instances:
        if 'module_'+ob['id'] in old_modules:
            raise ValueError(f"Module ID collision: module_{ob['id']}")
        lid=ob.get('layer_id','01_guided_instances')
        if not SAFE.fullmatch(lid):raise ValueError(f'Invalid layer ID: {lid}')
    masksdir=root/'masks';masksdir.mkdir(exist_ok=True)
    layers={x['id']:x for x in man.get('layers',[])}
    for ob,mask,record in zip(instances,newmasks,entries):
        iid=ob['id'];Image.fromarray(mask.astype(np.uint8)*255).save(masksdir/f'{iid}.png')
        lid=ob.get('layer_id','01_guided_instances')
        if not SAFE.fullmatch(lid):raise ValueError('Invalid layer id')
        if lid not in layers:
            layers[lid]={'id':lid,'name_zh':ob.get('layer_name_zh','辅助实例填色'),'name_en':ob.get('layer_name_en','Guided instances'),'objects':[]}
        layers[lid]['objects'].append({'id':iid,'name_zh':ob.get('name_zh',iid),'name_en':ob.get('name_en',iid),
            'geometry':{'type':'mask_png','file':f'masks/{iid}.png'},'fill':ob.get('fill',record['sampled_fill']),
            'stroke':'none','notes':'Assisted mask; anatomy label provided externally; verify contours/overlaps'})
    man['layers']=list(layers.values())
    # Modules reference newly created IDs to prevent accidentally changing existing modules.
    man.setdefault('modules',[])
    for ob in instances:
        man['modules'].append({'id':'module_'+ob['id'],'name_zh':ob.get('name_zh',ob['id']),'object_ids':[ob['id']]})
    pending=[e['id'] for e in entries if e['review_required']]
    man.setdefault('qa',{}).setdefault('unresolved_details',[]).append(
        '实例分割仅由人工种子/ROI/标注辅助产生；语义分类、遮挡关系及可见边界仍需逐个检查。'+(' 重点检查: '+','.join(pending) if pending else ''))
    manpath.write_text(json.dumps(man,ensure_ascii=False,indent=2),encoding='utf-8')
    (root/'instance_annotations.json').write_text(json.dumps(annotations,ensure_ascii=False,indent=2),encoding='utf-8')
    report={'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'algorithm':'guided_seed_lab_or_grabcut',
        'medical_semantics_inferred':False,'instance_count':len(entries),'instances':entries,'overlap_pairs':overlap,
        'all_instances_review_required':True,'notes':['ROI 边界接触可能代表结构被裁断','实例重叠可能是遮挡或误分割','人工验收前不得宣称 1:1']}
    (root/'instance_segmentation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',required=True,type=Path)
    p.add_argument('--annotations',required=True,type=Path)
    p.add_argument('--append',action='store_true')
    a=p.parse_args()
    result=process(a.project,a.annotations,append=a.append)
    print(json.dumps({'instances':result['instance_count'],'overlaps':len(result['overlap_pairs']),
                      'review_required':True},ensure_ascii=False))

if __name__=='__main__':main()
