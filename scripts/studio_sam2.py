"""local SAM2 prompt sessions: inference-only proposals, explicit human acceptance.

No remote service is contacted except the optional explicit --sam2-hf-model load.
Model weights are not shipped; diagnostic mock predictors are used in CI only.
"""
import base64
import io
import math
from pathlib import Path
import numpy as np
from PIL import Image
from medical_mask_postprocess import refine_mask
from sam2_medical_segment import load_sam2_predictor

MAX_PROMPTS=80

def mask_png(mask):
    b=io.BytesIO()
    Image.fromarray((np.asarray(mask,dtype=np.uint8)*255),'L').save(b,format='PNG')
    return b.getvalue()

def validate_prompts(req,w,h):
    points=req.get('points',[])
    box=req.get('box')
    if not isinstance(points,list) or len(points)>MAX_PROMPTS:
        raise ValueError('Maximum 80 prompt points')
    coords=[];labels=[]
    for p in points:
        if not isinstance(p,dict) or not isinstance(p.get('x'),(float,int)) or not isinstance(p.get('y'),(float,int)) or not math.isfinite(p['x']) or not math.isfinite(p['y']):
            raise ValueError('Invalid prompt coordinate')
        if p.get('label') not in (0,1):raise ValueError('Prompt label must be foreground=1 or background=0')
        if not 0<=p['x']<w or not 0<=p['y']<h:raise ValueError('Prompt outside canvas')
        coords.append([float(p['x']),float(p['y'])]);labels.append(int(p['label']))
    if box is not None:
        if not isinstance(box,list) or len(box)!=4 or not all(isinstance(z,(int,float)) and math.isfinite(z) for z in box):
            raise ValueError('Expected XYXY box [x0,y0,x1,y1]')
        x0,y0,x1,y1=box
        if not (0<=x0<x1<=w and 0<=y0<y1<=h):raise ValueError('Invalid bounding box')
    if not coords and box is None:raise ValueError('At least one point or box required')
    if len(coords)>0 and not any(labels) and box is None:raise ValueError('Background-only prompts need a box')
    return (np.asarray(coords,dtype=np.float32) if coords else None,
            np.asarray(labels,dtype=np.int32) if labels else None,
            np.asarray(box,dtype=np.float32) if box else None)

class SAM2StudioEngine:
    def __init__(self, source_rgb, model_spec=None, predictor=None):
        self.image=np.array(source_rgb.convert('RGB'),dtype=np.uint8,copy=True)
        self.h,self.w=self.image.shape[:2]
        self.model_spec=model_spec or {}
        self.predictor=predictor
        self.loaded=predictor is not None
        self.device='test_injected' if predictor is not None else 'uninitialized'
        self.image_set=False
        if self.predictor is None and not (self.model_spec.get('hf_model') or
            (self.model_spec.get('config') and self.model_spec.get('checkpoint'))):
            self.status='not_configured'
        else:self.status='ready_to_load' if predictor is None else 'test_predictor'

    def load(self):
        if self.status=='not_configured':raise RuntimeError('SAM2 not configured; restart studio with --sam2-hf-model or --sam2-config plus --sam2-checkpoint')
        if self.predictor is None:
            self.predictor,self.device=load_sam2_predictor(
                hf_model=self.model_spec.get('hf_model'),config=self.model_spec.get('config'),
                checkpoint=self.model_spec.get('checkpoint'),device=self.model_spec.get('device','auto'))
            self.loaded=True
        if not self.image_set:
            self.predictor.set_image(self.image)
            self.image_set=True

    def preview(self,request):
        coords,labels,box=validate_prompts(request,self.w,self.h)
        profile=request.get('profile','generic')
        if profile not in ('generic','nerve','lead','electrode','device','body'):
            raise ValueError('Unsupported medical illustration profile')
        # A caller with an object can supply its medical profile, but no model is
        # allowed to infer anatomy or hidden connections from a name alone.
        ob={'id':str(request.get('object_id','object')),'profile':profile,
            'fg_points':[x.tolist() for x,l in zip(coords if coords is not None else [],labels if labels is not None else []) if l==1],
            'bg_points':[x.tolist() for x,l in zip(coords if coords is not None else [],labels if labels is not None else []) if l==0],
            'allow_disconnected':bool(request.get('allow_disconnected',False)),
            'max_area_fraction':float(request.get('max_area_fraction',.65))}
        if box is not None:
            x0,y0,x1,y1=box.tolist()
            # bbox_mask requires integer [x,y,width,height]
            left,top=int(math.floor(x0)),int(math.floor(y0))
            right,bottom=int(math.ceil(x1)),int(math.ceil(y1))
            ob['bbox']=[left,top,right-left,bottom-top]
        self.load()
        masks,scores,_=self.predictor.predict(point_coords=coords,point_labels=labels,box=box,
                                                 multimask_output=True,normalize_coords=True)
        masks=np.asarray(masks);scores=np.asarray(scores).flatten()
        if masks.ndim==2:masks=masks[np.newaxis,:,:]
        if masks.ndim!=3 or len(masks)!=len(scores):raise ValueError('Invalid SAM2 prediction shape')
        candidates=[];rejected=[];rgba=np.dstack([self.image,np.full((self.h,self.w),255,dtype=np.uint8)])
        for i,(mask,score) in enumerate(zip(masks,scores)):
            if not np.isfinite(score) or float(score)<0 or float(score)>1:
                rejected.append({'candidate':i,'reason':'Invalid predicted score'});continue
            try:
                clean,report=refine_mask(mask,rgba,ob)
            except ValueError as exc:
                rejected.append({'candidate':i,'reason':str(exc)});continue
            png=mask_png(clean)
            candidates.append({'index':i,'score':float(score),
                'pixel_count':int(clean.sum()),'qa':report,'mask_png':png,
                'data_uri':'data:image/png;base64,'+base64.b64encode(png).decode('ascii')})
        candidates.sort(key=lambda x:-x['score'])
        return {'candidates':candidates,'rejected':rejected,'model_loaded':self.loaded,
                'device':self.device,'model_status':self.status}
