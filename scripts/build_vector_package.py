#!/usr/bin/env python3
"""Compile curated semantic masks/SVG paths into editable SVG and exploded-view files.

This program does not detect anatomy or generate missing outlines. Each provided
mask is vectorized into polygons; hand-traced SVG path is preferred for curves.
"""
import argparse
import copy
import csv
import hashlib
import json
import math
import re
import zipfile
import io
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import cairosvg
from mask_precision import trace_mask
from lxml import etree

SVG_NS = 'http://www.w3.org/2000/svg'
INK_NS = 'http://www.inkscape.org/namespaces/inkscape'
# This is the official Inkscape SVG namespace, not an Adobe layer guarantee.
NSMAP = {None:SVG_NS, 'inkscape':INK_NS}
HEX = re.compile(r'^#[0-9A-Fa-f]{6}$')
ID_RE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.-]*$')

def tag(name): return f'{{{SVG_NS}}}{name}'
def safe_id(value):
    if not isinstance(value,str) or not ID_RE.fullmatch(value):
        raise ValueError(f'Invalid SVG ID (use ASCII letters/numbers/_/-): {value!r}')
    return value

def local_path(root, relative):
    if not isinstance(relative,str): raise ValueError('Path must be a string')
    p=(root/relative).resolve()
    if not p.is_relative_to(root.resolve()): raise ValueError(f'Path escapes project: {relative}')
    if not p.is_file(): raise ValueError(f'File does not exist: {relative}')
    return p

def color(value, default='none'):
    v=default if value is None else value
    if v=='none': return v
    if not isinstance(v,str) or not HEX.fullmatch(v): raise ValueError(f'Invalid HEX color {v!r}')
    return v.upper()

def geom_from_mask(path,w,h,epsilon,trace_mode):
    return trace_mask(path,w,h,epsilon,mode=trace_mode)


def visible_bbox(group,w,h):
    """Calculate a path's REAL visible pixel bounds including curves and strokes.

    Actual SVG renderer is the geometry oracle; avoids inaccurate manual bbox,
    and works for cubic Beziers, relative commands, elliptical arcs and holes.
    Returns alpha bounds in source pixels (subpixel precision limited to 1px).
    """
    stage=root_svg(w,h)
    stage.append(copy.deepcopy(group))
    png=cairosvg.svg2png(bytestring=to_xml(stage))
    with Image.open(io.BytesIO(png)) as im:
        alpha=im.convert('RGBA').getchannel('A')
        bounds=alpha.getbbox()
    if bounds is None:
        raise ValueError(f'{group.get("id")}: object has no visible geometry (empty path, fully transparent or off-canvas)')
    x0,y0,x1,y1=bounds
    return [x0,y0,x1-x0,y1-y0]


def bbox_disagreement(expected,real):
    if expected is None:return None
    if not isinstance(expected,list) or len(expected)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in expected):
        raise ValueError('Manifest bbox must be 4 finite numbers')
    x,y,bw,bh=[float(v) for v in expected]
    if bw<=0 or bh<=0:raise ValueError('Manifest bbox has nonpositive size')
    delta=[abs(a-b) for a,b in zip(expected,real)]
    tolerance=max(3, .015*max(real[2],real[3]))
    return {'declared':expected,'measured':real,'max_coordinate_delta_px':round(max(delta),3),
            'tolerance_px':round(tolerance,3),'significant':max(delta)>tolerance}

def build_object(obj,root,w,h,epsilon,trace_mode):
    oid=safe_id(obj['id'])
    geometry=obj.get('geometry',{})
    typ=geometry.get('type')
    if typ=='mask_png':
        d,bbox,subpaths,trace_info=geom_from_mask(local_path(root,geometry['file']),w,h,epsilon,trace_mode)
    elif typ=='svg_path':
        d=geometry.get('d','').strip()
        if not d or not re.match(r'^[Mm]',d): raise ValueError(f'{oid}: expected SVG path beginning M')
        if any(x in d.lower() for x in ('<','>','url(','javascript:')): raise ValueError(f'{oid}: invalid path string')
        bbox=obj.get('bbox')  # Legacy advisory value, never trusted for layout.
        trace_info={'trace_mode_used':'authored_svg_path'}
        subpaths=len(re.findall(r'[Mm]',d))
    else:
        raise ValueError(f'{oid}: invalid/missing geometry type {typ!r}')
    # Keep a semantic wrapper group so independently selectable objects are preserved.
    group=etree.Element(tag('g'),id=('obj_'+oid if oid[0].isdigit() else oid))
    group.set(f'{{{INK_NS}}}label',obj.get('name_zh',oid))
    group.set('data-name-en',obj.get('name_en',oid))
    if obj.get('transform'):
        if not isinstance(obj['transform'],str) or '<' in obj['transform'] or 'url(' in obj['transform']:
            raise ValueError(f'{oid}: unsafe transform')
        group.set('transform',obj['transform'])
    if obj.get('inferred_hidden'):group.set('data-inferred-hidden','true')
    etree.SubElement(group,tag('title')).text=obj.get('name_zh',oid)
    path=etree.SubElement(group,tag('path'),d=d)
    path.set('fill',color(obj.get('fill')))
    path.set('stroke',color(obj.get('stroke')))
    sw=float(obj.get('stroke_width',1))
    if sw<0 or not math.isfinite(sw):raise ValueError(f'{oid}: invalid stroke_width')
    path.set('stroke-width',f'{sw:g}')
    opacity=float(obj.get('opacity',1))
    if not 0<=opacity<=1 or not math.isfinite(opacity):raise ValueError(f'{oid}: invalid opacity')
    path.set('opacity',f'{opacity:g}')
    fill_rule=obj.get('fill_rule','evenodd' if typ=='mask_png' else 'nonzero')
    cap=obj.get('stroke_linecap','round')
    join=obj.get('stroke_linejoin','round')
    if fill_rule not in ('evenodd','nonzero'):raise ValueError(f'{oid}: invalid fill-rule')
    if cap not in ('round','butt','square'):raise ValueError(f'{oid}: invalid stroke-linecap')
    if join not in ('round','miter','bevel'):raise ValueError(f'{oid}: invalid stroke-linejoin')
    path.set('fill-rule',fill_rule)
    path.set('stroke-linecap',cap)
    path.set('stroke-linejoin',join)
    # variable-width SVG 1.1 representation: a visible editable filled
    # outline plus hidden centerline paths for subsequent editing. This is NOT
    # a native Illustrator Width Tool stroke. Profiles stay in the manifest.
    profiles=geometry.get('centerline_profiles',[])
    if profiles:
        if geometry.get('width_representation')!='filled_outline_plus_hidden_centerline':
            raise ValueError(f'{oid}: unsupported width representation')
        if color(obj.get('stroke'))!='none' or color(obj.get('fill'))=='none':
            raise ValueError(f'{oid}: variable-width representation requires a filled outline without stroke')
        if len(profiles)>2000:raise ValueError(f'{oid}: too many profiles')
        for i,prof in enumerate(profiles,1):
            guide=prof.get('centerline_d','')
            if not isinstance(guide,str) or not guide.startswith('M ') or len(guide)>400000 or any(x in guide.lower() for x in ('<','>','url(','javascript:')):
                raise ValueError(f'{oid}: invalid centerline SVG')
            widths=prof.get('width_samples_px',[])
            if not widths or len(widths)>200000 or not all(isinstance(z,(int,float)) and math.isfinite(z) and z>0 for z in widths):
                raise ValueError(f'{oid}: invalid width profile')
            hidden=etree.SubElement(group,tag('path'),d=guide,id=f'{oid}_guide_{i:03d}')
            hidden.set('display','none');hidden.set('fill','none')
            hidden.set('stroke',color(obj.get('fill')))
            hidden.set('data-centerline-guide','true')
            hidden.set('data-width-profile-index',str(i-1))
    measured_bbox=visible_bbox(group,w,h)
    discrepancy=bbox_disagreement(obj.get('bbox'),measured_bbox)
    info={'id':oid, 'bbox':measured_bbox,'declared_bbox_check':discrepancy,
        'trace_diagnostics':trace_info,'subpaths':subpaths,'geometry_type':typ,
        'fill':color(obj.get('fill')),'stroke':color(obj.get('stroke')),
        'semantic_name_zh':obj.get('name_zh',oid),
        'semantic_name_en':obj.get('name_en',oid),
        'variable_width':bool(profiles),
        'variable_width_repr':geometry.get('width_representation') if profiles else None,
        'variable_width_profile_count':len(profiles),
        'inferred_hidden':bool(obj.get('inferred_hidden',False))}
    return group,info

def root_svg(w,h):
    root=etree.Element(tag('svg'),nsmap=NSMAP)
    root.set('width',f'{w}px'); root.set('height',f'{h}px'); root.set('viewBox',f'0 0 {w} {h}')
    root.set('version','1.1')
    return root

def to_xml(root): return etree.tostring(root,encoding='utf-8',xml_declaration=True,pretty_print=True)

def render(root,filename,width=None):
    xml=to_xml(root)
    opts={'bytestring':xml,'write_to':str(filename)}
    if width:opts['output_width']=int(width)
    cairosvg.svg2png(**opts)

def component_fit(bbox,cx,cy,available_w,available_h,limit_upscale=2.0):
    x,y,bw,bh=map(float,bbox)
    s=min(available_w/max(bw,1),available_h/max(bh,1),limit_upscale)
    tx=cx-s*(x+bw/2)
    ty=cy-s*(y+bh/2)
    return f'translate({tx:.6f} {ty:.6f}) scale({s:.6f})'

def union_boxes(boxes):
    if not boxes:raise ValueError('Module with no objects')
    xs=[b[0] for b in boxes];ys=[b[1] for b in boxes]
    rs=[b[0]+b[2] for b in boxes];bs=[b[1]+b[3] for b in boxes]
    return [min(xs),min(ys),max(rs)-min(xs),max(bs)-min(ys)]

def create_breakdown(full_svg, manifest, elements, info_by_id, w,h):
    modules=manifest.get('modules') or [
        {'id':f'm_{layer["id"]}','name_zh':layer.get('name_zh',layer['id']),'layer_ids':[layer['id']]}
        for layer in manifest['layers']
    ]
    object_to_layer={o['id']:layer['id'] for layer in manifest['layers'] for o in layer['objects']}
    object_sequence=list(elements)
    parts=[('00','完整合成图',list(object_sequence),[0,0,w,h])]
    for idx,module in enumerate(modules,1):
        ids=set(module.get('object_ids') or [])
        ids |= {oid for oid in object_sequence if object_to_layer[oid] in module.get('layer_ids',[])}
        if not ids:raise ValueError(f'Module {module.get("id")}: no matching objects')
        selected=[oid for oid in object_sequence if oid in ids]
        bb=union_boxes([info_by_id[oid]['bbox'] for oid in selected])
        parts.append((f'{idx:02d}',module.get('name_zh',module.get('id',f'模块{idx}')),selected,bb))
    ncols=min(4,max(2,math.ceil(math.sqrt(len(parts)))))
    nrows=math.ceil(len(parts)/ncols)
    pw,ph=420,360
    margin=30; gap=20
    BW=margin*2+ncols*pw+(ncols-1)*gap
    BH=margin*2+nrows*ph+(nrows-1)*gap
    root=root_svg(BW,BH)
    etree.SubElement(root,tag('rect'),x='0',y='0',width=str(BW),height=str(BH),fill='#F8FAFD')
    for i,(number,title,ids,bbox) in enumerate(parts):
        row,col=divmod(i,ncols)
        left=margin+col*(pw+gap)
        top=margin+row*(ph+gap)
        panel=etree.SubElement(root,tag('g'),id=f'panel_{number}')
        etree.SubElement(panel,tag('rect'),x=str(left),y=str(top),width=str(pw),height=str(ph),rx='14',fill='#FFFFFF',stroke='#D9E2EE',**{'stroke-width':'1.4'})
        txt=etree.SubElement(panel,tag('text'),x=str(left+18),y=str(top+35),fill='#27384B',**{'font-family':'Noto Sans CJK SC, sans-serif','font-size':'19','font-weight':'600'})
        txt.text=f'{number}  {title}'
        bx,by,bw,bh=left+20,top+64,pw-40,ph-86
        transform=component_fit(bbox,bx+bw/2,by+bh/2,bw-8,bh-8)
        content=etree.SubElement(panel,tag('g'),transform=transform)
        for oid in ids:
            g=copy.deepcopy(elements[oid])
            g.set('id',f'panel_{number}_{oid}')
            content.append(g)
    return root,parts

def validate_svg(svg_path, expected_objects):
    tree=etree.parse(str(svg_path));root=tree.getroot()
    ids=[e.get('id') for e in root.iter() if e.get('id')]
    bad=[e for e in root.iter() if etree.QName(e).localname in ('image','foreignObject')]
    paths=[e for e in root.iter() if etree.QName(e).localname=='path']
    return {'svg_xml_valid':True,'no_raster_embeds':len(bad)==0,
            'unique_svg_ids':len(ids)==len(set(ids)),
            'path_element_count':len(paths),
            'at_least_one_path_per_object':len(paths)>=expected_objects}

def write_palette(out,counts):
    with (out/'05_Color_Palette.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['HEX','Usage','Object_Count'])
        for (col,role),count in sorted(counts.items(),key=lambda kv:(kv[0][0],kv[0][1])):
            writer.writerow([col,role,count])

def compare_preview(source_path, preview_path, out):
    with Image.open(source_path) as src, Image.open(preview_path) as pred:
        # Display comparison is on white because transparent RGB is otherwise undefined.
        def white_bg(im):
            bg=Image.new('RGBA',im.size,'white')
            bg.alpha_composite(im.convert('RGBA'))
            return bg.convert('RGB')
        s=white_bg(src);r=white_bg(pred)
        if s.size!=r.size: raise ValueError(f'Render dimensions {r.size} != source {s.size}')
        sa=np.asarray(s,dtype=np.int16);ra=np.asarray(r,dtype=np.int16)
        diff=np.abs(sa-ra).astype(np.uint8)
        alpha_mae=float(np.abs(np.asarray(src.convert('RGBA').getchannel('A'),dtype=np.int16)-np.asarray(pred.convert('RGBA').getchannel('A'),dtype=np.int16)).mean())
        mae=float(diff.astype(np.float64).mean())
        npix=float(np.mean(np.any(diff>15,axis=-1)))
        # alpha detects transparent-vs-white mismatch hidden by white compositing.
        s_alpha=np.asarray(src.convert('RGBA').getchannel('A'))
        r_alpha=np.asarray(pred.convert('RGBA').getchannel('A'))
        alpha_mismatch=float(np.mean(np.abs(s_alpha.astype('int16')-r_alpha.astype('int16'))>15))
        # Edge agreement: measure distance from both Canny edge maps (tolerates 1px raster AA).
        gray_s=cv2.cvtColor(np.asarray(s),cv2.COLOR_RGB2GRAY)
        gray_r=cv2.cvtColor(np.asarray(r),cv2.COLOR_RGB2GRAY)
        edge_s=cv2.Canny(gray_s,60,120)>0;edge_r=cv2.Canny(gray_r,60,120)>0
        dist_s=cv2.distanceTransform((~edge_s).astype('uint8'),cv2.DIST_L2,3)
        dist_r=cv2.distanceTransform((~edge_r).astype('uint8'),cv2.DIST_L2,3)
        miss_s=float(np.mean(dist_r[edge_s]>2.0)) if edge_s.any() else (0.0 if not edge_r.any() else 1.0)
        miss_r=float(np.mean(dist_s[edge_r]>2.0)) if edge_r.any() else (0.0 if not edge_s.any() else 1.0)
        edge_mismatch=(miss_s+miss_r)/2
        overlay=Image.blend(s,r,0.5)
        overlay.save(out/'09_Overlay_Comparison.png')
        # Amplified difference; not actual absolute colors.
        Image.fromarray(np.clip(diff.astype(np.int16)*4,0,255).astype(np.uint8),'RGB').save(out/'10_Difference_Map.png')
        return {'mae_rgb_0_255':round(mae,4), 'mae_alpha_0_255':round(alpha_mae,4), 'fraction_of_pixels_with_channel_difference_gt15':round(npix,6),
            'fraction_of_alpha_pixels_difference_gt15':round(alpha_mismatch,6),
            'fraction_of_edges_farther_than_2px':round(edge_mismatch,6),
            'comparison_composited_on':'white',
            'interpretation':'Diagnostics only: anti-aliasing, PNG/JPEG color management and important tiny geometry can defeat naive threshold judgments.'}

def outline_stage(full,w,h):
    """Review projection, not evidence that manual tracing occurred first."""
    out=copy.deepcopy(full)
    for path in out.xpath('//*[local-name()="path"]'):
        stroke=path.get('stroke','none')
        fill=path.get('fill','none')
        if stroke=='none':path.set('stroke',fill if fill!='none' else '#64748B')
        path.set('fill','none')
        path.set('stroke-width',str(max(0.8,float(path.get('stroke-width','1')))))
        path.set('opacity','1')
    return out


def review_fidelity(m,qa):
    defaults={'max_mae_rgb':12.0,'max_mae_alpha':12.0,
              'max_changed_pixel_fraction':.12,'max_alpha_changed_fraction':.08,
              'max_edge_mismatch_fraction':.24}
    limits={**defaults,**qa.get('fidelity_thresholds',{})}
    metrics={'max_mae_rgb':m['mae_rgb_0_255'], 'max_mae_alpha':m['mae_alpha_0_255'],
             'max_changed_pixel_fraction':m['fraction_of_pixels_with_channel_difference_gt15'],
             'max_alpha_changed_fraction':m['fraction_of_alpha_pixels_difference_gt15'],
             'max_edge_mismatch_fraction':m['fraction_of_edges_farther_than_2px']}
    for k,v in limits.items():
        if not isinstance(v,(int,float)) or not math.isfinite(v) or v<0:
            raise ValueError(f'Invalid fidelity QA limit {k}: {v}')
    failing=[{'metric':k,'observed':v,'limit':limits[k]} for k,v in metrics.items() if v>limits[k]]
    return limits,failing


def check_semantic_inventory(manifest, object_ids):
    qa=manifest.get('qa',{})
    required=set(qa.get('required_object_ids',[]))
    missing=required-set(object_ids)
    if missing:raise ValueError(f'Missing required independently editable objects: {sorted(missing)}')
    counts={}
    for prefix,count in qa.get('expected_object_counts_by_prefix',{}).items():
        actual=sum(oid.startswith(prefix) for oid in object_ids)
        counts[prefix]={'expected':int(count),'actual':actual}
        if actual!=int(count):
            raise ValueError(f'Wrong number of objects beginning {prefix!r}: expected {count}, got {actual}')
    return counts


def check_key_regions(source_path,preview_path,qa,out):
    """Clinical ROIs prevent small neural/electrode errors from hiding in global MAE."""
    regions=qa.get('key_regions',[])
    results=[]; failures=[]
    with Image.open(source_path) as original, Image.open(preview_path) as predicted:
        s=original.convert('RGBA');r=predicted.convert('RGBA')
        for idx,reg in enumerate(regions):
            name=reg.get('name',f'ROI_{idx+1}')
            bounds=reg.get('bbox')
            if not isinstance(bounds,list) or len(bounds)!=4:raise ValueError(f'{name}: ROI bbox [x,y,w,h] required')
            x,y,w,h=map(int,bounds)
            if w<=0 or h<=0 or x<0 or y<0 or x+w>s.width or y+h>s.height:
                raise ValueError(f'{name}: ROI is outside canvas')
            src=s.crop((x,y,x+w,y+h));pred=r.crop((x,y,x+w,y+h))
            def white(im):
                bg=Image.new('RGBA',im.size,'white');bg.alpha_composite(im)
                return np.asarray(bg.convert('RGB'),dtype=np.int16)
            delta=np.abs(white(src)-white(pred));mae=float(delta.mean())
            changed=float(np.mean(np.any(delta>15,axis=2)))
            alpha_delta=np.abs(np.asarray(src.getchannel('A'),dtype=np.int16)-np.asarray(pred.getchannel('A'),dtype=np.int16))
            alpha_mae=float(alpha_delta.mean())
            row={'name':name,'bbox':[x,y,w,h],'mae_rgb_0_255':round(mae,4),
                 'changed_pixel_fraction':round(changed,5),'mae_alpha_0_255':round(alpha_mae,4)}
            thresh={'max_mae_rgb':float(reg.get('max_mae_rgb',8.0)),
                    'max_changed_pixel_fraction':float(reg.get('max_changed_pixel_fraction',.10)),
                    'max_mae_alpha':float(reg.get('max_mae_alpha',8.0))}
            row['thresholds']=thresh
            checks=[('mae_rgb_0_255','max_mae_rgb'),('changed_pixel_fraction','max_changed_pixel_fraction'),
                    ('mae_alpha_0_255','max_mae_alpha')]
            row['failures']=[{'metric':metric,'observed':row[metric],'limit':thresh[key]}
                             for metric,key in checks if row[metric]>thresh[key]]
            if row['failures']:failures.append({'region':name,'failures':row['failures']})
            results.append(row)
            # Local visual check, shown side-by-side for manual medical verification.
            preview=Image.new('RGB',(w*2,h),'white')
            preview.paste(Image.fromarray(white(src).astype('uint8')), (0,0))
            preview.paste(Image.fromarray(white(pred).astype('uint8')), (w,0))
            preview.save(out/f'ROI_{idx+1:02d}_Comparison.png')
    return results,failures


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--epsilon',type=float,default=0.0,help='mask contour simplification in source pixels; 0 means no simplification')
    parser.add_argument('--trace-mode',choices=['polygon','adaptive-bezier'],default='polygon',
                        help='adaptive-bezier is accepted only when its outline matches polygon baseline')
    parser.add_argument('--hires-scale',type=int,default=1,
                        help='Additional editable SVG raster preview upscale (2 or 3 recommended for review)')
    parser.add_argument('--require-line-quality-review',action='store_true',
                        help='Require current source/SVG-bound 4x per-object visual review before final ZIP')
    parser.add_argument('--include-source-project',action='store_true',
                        help='Pack original source and editable object masks for reproducibility (may contain private images)')
    parser.add_argument('--allow-draft',action='store_true',
                        help='Package even when fidelity checks fail; report FAIL and never claim verified')
    parser.add_argument('--analyze-occlusion',action='store_true',
                        help='Analyze visible object overlaps even when manifest has no occlusion settings')
    a=parser.parse_args()
    if a.epsilon<0 or not math.isfinite(a.epsilon):parser.error('--epsilon must be finite and nonnegative')
    if not 1<=a.hires_scale<=4:parser.error('--hires-scale must be 1..4')
    proj=a.project.resolve(strict=True)
    manifest=json.loads(local_path(proj,'manifest.json').read_text('utf-8'))
    if manifest.get('schema_version')!='1.0':raise ValueError('schema_version must be 1.0')
    source=local_path(proj,manifest['source_image'])
    original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    if manifest.get('source_sha256') and manifest['source_sha256']!=original_hash:
        raise ValueError('Source SHA256 does not match manifest. Stop before exporting.')
    with Image.open(source) as im:source_w,source_h=im.size
    c=manifest.get('canvas',{})
    w,h=int(c.get('width',0)),int(c.get('height',0))
    if (w,h)!=(source_w,source_h):raise ValueError(f'Canvas {(w,h)} must match source {(source_w,source_h)}')
    layers=manifest.get('layers')
    if not layers or not any(l.get('objects') for l in layers):
        raise ValueError('No traced semantic objects: populate layers / objects before exporting; init_project alone is not vectorization.')
    full=root_svg(w,h)
    elements={};info_by_id={};global_ids=set();counts=Counter();layers_out=[]
    for layer in layers:
        lid=safe_id(layer['id'])
        if lid in global_ids:raise ValueError(f'Duplicate layer ID {lid}')
        global_ids.add(lid)
        lg=etree.SubElement(full,tag('g'),id=('layer_'+lid if lid[0].isdigit() else lid))
        lg.set(f'{{{INK_NS}}}groupmode','layer')
        lg.set(f'{{{INK_NS}}}label',layer.get('name_zh',lid))
        lg.set('data-name-en',layer.get('name_en',lid))
        layer_info={'id':lid,'name_zh':layer.get('name_zh',lid),'name_en':layer.get('name_en',lid),'objects':[]}
        for obj in layer.get('objects',[]):
            if obj.get('id') in global_ids:raise ValueError(f'Duplicate layer/object ID {obj["id"]}')
            group,info=build_object(obj,proj,w,h,a.epsilon,a.trace_mode)
            global_ids.add(obj['id']);lg.append(group)
            elements[obj['id']]=group;info_by_id[obj['id']]=info
            layer_info['objects'].append(info)
            if info['fill']!='none':counts[(info['fill'],'fill')]+=1
            if info['stroke']!='none':counts[(info['stroke'],'stroke')]+=1
        layers_out.append(layer_info)
    if not elements:raise ValueError('No objects')
    inventory_check=check_semantic_inventory(manifest,elements)
    from editable_svg import inspect_editability, linework
    editing_report=inspect_editability(elements,manifest.get('qa',{}))
    out=a.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError(f'Output directory must be empty to avoid stale/misleading assets: {out}; use a fresh directory')
    out.mkdir(parents=True,exist_ok=True)
    occlusion_report=None;occlusion_runs=[];occlusion_failures=[]
    if a.analyze_occlusion or manifest.get('occlusion') is not None:
        from occlusion_layers import analyze_scene, resolve_stack, form_layer_groups
        occlusion_report=analyze_scene(manifest,elements,source,w,h,render_assets_dir=out)
        ordered,_,occlusion_dag=resolve_stack(manifest)
        # Commit a new stack of *real* SVG layer groups. If the same semantic layer
        # becomes non-contiguous, split its display run instead of destroying
        # independently selectable objects or changing their semantic source ID.
        for child in list(full):full.remove(child)
        occlusion_runs=form_layer_groups(manifest,elements,ordered,full)
        elements={oid:elements[oid] for oid in ordered}
        (out/'17_Occlusion_Report.json').write_text(
            json.dumps(occlusion_report,ensure_ascii=False,indent=2),encoding='utf-8')
        if manifest.get('qa',{}).get('require_resolved_occlusions',False):
            unresolved=[row for row in occlusion_report['contacts']
                        if row['overlap_pixels']>=12 and not row['ordering_resolved_by_graph']]
            if unresolved:
                occlusion_failures.append({'reason':'unresolved_visible_overlap',
                    'pairs':[r['pair'] for r in unresolved]})
        import networkx as nx
        conflicts=[]
        for row in occlusion_report['contacts']:
            if row['status']=='strong_appearance_candidate' and row['ordering_resolved_by_graph']:
                if nx.has_path(occlusion_dag,row['suggested_front'],row['suggested_behind']):
                    conflicts.append(row['pair'])
        if conflicts:
            occlusion_failures.append({'reason':'explicit_order_conflicts_with_strong_visible_color_evidence',
                'pairs':conflicts})
    # reviewed OCR: add native editable SVG text, never raster-embed recognized words.
    from text_recognition import append_approved_text
    reviewed_text=append_approved_text(full,proj/'text_review.json',original_hash,w,h)
    paths={
        'full':out/'01_Full_Illustration.svg','breakdown':out/'02_Layer_Breakdown.svg',
        'full_preview':out/'03_Full_Preview.png','breakdown_preview':out/'04_Breakdown_Preview.png'
    }
    paths['full'].write_bytes(to_xml(full))
    editable_lines=linework(full)
    (out/'24_Editable_Linework.svg').write_bytes(to_xml(editable_lines))
    render(editable_lines,out/'24_Editable_Linework.png')
    (out/'25_Editability_Report.json').write_text(json.dumps(editing_report,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'11_Outline_Inspection.svg').write_bytes(to_xml(outline_stage(full,w,h)))
    # Reviewed OCR is its own *editable* breakdown module, not only text
    # painted on the combined SVG. Keep the source geometry count unchanged.
    breakdown_manifest=copy.deepcopy(manifest)
    breakdown_elements=dict(elements)
    breakdown_info=dict(info_by_id)
    if reviewed_text:
        text_objects=[]
        for item in full.xpath('//*[local-name()="g" and @data-ocr-reviewed="true"]'):
            tid=item.get('id')
            if tid in breakdown_elements:raise ValueError(f'Duplicate OCR/geometry identifier: {tid}')
            breakdown_elements[tid]=item
            breakdown_info[tid]={'bbox':visible_bbox(item,w,h)}
            text_objects.append({'id':tid})
        text_layer='99_Reviewed_Text'
        breakdown_manifest['layers'].append({'id':text_layer,'name_zh':'已核对文字',
                                             'name_en':'Reviewed editable OCR text','objects':text_objects})
        if breakdown_manifest.get('modules'):
            breakdown_manifest['modules'].append({'id':'module_reviewed_text','name_zh':'可编辑文字',
                         'layer_ids':[text_layer]})
    breakdown,parts=create_breakdown(full,breakdown_manifest,breakdown_elements,breakdown_info,w,h)
    paths['breakdown'].write_bytes(to_xml(breakdown))
    render(full,paths['full_preview'])
    render(breakdown,paths['breakdown_preview'])
    if a.hires_scale>1:
        render(full,out/'13_HiRes_Preview.png',width=w*a.hires_scale)
    from line_quality import inspect_line_quality
    line_required=a.require_line_quality_review or manifest.get('qa',{}).get('require_line_quality_review',False) is True
    if line_required and a.hires_scale<4:
        render(full,out/'13_HiRes_Preview.png',width=w*4)
    line_report=inspect_line_quality(paths['full'].read_bytes(),elements,original_hash,
                                    proj/'line_quality_review.json',line_required)
    (out/'26_Line_Quality_Report.json').write_text(json.dumps(line_report,ensure_ascii=False,indent=2),encoding='utf-8')
    write_palette(out,counts)
    result_manifest={'schema_version':'1.0','source':manifest['source_image'],
        'source_sha256':original_hash,'canvas':{'width':w,'height':h},
        'layers':layers_out,'reviewed_editable_text':reviewed_text,'render_stack_layer_runs':occlusion_runs,
        'occlusion':occlusion_report,'original_project_manifest':manifest,'modules':[
            {'number':number,'name_zh':label,'object_ids':ids,'bbox':box}
            for number,label,ids,box in parts
        ],'qa_metadata':manifest.get('qa',{})}
    (out/'06_Layer_Manifest.json').write_text(json.dumps(result_manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    variable_profiles={o['id']:o['geometry']['centerline_profiles']
        for l in layers for o in l['objects'] if o.get('geometry',{}).get('centerline_profiles')}
    if variable_profiles:
        (out/'14_Variable_Width_Profiles.json').write_text(
            json.dumps({'representation':'editable_filled_outline_plus_hidden_path',
                        'native_illustrator_width_profile':False,
                        'profiles':variable_profiles},ensure_ascii=False,indent=2),encoding='utf-8')
    original_comp=compare_preview(source,paths['full_preview'],out)
    qa=manifest.get('qa',{})
    limits,fidelity_failures=review_fidelity(original_comp,qa)
    region_results,region_failures=check_key_regions(source,paths['full_preview'],qa,out)
    if region_failures:
        fidelity_failures.extend({'metric':'key_region','details':item} for item in region_failures)
    bbox_issues=[{'object_id':i['id'],**i['declared_bbox_check']} for i in info_by_id.values()
                 if i['declared_bbox_check'] is not None and i['declared_bbox_check']['significant']]
    geometric_issues=list(occlusion_failures)
    fidelity_status='failed' if fidelity_failures else 'within_numeric_limits_requires_review'
    seg_report_path=proj/'instance_segmentation_report.json'
    seg_report=json.loads(seg_report_path.read_text('utf-8')) if seg_report_path.is_file() else None
    sam2_report_path=proj/'sam2_segmentation_report.json'
    sam2_report=json.loads(sam2_report_path.read_text('utf-8')) if sam2_report_path.is_file() else None
    v23_reports=[]
    for pattern in ('subpixel_*_report.json','variable_width_*_report.json'):
        for fp in sorted(proj.glob(pattern)):
            record=json.loads(fp.read_text('utf-8'))
            v23_reports.append({'file':fp.name,'object_id':record.get('id'),
                'passed':record.get('passed',record.get('qa',{}).get('passed')),
                'selected':record.get('selected'),
                'mask_iou':record.get('qa',{}).get('mask_iou'),
                'review_required':True})
    skeleton_reports=[]
    for tracepath in sorted(proj.glob('centerline_*_report.json')):
        tr=json.loads(tracepath.read_text('utf-8'))
        skeleton_reports.append({'id':tr.get('id'),'mask_source':tr.get('mask_source'),
            'iou':tr.get('qa',{}).get('iou'),'segments':tr.get('qa',{}).get('segments'),
            'junction_count':tr.get('qa',{}).get('junction_count'),
            'review_required':tr.get('qa',{}).get('review_required',True)})
    report={'result':'exported_draft_checks_failed' if fidelity_failures or geometric_issues or editing_report['failures'] else 'exported_svg_needs_review','source_sha256':original_hash,'canvas':{'width':w,'height':h},
        'guided_segmentation_summary':({'instance_count':seg_report.get('instance_count'),
            'overlap_pairs':seg_report.get('overlap_pairs'),'all_instances_review_required':True} if seg_report else None),
        'sam2_segmentation_summary':({'method':sam2_report.get('method'),
            'instance_count':sam2_report.get('instance_count'),
            'actual_sam2_inference':sam2_report.get('actual_sam2_inference'),
            'model_source':sam2_report.get('model_source'),
            'overlap_pairs':sam2_report.get('overlap_pairs'),
            'all_instances_review_required':True} if sam2_report else None),
        'centerline_trace_summaries':skeleton_reports,
        'precision_v23_summaries':v23_reports,
        'occlusion_v24_summary':({'candidate_count':occlusion_report['candidate_count'],
            'unresolved_overlap_count':occlusion_report['unresolved_overlap_count'],
            'explicit_constraint_count':len(occlusion_report['explicit_constraints']),
            'bottom_to_top_order':occlusion_report['bottom_to_top_order'],
            'svg_layer_run_count':len(occlusion_runs),
            'review_required':occlusion_report['review_required'],
            'no_hidden_anatomy_generated':True} if occlusion_report else None),
        'variable_width_object_count':len(variable_profiles),
        'reviewed_editable_text_count':len(reviewed_text),
        'reviewed_editable_text':reviewed_text,
        'module_count_excluding_composite':len(parts)-1,'layer_count':len(layers),
        'actual_svg_layer_count':len(occlusion_runs) if occlusion_report else len(layers),
        'object_count':len(elements),'object_id_independent':len(elements)==len(set(elements)),
        'number_inferred_hidden':sum(i['inferred_hidden'] for i in info_by_id.values()),
        'full_svg':validate_svg(paths['full'],len(elements)),
        'breakdown_svg':validate_svg(paths['breakdown'],len(elements)),
        'image_comparison':original_comp,
        'fidelity_status':fidelity_status,
        'fidelity_thresholds':limits,
        'fidelity_failures':fidelity_failures,
        'declared_bbox_mismatches':bbox_issues,
        'geometry_failures':geometric_issues,
        'key_region_results':region_results,
        'key_region_failures':region_failures,
        'semantic_inventory_verified':inventory_check,
        'semantic_inventory_declared':bool(qa.get('required_object_ids') or qa.get('expected_object_counts_by_prefix')),
        'editability':editing_report,
        'line_quality':line_report,
        'quality_gates_passed':not fidelity_failures and not geometric_issues and editing_report['quality_gates_passed'] and line_report['quality_gates_passed'],
        'release_ready':False,  # Always requires clinician/illustrator inspection and AI verification.
        'trace_mode':a.trace_mode,
        'illustrator_native_verified':False,
        'notes':['Compiles curated object masks or paths. No automatic anatomy/semantic extraction performed.',
                 'SVG groups may need promotion to native Illustrator layers after import.',
                 'Mask-traced outlines use polygon unless adaptive-bezier passes geometry checks.',
                 'Outline inspection SVG shows outlines of final objects; not proof of a completed drawing phase.'],
        'unresolved_details':manifest.get('qa',{}).get('unresolved_details',[]),
        'requires_manual_visual_and_illustrator_inspection':True}
    (out/'quality_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not all(v is True for k,v in report['full_svg'].items() if isinstance(v,bool)):
        raise ValueError('SVG quality gates failed')
    if (fidelity_failures or geometric_issues or editing_report['failures'] or line_report['failures']) and not a.allow_draft:
        print(json.dumps({'error':'Fidelity/occlusion/editing/line-review gates FAILED; diagnostics retained, ZIP withheld.',
                          'fidelity_failures':fidelity_failures,
                          'occlusion_failures':geometric_issues,'editability_failures':editing_report['failures'],
                          'line_quality_failures':line_report['failures'],'out':str(out)},ensure_ascii=False,indent=2),file=sys.stderr)
        raise SystemExit(2)
    if a.include_source_project:
        # Opt-in: source images may contain patient information. No automatic sharing.
        with zipfile.ZipFile(out/'12_Editable_Project.zip','w',compression=zipfile.ZIP_DEFLATED) as project_zip:
            sources=[local_path(proj,'manifest.json'),source]
            original_svg=proj/'original_source.svg'
            if original_svg.is_file():sources.append(original_svg)
            for layer in layers:
                for object_spec in layer.get('objects',[]):
                    g=object_spec.get('geometry',{})
                    if g.get('type')=='mask_png':sources.append(local_path(proj,g['file']))
            # Preserve tracing provenance and masks converted to centerline paths.
            # This is explicitly OPT-IN: source images may contain patient data.
            for f in list((proj/'masks').glob('*.png')) + list(proj.glob('centerline_*_report.json')):
                if f.is_file():sources.append(f)
            for f in sorted((proj/'sam2_previews').glob('*.png')):
                if f.is_file():sources.append(f)
            for f in list(proj.glob('subpixel_*_report.json'))+list(proj.glob('variable_width_*_report.json')):
                if f.is_file():sources.append(f)
            for name in ('occlusion_analysis_report.json', 'instance_annotations.json','instance_segmentation_report.json',
                         'sam2_annotations.json','sam2_segmentation_report.json','source_inspection.json',
                         'text_review.json','text_review.png','completion_annotations.json','line_quality_review.json'):
                f=proj/name
                if f.is_file():sources.append(f)
            for f in sorted(set(sources)):
                resolved=f.resolve()
                if not resolved.is_relative_to(proj):raise ValueError('Symlink escapes project, refusing to package')
                rel=f.relative_to(proj)
                project_zip.write(f,rel.as_posix())
    # modal/amodal candidates never alter the original output.
    # By default, generate separate isolated amodal objects and review report.
    from amodal_completion import generate as generate_amodal
    completion_file=proj/'completion_annotations.json'
    amodal_report=generate_amodal(proj,out,local_path(proj,completion_file.name) if completion_file.exists() else None,elements=elements)
    report['amodal_completion_v32']={'object_count':amodal_report['total_objects'],
             'inferred_requires_manual_review':True,'modal_source_unchanged':True}
    (out/'quality_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    allowed={'26_Line_Quality_Report.json','24_Editable_Linework.svg','24_Editable_Linework.png','25_Editability_Report.json','18_Modal_Illustration.svg','19_Amodal_Isolated_Objects.svg',
             '19_Amodal_Isolated_Objects.png','20_Completion_Report.json','21_Completion_Review.png',
             '22_Unapproved_Completion_Candidates.svg','22_Unapproved_Completion_Candidates.png',
             '23_Amodal_Approval_Review.svg','23_Amodal_Approval_Review.png',
             '15_Occlusion_Review.png','16_Occlusion_Stack.svg','17_Occlusion_Report.json',
             '14_Variable_Width_Profiles.json','12_Editable_Project.zip','13_HiRes_Preview.png','11_Outline_Inspection.svg','01_Full_Illustration.svg','02_Layer_Breakdown.svg',
        '03_Full_Preview.png','04_Breakdown_Preview.png',
        '05_Color_Palette.csv','06_Layer_Manifest.json',
        '09_Overlay_Comparison.png','10_Difference_Map.png','quality_report.json'}
    with zipfile.ZipFile(out/'08_All_Files.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.iterdir()):
            if f.is_file() and (f.name in allowed or f.name.startswith(('18_inferred_','22_proposal_')) and f.name.endswith('.png') or f.name.startswith('ROI_') and f.name.endswith('_Comparison.png')):z.write(f,f.name)
    print(json.dumps({'out':str(out),'objects':len(elements),'layers':len(layers),
       'modules':len(parts)-1,'image_mae':original_comp['mae_rgb_0_255'],
       'ai_created':False,'fidelity_status':fidelity_status,
       'bbox_warnings':len(bbox_issues),
       'occlusion_constraints':len(occlusion_report['explicit_constraints']) if occlusion_report else 0},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
