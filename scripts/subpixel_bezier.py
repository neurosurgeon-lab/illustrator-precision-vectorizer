#!/usr/bin/env python3
"""conservative subpixel silhouette tracing for *already separated* illustration masks.

This does NOT segment anatomy, recover hidden content, nor improve detail absent
from the image. Estimates a boundary coverage map only for sufficiently flat,
well-separated foreground/background colors (or native transparent alpha).
Rejects unsupported imagery; validates every vector candidate against the
source mask, reconstructed coverage, and number of components/holes.
"""
import argparse
import hashlib
import io
import json
import math
import re
from pathlib import Path
import cairosvg
import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter


def topology(mask):
    mask=np.asarray(mask,dtype=np.uint8)
    n,_=cv2.connectedComponents(mask,connectivity=8)
    _,hierarchy=cv2.findContours(mask*255,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    holes=0
    if hierarchy is not None:
        h=hierarchy[0]
        for i,row in enumerate(h):
            if row[3]>=0:
                depth=0;parent=row[3]
                while parent>=0:
                    depth+=1;parent=h[parent,3]
                if depth%2:holes+=1
    return {'components':int(n-1),'holes':int(holes)}


def coverage_from_source(src,mask,max_shift_px=1.5):
    """Recover conservative per-pixel foreground fraction from AA RGB or alpha.

    Flat RGB foreground/background are estimated from eroded mask and a narrow
    outer band. Candidate occupancy is allowed to vary only near known edges.
    """
    if src.shape[:2]!=mask.shape:raise ValueError('Source and mask dimensions differ')
    rgba=np.asarray(src,dtype=np.float32)
    fg=mask.astype(np.uint8)
    if min(mask.shape)<12:raise ValueError('Image too small for subpixel color statistics')
    alpha=rgba[:,:,3]/255.
    if alpha.max()-alpha.min()>.5 and float(np.percentile(alpha[mask],80))>.9:
        raw=alpha
        evidence={'model':'original_alpha','alpha_range':float(alpha.max()-alpha.min())}
    else:
        inner=cv2.erode(fg,np.ones((3,3),np.uint8),iterations=2)>0
        outer=cv2.dilate(fg,np.ones((3,3),np.uint8),iterations=2)>0
        bg=~outer
        if inner.sum()<25 or bg.sum()<25:
            raise ValueError('Insufficient isolated foreground/background pixels to estimate subpixel boundary')
        # Use samples nearest the object rather than all of a complicated scene.
        bg_near=(cv2.dilate(fg,np.ones((11,11),np.uint8))>0)&~outer
        if bg_near.sum()<25:bg_near=bg
        cf=np.median(rgba[inner,:3],axis=0);cb=np.median(rgba[bg_near,:3],axis=0)
        sf=np.median(np.abs(rgba[inner,:3]-cf),axis=0)
        sb=np.median(np.abs(rgba[bg_near,:3]-cb),axis=0)
        diff=cf-cb;contrast=float(np.linalg.norm(diff))
        if contrast<18 or max(sf.max(),sb.max())>9:
            raise ValueError(f'Non-flat / insufficient color contrast: contrast={contrast:.1f}, MADs={sf.tolist()}/{sb.tolist()}; use polygon/manual tracing')
        raw=np.clip(((rgba[:,:,:3]-cb)*diff).sum(axis=2)/max(contrast**2,1),0,1)
        # Pixels not reasonably explained as anti-alias mixing remain unchanged.
        reconstruction=cb[None,None,:]+raw[:,:,None]*diff[None,None,:]
        residual=np.linalg.norm(reconstruction-rgba[:,:,:3],axis=2)
        evidence={'model':'flat_rgb_unmix','foreground_rgb':cf.round(2).tolist(),
                  'background_rgb':cb.round(2).tolist(),'contrast_rgb':round(contrast,2),
                  'median_abs_deviation_fg':sf.round(2).tolist(),
                  'median_abs_deviation_bg':sb.round(2).tolist()}
    d_in=cv2.distanceTransform(fg,cv2.DIST_L2,5)
    d_out=cv2.distanceTransform(1-fg,cv2.DIST_L2,5)
    band=(d_in<=max_shift_px+1)&(d_out<=max_shift_px+1)
    # Only tune within 1-2 pixels of a verified instance boundary.
    cov=np.where(band,raw,fg).astype(np.float32)
    cov[~band]=fg[~band]
    if evidence['model']=='flat_rgb_unmix':
        # Refuse if more than a small portion of edge-band pixels do not fit
        # a two-color flat illustration model; never smooth photographic content.
        ambiguous=band & (cov>.08)&(cov<.92)
        bad=float(np.mean(residual[ambiguous]>20)) if ambiguous.any() else 0.
        evidence['ambiguous_edge_fraction_with_high_color_residual']=round(bad,4)
        if bad>.15:raise ValueError('Antialias edge colors violate two-color mixing model; keep original mask')
    return cov,evidence


def contour_paths(coverage,scale,epsilon_px=0.,bezier=False,corner_angle=110):
    h,w=coverage.shape
    hi=cv2.resize(coverage,(w*scale,h*scale),interpolation=cv2.INTER_LINEAR)
    binary=(hi>=.5).astype(np.uint8)
    # Include pixels clipped by the image boundary, never invent off-canvas ink.
    contours,_=cv2.findContours(binary*255,cv2.RETR_TREE,cv2.CHAIN_APPROX_NONE)
    output=[];anchors=0
    for contour in contours:
        if len(contour)<3:continue
        p=contour.reshape(-1,2).astype(float)
        if epsilon_px>0:
            p=cv2.approxPolyDP(contour,float(epsilon_px*scale),True).reshape(-1,2).astype(float)
        p=(p+.5)/scale-.5
        n=len(p)
        if n<3:continue
        anchors+=n
        if bezier and n>=5:
            t=[]
            for i in range(n):
                a=p[(i-1)%n]-p[i];b=p[(i+1)%n]-p[i]
                angle=math.degrees(math.acos(float(np.clip(np.dot(a,b)/max(np.linalg.norm(a)*np.linalg.norm(b),1e-8),-1,1))))
                t.append(np.zeros(2) if angle<corner_angle else (p[(i+1)%n]-p[(i-1)%n])*.5)
            seq=[f'M {p[0,0]:.4f},{p[0,1]:.4f}']
            for i in range(n):
                j=(i+1)%n;c1=p[i]+t[i]/3;c2=p[j]-t[j]/3
                seq.append(f'C {c1[0]:.4f},{c1[1]:.4f} {c2[0]:.4f},{c2[1]:.4f} {p[j,0]:.4f},{p[j,1]:.4f}')
            seq.append('Z')
        else:
            seq=[f'M {p[0,0]:.4f},{p[0,1]:.4f}']+[f'L {x:.4f},{y:.4f}' for x,y in p[1:]]+['Z']
        output.append(' '.join(seq))
    if not output:raise ValueError('No contours in supersampled coverage')
    return ' '.join(output),anchors,binary.astype(bool)


def render_svg_path(d,w,h,scale=3):
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><path d="{d}" fill="#000000" fill-rule="evenodd" /></svg>'
    pix=cairosvg.svg2png(bytestring=svg.encode(),output_width=w*scale,output_height=h*scale)
    return np.asarray(Image.open(io.BytesIO(pix)).convert('RGBA'))[:,:,3]>=128


def metrics(ref,pred,scale=1):
    a=np.asarray(ref,dtype=bool);b=np.asarray(pred,dtype=bool)
    if a.shape!=b.shape:raise ValueError('Shape mismatch')
    union=np.count_nonzero(a|b);inter=np.count_nonzero(a&b)
    ea=cv2.Canny(a.astype('uint8')*255,50,150)>0
    eb=cv2.Canny(b.astype('uint8')*255,50,150)>0
    if ea.any() and eb.any():
        da=cv2.distanceTransform((~ea).astype('uint8'),cv2.DIST_L2,5)
        db=cv2.distanceTransform((~eb).astype('uint8'),cv2.DIST_L2,5)
        q95=float(np.percentile(np.r_[da[eb],db[ea]],95))/scale
    else:q95=float('inf')
    return {'iou':round(float(inter/union if union else 0),6),'boundary_p95_px':round(q95,4)}


def refine(mask,source_rgba,scale=3,min_native_iou=.975,min_super_iou=.94,max_boundary_px=1.0):
    if scale not in (2,3,4):raise ValueError('Subpixel scale must be 2,3,4')
    mask=np.asarray(mask,dtype=bool)
    if not mask.any():raise ValueError('Empty mask')
    cov,evidence=coverage_from_source(source_rgba,mask)
    _,_,target=contour_paths(cov,scale)
    native_topo=topology(mask)
    _,native_truth=cv2.threshold((cov*255).astype('uint8'),127,255,cv2.THRESH_BINARY)
    trials=[];best=None
    for mode,eps in [('polyline',0.),('polyline',.2),('polyline',.35),('bezier',.2),('bezier',.35),('bezier',.55),('bezier',.75),('bezier',1.)]:
        d,n,_=contour_paths(cov,scale,eps,bezier=mode=='bezier')
        r=render_svg_path(d,mask.shape[1],mask.shape[0],scale)
        rr=cv2.resize(r.astype('uint8'),(mask.shape[1],mask.shape[0]),interpolation=cv2.INTER_AREA)>=.5
        qa_hi=metrics(target,r,scale)
        qa_native=metrics(mask,rr)
        tp=topology(rr)
        ok=(qa_native['iou']>=min_native_iou and qa_hi['iou']>=min_super_iou
            and qa_hi['boundary_p95_px']<=max_boundary_px and tp==native_topo)
        trial={'mode':mode,'epsilon_px':eps,'anchor_count':n,'native':qa_native,'supersampled':qa_hi,
               'topology':tp,'passed':bool(ok)}
        trials.append(trial)
        if ok:
            # Prefer fewer control points; error as tie breaker.
            key=(n,-qa_hi['iou'],qa_hi['boundary_p95_px'])
            if best is None or key<best[0]:best=(key,d,trial,r)
    if best is None:
        return None,{'passed':False,'evidence':evidence,'source_topology':native_topo,'trials':trials,
                     'warning':'All candidates failed. Keep mask geometry; do not commit.'},None
    _,d,choice,preview=best
    return d,{'passed':True,'evidence':evidence,'source_topology':native_topo,
              'selected':choice,'trials':trials,'review_required':True,
              'subpixel_claim':'Color/alpha edge estimate validated against source mask; not recovered ground truth.'},preview


def process(project,object_id,write_manifest=False,scale=3,**kwargs):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*",object_id):raise ValueError("Unsafe object ID")
    root=Path(project).resolve();mf=root/'manifest.json';man=json.loads(mf.read_text('utf-8'))
    matches=[o for l in man.get('layers',[]) for o in l.get('objects',[]) if o['id']==object_id]
    if len(matches)!=1:raise ValueError('Exactly one object id required')
    obj=matches[0];geom=obj.get('geometry',{})
    if geom.get('type')!='mask_png':raise ValueError('Subpixel refinement requires preserved mask_png')
    mp=(root/geom['file']).resolve()
    if not mp.is_relative_to(root):raise ValueError('Mask escapes project')
    with Image.open(mp) as im:mask=np.asarray(im.convert('L'))>=128
    source=(root/man['source_image']).resolve()
    if not source.is_relative_to(root):raise ValueError('Source escapes project')
    with Image.open(source) as im:rgba=np.asarray(im.convert('RGBA'))
    d,qa,preview=refine(mask,rgba,scale=scale,**kwargs)
    qa.update({'id':object_id,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
               'original_mask':geom['file'],'scale':scale,'committed':False})
    (root/f'subpixel_{object_id}_report.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
    if preview is not None:
        Image.fromarray((preview*255).astype('uint8')).save(root/f'subpixel_{object_id}_preview_{scale}x.png')
    if write_manifest:
        if not qa['passed']:raise ValueError('Subpixel QA failed; original manifest unchanged')
        obj['geometry']={'type':'svg_path','d':d,'source_mask_file':geom['file'],
                         'subpixel_report':f'subpixel_{object_id}_report.json'}
        # OpenCV nested contours must keep their holes across SVG viewers.
        obj['fill_rule']='evenodd'
        man.setdefault('qa',{}).setdefault('unresolved_details',[]).append(
            f'{object_id}: subpixel estimate is not anatomical ground truth; manually review edge and holes.')
        mf.write_text(json.dumps(man,ensure_ascii=False,indent=2),encoding='utf-8')
        qa['committed']=True
        (root/f'subpixel_{object_id}_report.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
    return qa


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',required=True,type=Path);p.add_argument('--object-id',required=True)
    p.add_argument('--scale',type=int,choices=(2,3,4),default=3)
    p.add_argument('--min-native-iou',type=float,default=.975)
    p.add_argument('--min-super-iou',type=float,default=.94)
    p.add_argument('--max-boundary-px',type=float,default=1.)
    p.add_argument('--write-manifest',action='store_true')
    a=p.parse_args()
    q=process(a.project,a.object_id,a.write_manifest,scale=a.scale,
              min_native_iou=a.min_native_iou,min_super_iou=a.min_super_iou,
              max_boundary_px=a.max_boundary_px)
    print(json.dumps({'object_id':a.object_id,'passed':q['passed'],
          'selected':q.get('selected'),'manifest_written':q['committed']},ensure_ascii=False))
    if not q['passed']:raise SystemExit(2)

if __name__=='__main__':main()
