#!/usr/bin/env python3
"""preserve the *visible* variable width of confirmed nerve/lead masks.

SVG 1.1 has no standard native variable-width stroke. This produces a true
filled outline (editable SVG path) and records separate editable centerline
and width samples in the manifest; it does NOT claim an Illustrator Width Tool
profile. Junction topology, visibility and hidden paths still require review.
"""
import argparse
import io
import json
import math
import re
from pathlib import Path
import cairosvg
import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter1d
from centerline_trace import skeleton_graph,anchor_paths,path_poly,compare_mask,trace_line


def geometry_outline(points,radii,cap_samples=9):
    """Construct a single filled round-capped tube about a sampled centerline."""
    p=np.asarray(points,dtype=float)
    r=np.asarray(radii,dtype=float)
    if len(p)<2 or len(p)!=len(r):raise ValueError('Path/radii mismatch')
    derivatives=np.gradient(p,axis=0)
    lengths=np.linalg.norm(derivatives,axis=1)
    tangent=derivatives/np.maximum(lengths[:,None],1e-8)
    normal=np.c_[-tangent[:,1],tangent[:,0]]
    left=p+normal*r[:,None];right=p-normal*r[:,None]
    # Circle caps follow the end and start tangent directions.
    def arc(center,start_angle,end_angle,radius):
        angles=np.linspace(start_angle,end_angle,cap_samples)
        return center[None,:]+radius*np.c_[np.cos(angles),np.sin(angles)]
    a1=math.atan2(normal[-1,1],normal[-1,0]);a0=math.atan2(normal[0,1],normal[0,0])
    endcap=arc(p[-1],a1,a1-math.pi,r[-1])[1:-1]
    startcap=arc(p[0],a0+math.pi,a0,r[0])[1:-1]
    polygon=np.concatenate((left,endcap,right[::-1],startcap),axis=0)
    if not np.isfinite(polygon).all():raise ValueError('Invalid tube polygon')
    return 'M '+f'{polygon[0,0]:.4f},{polygon[0,1]:.4f}'+' '.join(f' L {x:.4f},{y:.4f}' for x,y in polygon[1:])+' Z'


def render_outline(d,w,h):
    svg=(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
         f'viewBox="0 0 {w} {h}"><path d="{d}" fill="#000000" fill-rule="nonzero"/></svg>')
    pix=cairosvg.svg2png(bytestring=svg.encode())
    return np.asarray(Image.open(io.BytesIO(pix)).convert('RGBA'))[:,:,3]>=128


def candidates_variable(mask,width_smooth_px=2.0):
    """Select round tubes based on mask medial distance, preserving endpoints."""
    h,w=mask.shape
    graph,_=skeleton_graph(mask)
    paths,topo=anchor_paths(graph)
    if not paths:raise ValueError('No traversable path')
    dt=cv2.distanceTransform(mask.astype('uint8'),cv2.DIST_L2,5)
    tubes=[];profiles=[];radius_raw=[]
    for path in paths:
        xy=np.asarray(path,dtype=np.float32)
        # Graph paths have near-unit pixel step; smooth radius over path arc.
        ix=np.clip(np.rint(xy[:,0]-.5).astype(int),0,w-1)
        iy=np.clip(np.rint(xy[:,1]-.5).astype(int),0,h-1)
        radii=np.maximum(.45,dt[iy,ix]-.25)
        smooth=gaussian_filter1d(radii,float(width_smooth_px),mode='nearest') if len(path)>3 else radii
        smooth=np.maximum(.4,smooth)
        radius_raw.extend(smooth.tolist())
        tubes.append((path,smooth))
        profiles.append({'centerline_d':path_poly(path,0.),'width_samples_px':np.round(2*smooth,3).tolist(),
                         'points_xy':np.round(xy,3).tolist()})
    return tubes,profiles,topo,radius_raw


def fit_variable(mask,minimum_iou=.80,max_boundary_error_px=2.5,width_smooth_px=2.):
    if mask.ndim!=2 or not mask.any():raise ValueError('Empty line mask')
    h,w=mask.shape
    tubes,profiles,topo,radii=candidates_variable(mask,width_smooth_px)
    uniform_paths,uniform_qa,_=trace_line(mask,mode='polyline',min_iou=.1)
    candidates=[];winner=None
    for factor in (.82,.90,.96,1.,1.04,1.10,1.18):
        d=' '.join(geometry_outline(p,np.asarray(r)*factor) for p,r in tubes)
        v=compare_mask(mask,render_outline(d,w,h))
        candidates.append({'width_factor':factor,**v})
        score=(v['iou'],-v['boundary_distance_p95_px'])
        if winner is None or score>winner[0]:winner=(score,d,factor,v)
    _,d,factor,metrics=winner
    for p in profiles:p['width_samples_px']=[round(x*factor,3) for x in p['width_samples_px']]
    # Variable width must improve materially if enabled for a varying wire;
    # equal accuracy is acceptable only when profile is almost constant.
    width_values=np.asarray(radii)*2*factor
    q10,q90=np.percentile(width_values,[10,90])
    width_dynamic_range=float(q90/q10) if q10>.01 else float('inf')
    quality=bool(metrics['iou']>=minimum_iou and metrics['boundary_distance_p95_px']<=max_boundary_error_px)
    return d,profiles,{'passed':quality,'mask_iou':metrics['iou'],
        'boundary_distance_p95_px':metrics['boundary_distance_p95_px'],
        'baseline_uniform_iou':uniform_qa['iou'],
        'improvement_over_uniform_iou':round(metrics['iou']-uniform_qa['iou'],5),
        'width_dynamic_range_p90_over_p10':round(width_dynamic_range,3),
        'optimized_width_factor':factor,'candidate_width_factors':candidates,
        'branch_count':len(tubes),'junction_count':topo['junction_count'],
        'endpoint_count':topo['endpoint_count'],'topology':topo,
        'centerline_profile_editable':True,
        'native_illustrator_width_profile':False,
        'review_required':True,
        'warnings':(['Junction / over-under crossing must be manually confirmed.'] if topo['junction_count'] else [])
       +(['Variable outline failed QA; do not write manifest.'] if not quality else [])}


def process(project,object_id,write_manifest=False,minimum_iou=.8,max_boundary_error_px=2.5,width_smooth_px=2.):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*",object_id):raise ValueError("Unsafe object ID")
    root=Path(project).resolve();mf=root/'manifest.json';man=json.loads(mf.read_text('utf-8'))
    matches=[o for l in man.get('layers',[]) for o in l.get('objects',[]) if o['id']==object_id]
    if len(matches)!=1:raise ValueError('Expected exactly one object id')
    obj=matches[0];geometry=obj.get('geometry',{})
    if geometry.get('type')!='mask_png':raise ValueError('Variable width requires original mask_png')
    mp=(root/geometry['file']).resolve()
    if not mp.is_relative_to(root):raise ValueError('Unsafe mask file')
    with Image.open(mp) as im:mask=np.asarray(im.convert('L'))>=128
    if mask.shape!=(man['canvas']['height'],man['canvas']['width']):raise ValueError('Mask dimension mismatch')
    original_fill=obj.get('fill')
    if not isinstance(original_fill,str) or len(original_fill)!=7 or not original_fill.startswith('#'):
        raise ValueError('Cannot preserve original color without HEX fill')
    d,profiles,qa=fit_variable(mask,minimum_iou,max_boundary_error_px,width_smooth_px)
    data={'id':object_id,'qa':qa,'geometry':{'type':'svg_path','d':d,
        'centerline_profiles':profiles,'width_representation':'filled_outline_plus_hidden_centerline',
        'source_mask_file':geometry['file']},'stroke_color':original_fill}
    (root/f'variable_width_{object_id}_report.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    Image.fromarray((render_outline(d,*mask.shape[::-1])*255).astype('uint8')).save(root/f'variable_width_{object_id}_preview.png')
    if write_manifest:
        if not qa['passed']:raise ValueError('Variable width QA failed; manifest unchanged')
        obj['geometry']=data['geometry'];obj['fill_rule']='nonzero';obj['fill']=original_fill
        obj['stroke']='none';obj['stroke_width']=0
        obj['notes']='Visible tube outline + hidden editable centerline profile; not a native Illustrator variable-width stroke'
        man.setdefault('qa',{}).setdefault('unresolved_details',[]).append(
            f'{object_id}: visible varying width preserved as editable filled outline; native Illustrator width profile NOT verified.')
        mf.write_text(json.dumps(man,ensure_ascii=False,indent=2),encoding='utf-8')
    return data


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',required=True,type=Path);p.add_argument('--object-id',required=True)
    p.add_argument('--min-iou',type=float,default=.80)
    p.add_argument('--max-boundary-error-px',type=float,default=2.5)
    p.add_argument('--width-smoothing-px',type=float,default=2.)
    p.add_argument('--write-manifest',action='store_true')
    a=p.parse_args()
    if not 0<a.min_iou<=1 or a.width_smoothing_px<0 or a.max_boundary_error_px<=0:
        raise ValueError('Invalid quality constraints')
    data=process(a.project,a.object_id,a.write_manifest,a.min_iou,
                 a.max_boundary_error_px,a.width_smoothing_px)
    print(json.dumps({'id':a.object_id,'qa':data['qa'],'manifest_written':a.write_manifest},ensure_ascii=False))
    if not data['qa']['passed']:raise SystemExit(2)

if __name__=='__main__':main()
