#!/usr/bin/env python3
"""Trace editable *open SVG strokes* from one manually verified line/nerve mask.

Skeletonization only describes the visible 2D ink. It CANNOT determine which
of two crossing cables goes over/under, restore occluded paths, infer nerve
anatomy, or identify endpoints reliably in photographs. Crossings are split into
branches and flagged for manual topology validation.
"""
import argparse
import io
import json
import math
import re
from pathlib import Path
import cairosvg
import cv2
import networkx as nx
import numpy as np
from PIL import Image
from skimage.morphology import skeletonize

SAFE=re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*$')
DIRS=[(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]

def skeleton_graph(binary):
    skeleton=skeletonize(binary)
    pix=set(zip(*np.nonzero(skeleton)))  # (row,col)
    graph=nx.Graph();graph.add_nodes_from(pix)
    for y,x in pix:
        for dy,dx in DIRS:
            n=(y+dy,x+dx)
            if n not in pix or n<=(y,x):continue
            # Suppress redundant diagonal edges along an orthogonal two-step
            # connection. Otherwise 2px staircase pixels become fake junctions.
            if dx and dy and ((y+dy,x) in pix or (y,x+dx) in pix): continue
            graph.add_edge((y,x),n,weight=math.hypot(dx,dy))
    return graph,skeleton

def anchor_paths(graph):
    """Compress junction clusters to a single hub; preserve loops and endpoints."""
    if not graph.nodes:return [],{'endpoint_count':0,'junction_count':0,'loop_count':0,'isolates':0}
    branches={n for n,d in graph.degree() if d>=3}
    clusters=[set(v) for v in nx.connected_components(graph.subgraph(branches))]
    hubs={node:i for i,cluster in enumerate(clusters) for node in cluster}
    anchors={n for n,d in graph.degree() if d!=2}
    anchors |= branches
    # A pure closed circle has degree=2 everywhere; seed one anchor to trace loop.
    loops=0
    for component in nx.connected_components(graph):
        if not (component & anchors):
            anchors.add(min(component));loops+=1
    visited=set();paths=[]
    def key(a,b):return frozenset((a,b))
    def center(node):
        if node in hubs:
            cluster=clusters[hubs[node]]
            return (sum(n[1]+.5 for n in cluster)/len(cluster),
                    sum(n[0]+.5 for n in cluster)/len(cluster))
        return (node[1]+.5,node[0]+.5)
    # Merge all pixels of a junction cluster into a hub; internal junction edges ignored.
    for origin in sorted(anchors):
        for nxt in sorted(graph.neighbors(origin)):
            edge=key(origin,nxt)
            if edge in visited:continue
            visited.add(edge)
            if origin in hubs and nxt in hubs and hubs[origin]==hubs[nxt]:continue
            points=[center(origin)]
            prev,cur=origin,nxt
            while True:
                if cur in anchors:
                    points.append(center(cur));break
                points.append(center(cur))
                candidates=[v for v in graph.neighbors(cur) if v!=prev]
                if not candidates:break
                # Due to graph simplification an internal degree-one could appear;
                # preserve the trace and report topology rather than reconnect.
                dest=candidates[0];visited.add(key(cur,dest))
                prev,cur=cur,dest
            # Strip redundant repeated centers at merged junctions.
            clean=[points[0]]
            for pt in points[1:]:
                if math.dist(pt,clean[-1])>.01:clean.append(pt)
            if len(clean)>=2:
                paths.append(clean)
    # For junction clusters larger than one pixel: paths through other members
    # will be represented by common hub; redundant very short branches remain
    # visible in diagnostics rather than being silently removed.
    return paths,{'endpoint_count':sum(d==1 for n,d in graph.degree()),
        'junction_count':len(clusters),'junction_pixel_count':len(branches),
        'loop_count':loops,'isolates':sum(d==0 for n,d in graph.degree()),
        'graph_components':nx.number_connected_components(graph)}

def path_poly(points,epsilon=0):
    pts=np.array(points,dtype=np.float32).reshape(-1,1,2)
    if epsilon>0 and len(points)>2:
        pts=cv2.approxPolyDP(pts,epsilon,False)
    a=pts.reshape(-1,2)
    return 'M '+f'{a[0,0]:.3f},{a[0,1]:.3f}'+' '.join(' L '+f'{x:.3f},{y:.3f}' for x,y in a[1:])

def path_bezier(points):
    """Piecewise cubic smooth interpolation; only used if raster QA accepts it."""
    if len(points)<4:return path_poly(points)
    p=np.asarray(points,dtype=float);t=np.zeros_like(p)
    for i in range(1,len(p)-1):
        left=p[i]-p[i-1];right=p[i+1]-p[i]
        if min(np.linalg.norm(left),np.linalg.norm(right))<1e-6:continue
        co=np.dot(-left,right)/(np.linalg.norm(left)*np.linalg.norm(right))
        ang=np.degrees(np.arccos(np.clip(co,-1,1)))
        if ang>125:t[i]=(p[i+1]-p[i-1])/2.0
    d=f'M {p[0,0]:.3f},{p[0,1]:.3f}'
    for i in range(len(p)-1):
        c1=p[i]+t[i]/3.;c2=p[i+1]-t[i+1]/3.
        d+=f' C {c1[0]:.3f},{c1[1]:.3f} {c2[0]:.3f},{c2[1]:.3f} {p[i+1,0]:.3f},{p[i+1,1]:.3f}'
    return d

def render_strokes(paths,widths,w,h):
    content=''.join('<path d="'+d+'" fill="none" stroke="black" '
           f'stroke-width="{width:.4f}" stroke-linecap="round" stroke-linejoin="round"/>'
           for d,width in zip(paths,widths))
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{content}</svg>'
    arr=np.asarray(Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode()))).convert('RGBA'))
    return arr[:,:,3]>=128

def compare_mask(src,out):
    intersection=int((src&out).sum());union=int((src|out).sum())
    a=cv2.Canny(src.astype(np.uint8)*255,80,180)>0
    b=cv2.Canny(out.astype(np.uint8)*255,80,180)>0
    # If outlines disappear entirely, this is an invalid trace.
    if not (a.any() and b.any()):p95=float('inf')
    else:
        db=cv2.distanceTransform((~b).astype(np.uint8),cv2.DIST_L2,3)
        da=cv2.distanceTransform((~a).astype(np.uint8),cv2.DIST_L2,3)
        p95=float(np.percentile(np.r_[db[a],da[b]],95))
    return {'iou':round(intersection/union if union else 0,5),
        'boundary_distance_p95_px':round(p95,3),
        'missed_source_pixels':int((src&~out).sum()),'extra_rendered_pixels':int((out&~src).sum())}

def trace_line(mask,mode='polyline',min_iou=.85,spur_prune_px=0,epsilon=0.0,max_boundary_error_px=2.5):
    if mask.ndim!=2 or not np.any(mask):raise ValueError('Line mask is empty')
    if mode not in ('polyline','adaptive-bezier'):raise ValueError('Invalid curve mode')
    h,w=mask.shape
    graph,skel=skeleton_graph(mask)
    if spur_prune_px:
        # Deliberate opt-in only: excessive spur removal can erase short real nerves.
        # Iteratively remove terminal pixels, never whole structures automatically.
        for _ in range(int(spur_prune_px)):
            ends=[n for n,d in graph.degree() if d==1]
            if not ends:break
            graph.remove_nodes_from(ends)
        if not graph.nodes:raise ValueError('Spur pruning removed entire skeleton')
    paths,topo=anchor_paths(graph)
    if not paths:raise ValueError('No traversable line segments; likely isolated pixels')
    dt=cv2.distanceTransform(mask.astype(np.uint8),cv2.DIST_L2,5)
    # A centered stroke of width w approximately covers width/2+0.5 in DT.
    # Optimize one common editable width over discrete candidates to minimize
    # false ends; variable-width wires will get a low IoU and require redraw.
    widths_from_skel=dt[skel]
    estimate=max(.8,2*float(np.median(widths_from_skel))-.8)
    candidates=sorted({round(max(.7,estimate+offset),2) for offset in (-2,-1,-.5,0,.5,1,2)})
    base=[path_poly(p,epsilon) for p in paths]
    best=None
    for sw in candidates:
        v=compare_mask(mask,render_strokes(base,[sw]*len(base),w,h))
        if best is None or (v['iou'],-v['boundary_distance_p95_px'])>(best[1]['iou'],-best[1]['boundary_distance_p95_px']):best=(sw,v)
    width,basic=best;final=base;used='polyline';curve_test=None
    if mode=='adaptive-bezier':
        curves=[path_bezier(p) for p in paths]
        curve_test=compare_mask(mask,render_strokes(curves,[width]*len(curves),w,h))
        if curve_test['iou']>=max(min_iou,basic['iou']-.01) and curve_test['boundary_distance_p95_px']<=max(2,basic['boundary_distance_p95_px']+.3):
            final=curves;used='adaptive-bezier'
    rendered=render_strokes(final,[width]*len(final),w,h)
    qa=compare_mask(mask,rendered)
    qa.update(topo)
    qa.update({'stroke_width_px':width,'segments':len(final),'source_mask_pixels':int(mask.sum()),
        'skeleton_pixels':int(skel.sum()),'curve_mode_requested':mode,'curve_mode_used':used,
        'curve_candidate':curve_test,'meets_min_iou':bool(qa['iou']>=min_iou),
        'max_boundary_error_px':float(max_boundary_error_px),
        'meets_quality_gate':bool(qa['iou']>=min_iou and qa['boundary_distance_p95_px']<=max_boundary_error_px),
        'medical_structure_verified':False,
        'review_required':True,
        'warnings':[]})
    if topo['junction_count']:
        qa['warnings'].append('分叉/交叉不可确定线缆归属与遮挡顺序；人工确认每一条分支。')
    if topo['isolates']:
        qa['warnings'].append('存在孤立像素；中心路径未覆盖它们。')
    if topo['graph_components']>1:
        qa['warnings'].append('多个互不连接的分量；勿臆测缺失的连接线。')
    if not qa['meets_quality_gate']:
        qa['warnings'].append('IoU 或双向边缘距离不合格；保留原 mask_png 轮廓或人工修正。')
    if mode=='adaptive-bezier' and used!='adaptive-bezier':
        qa['warnings'].append('曲线平滑未通过精度门禁，已退回折线。')
    return final,qa,rendered

def process(project,object_id,mode='polyline',min_iou=.85,write_manifest=False,stroke=None,epsilon=0,allow_draft=False,max_boundary_error_px=2.5):
    root=Path(project).resolve();p=root/'manifest.json';man=json.loads(p.read_text('utf-8'))
    found=[(l,o) for l in man.get('layers',[]) for o in l.get('objects',[]) if o.get('id')==object_id]
    if len(found)!=1:raise ValueError(f'Expected exactly one object id {object_id} in manifest')
    layer,obj=found[0]
    if stroke is None:stroke=obj.get('fill')
    if not isinstance(stroke,str) or not re.fullmatch('#[0-9a-fA-F]{6}',stroke):
        raise ValueError('Cannot infer original line color; provide --stroke #RRGGBB')
    geom=obj.get('geometry',{})
    if geom.get('type')!='mask_png':raise ValueError('Only a verified mask_png object can be centerlined')
    maskfile=(root/geom['file']).resolve()
    if not maskfile.is_relative_to(root):raise ValueError('Unsafe mask path')
    with Image.open(maskfile) as im:gray=np.asarray(im.convert('L'))
    h,w=gray.shape
    if (w,h)!=(man['canvas']['width'],man['canvas']['height']):raise ValueError('Mask dimension mismatch')
    paths,qa,rendered=trace_line(gray>=128,mode=mode,min_iou=min_iou,epsilon=epsilon,max_boundary_error_px=max_boundary_error_px)
    ids={o['id'] for l in man['layers'] for o in l['objects']} - {object_id}
    specs=[]
    for i,d in enumerate(paths,1):
        sid=object_id if len(paths)==1 else f'{object_id}_branch_{i:02d}'
        if not SAFE.fullmatch(sid) or sid in ids:raise ValueError(f'Invalid/duplicate output ID {sid}')
        specs.append({'id':sid,'name_zh':obj.get('name_zh',object_id)+(f' 分支{i:02d}' if len(paths)>1 else ''),
            'name_en':obj.get('name_en',object_id),
            'geometry':{'type':'svg_path','d':d},'fill':'none',
            'stroke':stroke,'stroke_width':qa['stroke_width_px'],
            'stroke_linecap':'round','stroke_linejoin':'round',
            'notes':'Centerline from confirmed visible mask; see centerline report; topology requires review'})
    prefix=f'centerline_{object_id}'
    Image.fromarray(rendered.astype(np.uint8)*255).save(root/f'{prefix}_preview.png')
    data={'id':object_id,'mask_source':geom['file'],'stroke_source':stroke,'segments':specs,
          'qa':qa,'path_only':True,'illustrator_verified':False}
    (root/f'{prefix}_report.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    if write_manifest:
        if not qa['meets_quality_gate'] and not allow_draft:
            raise ValueError(f'Path QA failed: IoU {qa["iou"]} (minimum {min_iou}), boundary p95 {qa["boundary_distance_p95_px"]}px (maximum {max_boundary_error_px}px); manifest unchanged')
        layer['objects']=[o for o in layer['objects'] if o.get('id')!=object_id]+specs
        for m in man.get('modules',[]):
            if object_id in m.get('object_ids',[]):
                m['object_ids']=[z for z in m['object_ids'] if z!=object_id]+[s['id'] for s in specs]
        man.setdefault('qa',{}).setdefault('unresolved_details',[]).append(
            f'{object_id}: skeleton -> editable open paths; junction/topology and source-mask fidelity require human review (IoU {qa["iou"]}).')
        p.write_text(json.dumps(man,ensure_ascii=False,indent=2),encoding='utf-8')
    return data

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',required=True,type=Path)
    p.add_argument('--object-id',required=True)
    p.add_argument('--mode',choices=['polyline','adaptive-bezier'],default='polyline')
    p.add_argument('--min-iou',type=float,default=.85)
    p.add_argument('--max-boundary-error-px',type=float,default=2.5)
    p.add_argument('--epsilon',type=float,default=0)
    p.add_argument('--stroke',default=None,help='default: retain sampled color from input mask object')
    p.add_argument('--write-manifest',action='store_true')
    p.add_argument('--allow-draft',action='store_true')
    a=p.parse_args()
    if not 0<a.min_iou<=1 or a.epsilon<0 or not (0<a.max_boundary_error_px<100):raise ValueError('Invalid limits')
    if a.stroke is not None and not re.fullmatch('#[0-9a-fA-F]{6}',a.stroke):raise ValueError('stroke must be #RRGGBB')
    out=process(a.project,a.object_id,mode=a.mode,min_iou=a.min_iou,
                write_manifest=a.write_manifest,stroke=a.stroke,epsilon=a.epsilon,allow_draft=a.allow_draft,
                max_boundary_error_px=a.max_boundary_error_px)
    q=out['qa']
    print(json.dumps({'id':a.object_id,'segments':q['segments'],'iou':q['iou'],
                      'junctions':q['junction_count'],'centerline_used':q['curve_mode_used'],
                      'review_required':True,'quality_gate_passed':q['meets_quality_gate'],'manifest_written':a.write_manifest},ensure_ascii=False))

if __name__=='__main__':main()
