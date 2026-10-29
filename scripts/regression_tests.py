#!/usr/bin/env python3
"""Adversarial tests for fidelity gates, bbox layout, source SVG, ROIs and seeds."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from PIL import Image,ImageDraw
import cairosvg
from lxml import etree

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'scripts'/'build_vector_package.py'
INIT=ROOT/'scripts'/'init_project.py'
SEEDS=ROOT/'scripts'/'seed_segment.py'

def run(*args,ok=True):
    r=subprocess.run([sys.executable,*map(str,args)],capture_output=True,text=True)
    if bool(r.returncode==0)!=ok:
        raise AssertionError(f'Expected success={ok}, status={r.returncode}, stderr={r.stderr[-900:]}')
    return r

def manifest(p,color='#0000FF',d='M0 0 H80 V60 H0 Z',bbox=None,qa=None):
    o={'id':'a','geometry':{'type':'svg_path','d':d},'fill':color,'stroke':'none'}
    if bbox is not None:o['bbox']=bbox
    m={'schema_version':'1.0','source_image':'source.png','canvas':{'width':80,'height':60},
       'layers':[{'id':'one','name_zh':'一','objects':[o]}],
       'modules':[{'id':'m','name_zh':'一','object_ids':['a']}], 'qa':qa or {}}
    (p/'manifest.json').write_text(json.dumps(m,ensure_ascii=False))

with tempfile.TemporaryDirectory() as tmp:
    t=Path(tmp)
    # A: full-color mismatch must fail and withhold final zip.
    p=t/'mismatch';p.mkdir();Image.new('RGB',(80,60),'red').save(p/'source.png')
    manifest(p,'#0000FF')
    run(BUILD,'--project',p,'--out',t/'mismatch_out',ok=False)
    j=json.loads((t/'mismatch_out'/'quality_report.json').read_text())
    assert j['fidelity_status']=='failed' and not (t/'mismatch_out'/'08_All_Files.zip').exists()
    assert j['release_ready'] is False
    # Draft is allowed only with explicit flag, and remains FAILED.
    run(BUILD,'--project',p,'--out',t/'draft','--allow-draft')
    assert json.loads((t/'draft'/'quality_report.json').read_text())['fidelity_status']=='failed'
    # B: wrong hand-entered bbox corrected, not allowed to hide breakdown object.
    q=t/'bbox';q.mkdir();Image.new('RGB',(80,60),'blue').save(q/'source.png')
    manifest(q,'#0000FF',bbox=[10000,10000,80,60])
    run(BUILD,'--project',q,'--out',t/'bbox_out')
    j=json.loads((t/'bbox_out'/'quality_report.json').read_text())
    assert j['declared_bbox_mismatches'] and j['declared_bbox_mismatches'][0]['measured']==[0,0,80,60]
    # C: empty path must be rejected (even though SVG path XML exists).
    r=t/'empty';r.mkdir();Image.new('RGB',(80,60),'white').save(r/'source.png')
    manifest(r,'#FFFFFF',d='M 10 10')
    run(BUILD,'--project',r,'--out',t/'empty_out',ok=False)
    # D: transparent/background mismatch must fail (alpha is not erased by white comparison).
    v=t/'alpha';v.mkdir();Image.new('RGBA',(80,60),(0,0,255,0)).save(v/'source.png')
    manifest(v,'#FFFFFF')
    run(BUILD,'--project',v,'--out',t/'alpha_out',ok=False)
    j=json.loads((t/'alpha_out'/'quality_report.json').read_text())
    assert any(f['metric']=='max_mae_alpha' for f in j['fidelity_failures'])
    # E: tiny critical device ROI wrong while global QA stays below thresholds.
    z=t/'roi';z.mkdir()
    base=Image.new('RGB',(200,200),'white');draw=ImageDraw.Draw(base)
    for x in [10,40,70,100,130,160]:draw.line([(x,10),(x,190)],fill='black',width=2)
    draw.rectangle([181,181,189,189],fill='red');base.save(z/'source.png')
    objects=[{'id':'bg','geometry':{'type':'svg_path','d':'M 0 0 H200 V200 H0Z'},'fill':'#FFFFFF','stroke':'none'}]
    for x in [10,40,70,100,130,160]:
        objects.append({'id':f'line_{x}','geometry':{'type':'svg_path','d':f'M{x},10 V190'},'fill':'none','stroke':'#000000','stroke_width':2,'stroke_linecap':'butt'})
    objects.append({'id':'electrode','geometry':{'type':'svg_path','d':'M181 181 H190 V190 H181 Z'},'fill':'#0000FF','stroke':'none'})
    mm={'schema_version':'1.0','source_image':'source.png','canvas':{'width':200,'height':200},
        'layers':[{'id':'l','objects':objects}],
        'qa':{'key_regions':[{'name':'electrode_critical','bbox':[180,180,12,12]}]}}
    (z/'manifest.json').write_text(json.dumps(mm))
    paths=[]
    for ob in objects:
        paths.append(f'<path d="{ob["geometry"]["d"]}" fill="{("#FF0000" if ob["id"]=="electrode" else ob["fill"])}" stroke="{ob.get("stroke","none")}" stroke-width="{ob.get("stroke_width",1)}" stroke-linecap="{ob.get("stroke_linecap","butt")}"/>')
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'+''.join(paths)+'</svg>'
    cairosvg.svg2png(bytestring=svg.encode(),write_to=str(z/'source.png'))
    run(BUILD,'--project',z,'--out',t/'roi_out',ok=False)
    jj=json.loads((t/'roi_out'/'quality_report.json').read_text())
    assert jj['key_region_failures']
    assert jj['image_comparison']['mae_rgb_0_255']<12
    # F: original vector SVG imported without re-tracing (contains exact authored paths).
    demo=ROOT/'examples'/'demo_project'
    run(BUILD,'--project',demo,'--out',t/'original')
    run(INIT,'--image',t/'original'/'01_Full_Illustration.svg','--out',t/'svgproj')
    run(BUILD,'--project',t/'svgproj','--out',t/'svg_out',ok=False)
    imported=json.loads((t/'svg_out'/'quality_report.json').read_text())
    assert imported['image_comparison']['mae_rgb_0_255']==0
    assert imported['object_count']==12
    assert imported['line_quality']['required'] and imported['line_quality']['status']=='blocked'
    assert not (t/'svg_out'/'08_All_Files.zip').exists(),'New projects must require line review even for pixel-perfect SVG imports'
    # G: Bézier falls back/accepts based on explicit mask fidelity check.
    run(BUILD,'--project',demo,'--out',t/'bezier','--trace-mode','adaptive-bezier')
    layers=json.loads((t/'bezier'/'06_Layer_Manifest.json').read_text())['layers']
    masks=[o for l in layers for o in l['objects'] if o['geometry_type']=='mask_png']
    assert len(masks)==1 and masks[0]['trace_diagnostics']['trace_mode_used'] in ['adaptive-bezier','polygon']
    # H: seed segmentation splits disconnected same-color regions.
    seed=t/'seeds';seed.mkdir()
    rgb=Image.new('RGB',(100,70),'white');draw=ImageDraw.Draw(rgb)
    draw.ellipse([5,10,28,34],fill='red');draw.ellipse([61,10,84,34],fill='red');rgb.save(seed/'reference.png')
    run(INIT,'--image',seed/'reference.png','--out',t/'seedproj')
    points={'objects':[{'id':'red_left','x':15,'y':20,'tolerance':0,'layer_id':'l'},
                       {'id':'red_right','x':73,'y':20,'tolerance':0,'layer_id':'l'}]}
    (t/'seeds.json').write_text(json.dumps(points))
    run(SEEDS,'--project',t/'seedproj','--seeds',t/'seeds.json')
    assert (t/'seedproj'/'masks'/'red_left.png').exists()
    assert (t/'seedproj'/'masks'/'red_right.png').exists()
    assert len(json.loads((t/'seedproj'/'manifest.json').read_text())['layers'][0]['objects'])==2
    print('PASS (8 adversarial groups): fidelity hard gate, explicit draft, actual bbox, invisible path, alpha, critical ROI, source SVG roundtrip, validated Bezier, disconnected seeded objects')
