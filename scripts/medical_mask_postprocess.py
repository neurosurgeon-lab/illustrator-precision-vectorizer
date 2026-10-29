#!/usr/bin/env python3
"""Conservative, auditable refinement for *illustration* instances.

Never infer hidden anatomy; never bridge discontinuities by default. Pixel-level
postprocessing is NOT a medical image segmentation algorithm or clinical tool.
"""
from __future__ import annotations
import cv2
import numpy as np
from skimage.morphology import skeletonize

PROFILES = {'generic','nerve','lead','electrode','device','body'}

def _point(p, w, h, label):
    if not isinstance(p,(list,tuple)) or len(p)!=2 or not all(isinstance(n,(int,float)) for n in p):
        raise ValueError(f'{label}: point must be [x,y]')
    x,y=map(int,p)
    if not (0<=x<w and 0<=y<h): raise ValueError(f'{label}: point out of bounds')
    return x,y

def bbox_mask(bbox,w,h):
    b=np.ones((h,w),dtype=bool)
    if bbox is None:return b
    if len(bbox)!=4 or not all(isinstance(v,int) for v in bbox):raise ValueError('bbox must be [x,y,width,height] integers')
    x,y,bw,bh=bbox
    if x<0 or y<0 or bw<=0 or bh<=0 or x+bw>w or y+bh>h:raise ValueError('Invalid bbox')
    b[:]=False;b[y:y+bh,x:x+bw]=True
    return b

def _components(a):
    n,lb,stats,centroids=cv2.connectedComponentsWithStats(a.astype(np.uint8),8)
    return n,lb,stats

def _color_refine(base, rgba, fg, allow, radius, tolerance):
    if radius<=0:return base
    lab=cv2.cvtColor(rgba[:,:,:3],cv2.COLOR_RGB2LAB).astype(np.float32)
    refs=np.array([lab[y,x] for x,y in fg],dtype=np.float32)
    if len(refs)>1 and np.max(np.linalg.norm(refs[:,None]-refs[None,:],axis=-1))>2*tolerance:
        raise ValueError('Conflicting foreground seed colors; color refinement unsafe')
    candidate=np.zeros(base.shape,bool)
    for ref in refs:
        candidate|=(np.linalg.norm(lab-ref,axis=2)<=tolerance)
    k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*radius+1,2*radius+1))
    vicinity=cv2.dilate(base.astype(np.uint8),k).astype(bool)
    return base | (candidate & vicinity & allow)

def _topology(mask,profile):
    n,lab,stats=_components(mask)
    info={'component_count':int(n-1),'holes':0}
    # Polygon holes stay untouched; report them rather than filling by default.
    contours,hierarchy=cv2.findContours(mask.astype(np.uint8),cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is not None:
        info['holes']=sum(int(row[3]!=-1) for row in hierarchy[0])
    if profile in ('nerve','lead'):
        sk=skeletonize(mask)
        y,x=np.nonzero(sk)
        if len(x)<150000:
            # adjacency pixel degree is an approximation; dense diagonal pixels can
            # overcount junctions and must not be accepted as biological topology.
            kernel=np.ones((3,3),dtype=np.uint8);kernel[1,1]=0
            deg=cv2.filter2D(sk.astype(np.uint8),cv2.CV_16S,kernel)
            info['skeleton_pixels']=int(sk.sum())
            info['endpoint_pixels_approx']=int(np.sum(sk&(deg==1)))
            info['junction_pixels_approx']=int(np.sum(sk&(deg>=3)))
    return info

def refine_mask(candidate,rgba,instance):
    """Return (conservative visible mask, report), raise on prompt/area violation."""
    h,w=rgba.shape[:2];iid=instance['id']
    raw=np.asarray(candidate,dtype=bool)
    if raw.shape!=(h,w):raise ValueError(f'{iid}: predictor mask shape {raw.shape} != image {(h,w)}')
    profile=instance.get('profile','generic')
    if profile not in PROFILES:raise ValueError(f'{iid}: unknown medical illustration profile {profile}')
    allowed=bbox_mask(instance.get('bbox'),w,h)&(rgba[:,:,3]>=int(instance.get('min_alpha',128)))
    fg=[_point(p,w,h,iid) for p in instance.get('fg_points',[])]
    bg=[_point(p,w,h,iid) for p in instance.get('bg_points',[])]
    if not fg and instance.get('bbox') is None:raise ValueError(f'{iid}: at least fg_points or bbox required')
    cropped=raw&allowed
    if not cropped.any():raise ValueError(f'{iid}: zero pixels inside ROI')
    if any(not allowed[y,x] for x,y in fg):raise ValueError(f'{iid}: FG seed outside alpha/ROI')
    if any(not cropped[y,x] for x,y in fg):raise ValueError(f'{iid}: predicted mask misses positive prompt(s)')
    if any(cropped[y,x] for x,y in bg):raise ValueError(f'{iid}: predicted mask includes negative prompt(s)')
    # Never infer concealed wiring or connect visible fragments with morphology.
    n,labels,stats=_components(cropped)
    if fg:
        kept={int(labels[y,x]) for x,y in fg if labels[y,x]>0}
        cropped=np.isin(labels,list(kept)) & cropped
    else:
        # Box-only prompt: retain largest predicted instance to prevent incidental spill.
        biggest=1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))
        cropped=labels==biggest
    before=_topology(cropped,profile)
    out=cropped.copy()
    refine=instance.get('color_refine',False)
    added_fraction=0.
    if refine:
        if profile not in ('nerve','lead','electrode'):
            raise ValueError(f'{iid}: color_refine only for nerve/lead/electrode')
        if not fg:raise ValueError(f'{iid}: color_refine requires foreground seed')
        radius=int(instance.get('refine_radius_px',2))
        tolerance=float(instance.get('refine_lab_tolerance',13))
        max_added=float(instance.get('max_added_fraction',.18))
        if not 1<=radius<=5 or not 1<=tolerance<=45 or not 0<=max_added<=.5:
            raise ValueError(f'{iid}: invalid conservative color refinement limits')
        proposed=_color_refine(out,rgba,fg,allowed,radius,tolerance)
        # Must not accept altered topology/large expansion automatically.
        added_fraction=float((proposed&~out).sum())/max(1,int(out.sum()))
        if added_fraction>max_added:
            raise ValueError(f'{iid}: color refine adds {added_fraction:.1%}; manual correction required')
        out=proposed
    for x,y in bg:out[y,x]=False
    after=_topology(out,profile)
    n_after=after['component_count']
    if n_after>1 and not instance.get('allow_disconnected',False):
        raise ValueError(f'{iid}: {n_after} components (possible occlusion); annotate allow_disconnected after visual review')
    area=int(out.sum())
    max_area=float(instance.get('max_area_fraction',.65))
    if not 0<max_area<=1:raise ValueError('max_area_fraction must be in (0,1]')
    if area<max(1,int(instance.get('min_pixels',1))) or area>max_area*w*h:
        raise ValueError(f'{iid}: implausible mask area {area} pixels')
    if any(not out[y,x] for x,y in fg):raise ValueError(f'{iid}: refinement lost positive seed')
    if any(out[y,x] for x,y in bg):raise ValueError(f'{iid}: refinement contains background seed')
    ys,xs=np.where(out)
    visible_bbox=[int(xs.min()),int(ys.min()),int(xs.max()-xs.min()+1),int(ys.max()-ys.min()+1)]
    # Bbox edges are review warnings, not automatic rejection: cropped structures can
    # legitimately terminate on the artboard boundary.
    touch=0
    b=instance.get('bbox')
    if b:
        x,y,bw,bh=b
        touch=int(out[y:y+bh,x].sum()+out[y:y+bh,x+bw-1].sum()+out[y,x:x+bw].sum()+out[y+bh-1,x:x+bw].sum())
    warnings=[]
    if touch:warnings.append('Touching annotation ROI boundary: check for crop loss')
    if before['component_count']!=after['component_count']:
        warnings.append('Color refinement changed connected-component count; inspect for artificial joins')
    if before['holes']!=after['holes']:
        warnings.append('Color refinement changed hole count; check electrode/device inner rings')
    if n_after>1:warnings.append('Disconnected visible fragments; do not invent occluded connections')
    if profile in ('nerve','lead') and after.get('junction_pixels_approx',0)>0:
        warnings.append('Visible branches/crossings require explicit topology review')
    return out,{'pixel_count':area,'raw_pixels':int(raw.sum()),'bbox_visible':visible_bbox,
        'profile':profile,'pre_refinement':before,'post_refinement':after,
        'added_fraction':round(added_fraction,5),'roi_boundary_pixel_count':touch,
        'warnings':warnings,'review_required':True}
