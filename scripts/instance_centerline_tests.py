#!/usr/bin/env python3
"""Deterministic nonclinical regression tests for guided segmentation and centerlines."""
import json
import tempfile
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from centerline_trace import trace_line, process as trace_project
from medical_instance_segment import process as segment_project, segment_one


def make_project(root,source):
    root.mkdir(parents=True,exist_ok=True)
    Image.fromarray(source).save(root/'source.png')
    h,w=source.shape[:2]
    (root/'manifest.json').write_text(json.dumps({'schema_version':'1.0','source_image':'source.png',
        'canvas':{'width':w,'height':h},'layers':[],'modules':[],'qa':{}},ensure_ascii=False),encoding='utf-8')

with tempfile.TemporaryDirectory() as td:
    p=Path(td)
    # Identically colored objects MUST be separate instances with independent IDs.
    rgba=np.full((100,160,4),255,dtype=np.uint8)
    cv2.circle(rgba,(35,45),17,(250,120,100,255),-1)
    cv2.circle(rgba,(125,45),17,(250,120,100,255),-1)
    proj=p/'disjoint';make_project(proj,rgba)
    specs={'instances':[
        {'id':'electrode_left','name_zh':'左电极','method':'seed_lab','fg_points':[[35,45]],'bbox':[12,20,45,50], 'lab_tolerance':2},
        {'id':'electrode_right','name_zh':'右电极','method':'seed_lab','fg_points':[[125,45]],'bbox':[100,20,50,50], 'lab_tolerance':2}]}
    ann=p/'instances.json';ann.write_text(json.dumps(specs,ensure_ascii=False),encoding='utf-8')
    report=segment_project(proj,ann)
    assert report['instance_count']==2 and not report['overlap_pairs']
    assert report['instances'][0]['pixel_count']>800
    l=np.asarray(Image.open(proj/'masks/electrode_left.png').convert('L'))>0
    r=np.asarray(Image.open(proj/'masks/electrode_right.png').convert('L'))>0
    assert (l&r).sum()==0 and l[45,35] and r[45,125] and not l[45,125]
    # Opposing colors in foreground seeds must NOT silently join a neural structure
    # and its adjacent electrode (regression found in the original synthetic demo).
    try:
        segment_one(rgba,{'id':'mixed_seed','method':'seed_lab','bbox':[10,15,145,65],
                          'fg_points':[[35,45],[80,45]], 'lab_tolerance':2})
    except ValueError:pass
    else:raise AssertionError('Conflicting color seed marks were accepted')
    # Full-frame GrabCut with no BG annotations must fail closed.
    try:segment_one(rgba,{'id':'x','method':'grabcut','fg_points':[[35,45]]})
    except ValueError:pass
    else:raise AssertionError('Unconstrained GrabCut unexpectedly allowed')
    # A bounded GrabCut object is isolated from an identically colored one.
    mask,meta=segment_one(rgba,{'id':'grab_left','method':'grabcut','bbox':[10,16,60,65],
        'fg_points':[[35,45]],'bg_points':[[12,17],[60,70]], 'lab_tolerance':19,'brush_radius':2})
    assert mask[45,35] and not mask[45,125] and mask.sum()>400,meta
    # Curated straight wire centerline, exact count, round stroke approximation.
    line=np.zeros((120,180),dtype=np.uint8)
    cv2.line(line,(15,70),(165,70),255,5,cv2.LINE_8)
    paths,qa,preview=trace_line(line>0,mode='adaptive-bezier',min_iou=.8)
    assert len(paths)==1 and qa['endpoint_count']==2 and qa['junction_count']==0 and qa['iou']>.9
    assert paths[0].startswith('M ') and 'Z' not in paths[0]
    # Y-shaped nerve branches => independent segments, one junction hub.
    y=np.zeros_like(line)
    cv2.line(y,(85,108),(85,50),255,5)
    cv2.line(y,(85,50),(30,12),255,5)
    cv2.line(y,(85,50),(140,12),255,5)
    yp,yq,_=trace_line(y>0,min_iou=.8)
    assert len(yp)==3 and yq['endpoint_count']==3 and yq['junction_count']==1 and yq['iou']>.85,yq
    assert yq['review_required'] and any('分叉' in x for x in yq['warnings'])
    # Closed loop must NOT invent open free endpoints.
    loop=np.zeros((120,180),dtype=np.uint8);cv2.circle(loop,(90,60),34,255,5)
    lp,lq,_=trace_line(loop>0)
    assert lq['endpoint_count']==0 and lq['loop_count']==1 and lq['iou']>.8
    # Crossing means ambiguity; branch count >2 and explicit warning.
    crossing=np.zeros_like(line)
    cv2.line(crossing,(15,60),(165,60),255,5)
    cv2.line(crossing,(90,15),(90,105),255,5)
    cp,cq,_=trace_line(crossing>0)
    assert cq['junction_count']==1 and cq['endpoint_count']==4 and cq['segments']==4
    # One-pixel noise cannot masquerade as an editable line.
    noise=np.zeros_like(line);noise[50,50]=255
    try:trace_line(noise>0)
    except ValueError:pass
    else:raise AssertionError('Isolated pixel accepted')
    # Integration: trace a project mask to PATH strokes, preserve layer + module IDs.
    proj2=p/'wire'; rgba2=np.full((120,180,4),255,dtype=np.uint8)
    rgba2[line>0,:3]=(90,110,140)
    make_project(proj2,rgba2)
    ann2=p/'wire.json'
    ann2.write_text(json.dumps({'instances':[{'id':'vagus_wire','name_zh':'神经示意线',
        'fg_points':[[50,70]],'bbox':[5,60,170,20], 'lab_tolerance':2}]}),encoding='utf-8')
    segment_project(proj2,ann2)
    res=trace_project(proj2,'vagus_wire',min_iou=.80,mode='adaptive-bezier',write_manifest=True,stroke='#5A6E8C')
    final=json.loads((proj2/'manifest.json').read_text('utf-8'))
    assert res['qa']['iou']>.90 and final['layers'][0]['objects'][0]['geometry']['type']=='svg_path'
    assert final['layers'][0]['objects'][0]['fill']=='none'
    assert len(final['modules'])==1
    print('PASS: 8 medical instance+centerline regression groups (seed instances, GrabCut guards, line, Y branch, loop, crossing, noise rejection, editable manifest roundtrip)')
