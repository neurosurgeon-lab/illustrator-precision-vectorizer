"""measured raster-vs-vector difference map, with explicitly scoped ROI.

Rendered against the *current* manifest. The heatmap is a diagnostic, not an
anatomical ground truth or a per-object precision score.
"""
import copy
import io
import math
from PIL import Image
import numpy as np
import cv2
import cairosvg
from lxml import etree
from build_vector_package import build_object,root_svg,to_xml,tag,INK_NS
from occlusion_layers import resolve_stack

MAX_PIXELS=12_000_000

def render_project(manifest,root,scale=1):
    w,h=[int(manifest['canvas'][x]) for x in ('width','height')]
    if w<1 or h<1 or w*h>MAX_PIXELS:raise ValueError('Canvas is too large for interactive diagnostic')
    order,_,_=resolve_stack(manifest)
    objects={o['id']:o for layer in manifest['layers'] for o in layer['objects']}
    scene=root_svg(w,h)
    for oid in order:
        g,_=build_object(objects[oid],root,w,h,0,'polygon')
        scene.append(g)
    binary=cairosvg.svg2png(bytestring=to_xml(scene))
    im=Image.open(io.BytesIO(binary)).convert('RGBA')
    return im

def difference(source,vector,roi=None,threshold=15,alpha_weight=1.0,max_display=1400):
    source=source.convert('RGBA');vector=vector.convert('RGBA')
    if source.size!=vector.size:raise ValueError('Source/vector size mismatch')
    w,h=source.size
    if not 0<=threshold<=255 or not 0<=alpha_weight<=5:raise ValueError('Invalid difference threshold')
    a=np.asarray(source,dtype=np.float32)
    b=np.asarray(vector,dtype=np.float32)
    # compositing over white matches default white-paper manuscript export and
    # avoids treating fully transparent RGB values as visible appearance.
    ca=a[:,:,:3]*a[:,:,3:4]/255+(255-a[:,:,3:4])
    cb=b[:,:,:3]*b[:,:,3:4]/255+(255-b[:,:,3:4])
    delta=np.mean(np.abs(ca-cb),axis=2)
    alpha_delta=np.abs(a[:,:,3]-b[:,:,3])
    # Separate alpha metric; visualization uses max to avoid hidden divergence.
    severity=np.maximum(delta,alpha_delta*alpha_weight)
    if roi is None:x0,y0,x1,y1=0,0,w,h
    else:
        if not isinstance(roi,(list,tuple)) or len(roi)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in roi):
            raise ValueError('Invalid ROI [x0,y0,x1,y1]')
        x0,y0,x1,y1=(int(round(v)) for v in roi)
        if not 0<=x0<x1<=w or not 0<=y0<y1<=h:raise ValueError('ROI is outside canvas')
    patch=severity[y0:y1,x0:x1]
    patch_rgb=delta[y0:y1,x0:x1]
    patch_alpha=alpha_delta[y0:y1,x0:x1]
    error_pixels=patch>=threshold
    # Continuous alpha scaled to intensity, not a misleading binary pass/fail map.
    m=np.uint8(np.clip(severity*(255/65),0,255))
    heat=cv2.applyColorMap(m,cv2.COLORMAP_TURBO)[:,:,::-1]
    preview=np.asarray(source.convert('RGB')).copy()
    show=severity>2
    preview[show]=np.uint8(preview[show]*.43+heat[show]*.57)
    if roi is not None:
        cv2.rectangle(preview,(x0,y0),(x1-1,y1-1),(20,150,245),2)
    image=Image.fromarray(preview,'RGB')
    if max(w,h)>max_display:
        k=max_display/max(w,h)
        image=image.resize((max(1,round(w*k)),max(1,round(h*k))),Image.Resampling.BILINEAR)
    bio=io.BytesIO();image.save(bio,'PNG')
    return {'image_png':bio.getvalue(),
            'metrics':{'scope':'ROI' if roi is not None else 'whole_canvas',
              'roi': [x0,y0,x1,y1],'threshold':threshold,
              'mae_rgb_0_255':round(float(patch_rgb.mean()),4),
              'mean_alpha_absolute_0_255':round(float(patch_alpha.mean()),4),
              'p95_visible_delta':round(float(np.percentile(patch,95)),3),
              'max_visible_delta':round(float(patch.max()),3),
              'fraction_above_threshold':round(float(error_pixels.mean()),6),
              'pixels_evaluated':int(patch.size),
              'interpretation':'Pixel difference diagnostic only; not mask IoU or anatomical accuracy.'}}

def analyze_project(manifest,root,source_path,roi=None,threshold=15):
    vector=render_project(manifest,root)
    with Image.open(source_path) as reference:
        return difference(reference,vector,roi=roi,threshold=threshold)
