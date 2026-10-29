#!/usr/bin/env python3
"""conservative visible-overlap analysis and explicit layer ordering.

Never extrapolates hidden anatomy. An apparent overlap is only appearance evidence;
constraints must be confirmed or explicitly accepted by the operator.
"""
import argparse
import copy
import io
import json
import math
from collections import defaultdict
from pathlib import Path

import cairosvg
import cv2
import networkx as nx
import numpy as np
from PIL import Image, ImageDraw
from lxml import etree

SVG_NS='http://www.w3.org/2000/svg'
INK_NS='http://www.inkscape.org/namespaces/inkscape'

def _objects(manifest):
    return [(layer, obj) for layer in manifest['layers'] for obj in layer.get('objects', [])]

def _validate_constraints(manifest, ids):
    edges=[];seen=set()
    conf=manifest.get('occlusion',{})
    if not isinstance(conf,dict):raise ValueError('occlusion must be an object')
    for row in conf.get('constraints',[]):
        back=row.get('behind');front=row.get('front')
        if back not in ids or front not in ids or back==front:
            raise ValueError(f'Invalid occlusion constraint {row}: unknown object, or self-reference')
        if (back,front) in seen:raise ValueError(f'Duplicate occlusion constraint: {back} behind {front}')
        if not isinstance(row.get('source'),str) or not row['source']:
            raise ValueError('Every constraint needs a nonempty source, e.g. user_confirmed')
        seen.add((back,front));edges.append((back,front,row))
    return edges

def resolve_stack(manifest, accepted_candidates=None):
    """Return stable, deterministic bottom-to-top sequence and explicit DAG edges."""
    ids=[obj['id'] for _,obj in _objects(manifest)]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate object identifiers')
    order={k:i for i,k in enumerate(ids)}
    g=nx.DiGraph();g.add_nodes_from(ids)
    constraints=_validate_constraints(manifest,set(ids))
    for back,front,_ in constraints:g.add_edge(back,front)
    for candidate in accepted_candidates or []:
        back,front=candidate['behind'],candidate['front']
        if back not in order or front not in order:raise ValueError('Unknown inferred order')
        g.add_edge(back,front)
    if not nx.is_directed_acyclic_graph(g):
        cycle=nx.find_cycle(g)
        raise ValueError('Occlusion cycle: '+ ' -> '.join(f'{a}:{b}' for a,b in cycle))
    sorted_ids=list(nx.lexicographical_topological_sort(g,key=lambda oid:order[oid]))
    return sorted_ids, [{'behind':u,'front':v,'source':(
        next((r['source'] for b,f,r in constraints if b==u and f==v),'appearance_candidate_accepted'))}
        for u,v in g.edges()],g

def _render_element(group, w, h):
    svg=etree.Element('{%s}svg'%SVG_NS,nsmap={None:SVG_NS})
    svg.set('width',str(w));svg.set('height',str(h));svg.set('viewBox',f'0 0 {w} {h}')
    svg.append(copy.deepcopy(group))
    arr=np.array(Image.open(io.BytesIO(cairosvg.svg2png(bytestring=etree.tostring(svg)))).convert('RGBA'))
    return arr

def _valid_sample(source, a, b, multiplicity):
    # Erode 1px to reject outline anti-aliasing. Require opaque structures;
    # semitransparent compositing is ambiguous without the complete scene.
    am=(a[:,:,3]>=250).astype('uint8');bm=(b[:,:,3]>=250).astype('uint8')
    kernel=np.ones((3,3),np.uint8)
    core=(cv2.erode(am,kernel)>0)&(cv2.erode(bm,kernel)>0)
    return core & (source[:,:,3]>=250) & (multiplicity==2)

def _background_like(array,w,h):
    # Any almost-full-canvas shape excluded from appearance candidate detection;
    # its order can be specified explicitly.
    return np.count_nonzero(array[:,:,3]>240)>=.92*w*h

def _score_pair(source, a, b, sample, back_name, front_name, min_pixels, min_gap):
    n=int(sample.sum())
    if n<min_pixels:
        return {'pair':[back_name,front_name],'status':'insufficient_unoccluded_overlap','sample_pixels':n}
    src=source[sample,:3].astype('float32')
    pa=a[sample,:3].astype('float32'); pb=b[sample,:3].astype('float32')
    delta_a=np.mean(abs(src-pa),axis=1)
    delta_b=np.mean(abs(src-pb),axis=1)
    color_gap=np.mean(abs(pa-pb),axis=1)
    mean_gap=float(np.median(color_gap))
    err_a=float(np.median(delta_a));err_b=float(np.median(delta_b))
    if err_a<err_b:
        top=back_name; behind=front_name; best=delta_a; runner=delta_b
    else:
        top=front_name; behind=back_name; best=delta_b; runner=delta_a
    win_ratio=float(np.mean(best+8<runner))
    # Insist on large color separation and excellent source fidelity; objects
    # that coincide but are partially transparent/unmodeled are review-only.
    confident=(mean_gap>=min_gap and float(np.median(best))<=12
               and float(np.median(runner-best))>=min_gap*.65 and win_ratio>=.90)
    return {'pair':[back_name,front_name],
            'status':'strong_appearance_candidate' if confident else 'ambiguous_requires_review',
            'sample_pixels':n,'median_color_separation':round(mean_gap,2),
            'median_error_for_first':round(err_a,2),'median_error_for_second':round(err_b,2),
            'winner_fraction':round(win_ratio,4),
            'suggested_behind':behind if confident else None,
            'suggested_front':top if confident else None,
            'interpretation':'Only local visible appearance, not proof of hidden continuity.'}

def analyze_scene(manifest,elements,source_path,w,h,min_pixels=12,min_color_gap=25,
                  contact_radius=3, render_assets_dir=None):
    """Input already-vectorized independent object groups; no hidden geometry creation."""
    order,edges,graph=resolve_stack(manifest)
    with Image.open(source_path) as image:
        if image.size!=(w,h):raise ValueError('Source image and canvas differ')
        src=np.array(image.convert('RGBA'))
    groups={oid:_render_element(elements[oid],w,h) for oid in elements}
    names=list(elements)
    background={k for k,g in groups.items() if _background_like(g,w,h)}
    skip=set(manifest.get('occlusion',{}).get('exclude_from_inference',[]))|background
    unknown=skip-set(elements)
    if unknown:raise ValueError(f'Unknown IDs in exclude_from_inference: {sorted(unknown)}')
    eligible=[name for name in names if name not in skip]
    masks={name:(groups[name][:,:,3]>=250) for name in eligible}
    bounds={}
    for name,ma in masks.items():
        ys,xs=np.nonzero(ma)
        bounds[name]=(int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1) if len(xs) else None
    multiplicity=np.zeros((h,w),dtype=np.uint16)
    for mask in masks.values():multiplicity+=mask.astype(np.uint16)
    min_pixels=int(min_pixels);min_color_gap=float(min_color_gap)
    if min_pixels<1 or min_color_gap<=0 or contact_radius<0:raise ValueError('Invalid occlusion thresholds')
    edge_pairs={(behind,front) for behind,front,_ in _validate_constraints(manifest,set(names))}
    contacts=[];candidates=[];unresolved=[];overlap_total=0
    dilation=np.ones((2*int(contact_radius)+1,)*2,np.uint8) if contact_radius else None
    for i,first in enumerate(eligible):
        ma=masks[first]
        if not np.any(ma):continue
        for second in eligible[i+1:]:
            ba,bb=bounds[first],bounds[second]
            if ba is None or bb is None:continue
            rad=contact_radius
            if ba[2]+rad<bb[0] or bb[2]+rad<ba[0] or ba[3]+rad<bb[1] or bb[3]+rad<ba[1]:
                continue  # Fast bbox rejection avoids all-canvas pairwise arrays.
            mb=masks[second]
            if not np.any(mb):continue
            count=int(np.count_nonzero(ma&mb))
            distance_contact=False
            if count==0 and dilation is not None:
                distance_contact=bool(np.any((cv2.dilate(ma.astype('uint8'),dilation)>0)&mb))
            if not count and not distance_contact:continue
            is_constrained=((first,second) in edge_pairs or (second,first) in edge_pairs)
            order_resolved=nx.has_path(graph,first,second) or nx.has_path(graph,second,first)
            if count:
                overlap_total+=count
                sample=_valid_sample(src,groups[first],groups[second],multiplicity)
                row=_score_pair(src,groups[first],groups[second],sample,first,second,min_pixels,min_color_gap)
                row['overlap_pixels']=count
                row['explicitly_constrained']=is_constrained
                row['ordering_resolved_by_graph']=order_resolved
                if row['status']=='strong_appearance_candidate':candidates.append(row)
                elif not order_resolved:unresolved.append(row)
            else:
                row={'pair':[first,second],'status':'near_touch_no_overlap','overlap_pixels':0,
                     'explicitly_constrained':is_constrained,
                     'ordering_resolved_by_graph':order_resolved,
                     'interpretation':'Possible junction or occlusion boundary; no ordering inferred'}
            contacts.append(row)
    # Underlying geometry is NOT automatically restored: this reports the
    # raster area of *already-authored* vectors hidden by completely opaque
    # objects above them. Transparent overdraw cannot be classified as invisible.
    opaque_foreground=np.zeros((h,w),dtype=bool)
    visibility={}
    declared={o['id']:o for _,o in _objects(manifest)}
    for oid in reversed(order):
        pix=groups[oid][:,:,3]>0
        occluded=pix & opaque_foreground
        n=int(pix.sum());blocked=int(occluded.sum())
        visibility[oid]={'authored_pixel_count':n,'opaque_occluded_pixel_count':blocked,
            'estimated_visible_pixel_count':n-blocked,
            'opaque_occluded_fraction':round(blocked/n,5) if n else 0,
            'hidden_geometry_provenance_review':bool(blocked and not declared[oid].get('inferred_hidden')
                                                 and declared[oid].get('geometry_provenance') not in ('source_vector','author_supplied_vector')),
            'generated_hidden_paths':False}
        opaque_foreground |= groups[oid][:,:,3]>=250
    # Constraints may be provided on touching/no-overlap objects; these cannot
    # be inferred, but remain user instructions.
    report={'schema_version':'2.4.0','method':'conservative_pairwise_visible_rgba',
        'canvas':{'width':w,'height':h},'bottom_to_top_order':order,
        'explicit_constraints':edges,'background_like_excluded':sorted(background),
        'inference_excluded':sorted(skip),'candidate_count':len(candidates),
        'unresolved_overlap_count':len(unresolved),'total_pairwise_overlap_pixels':overlap_total,
        'near_contact_radius_px':contact_radius,'contacts':contacts,
        'object_visibility':visibility,
        'hidden_geometry_provenance_review_count':sum(x['hidden_geometry_provenance_review'] for x in visibility.values()),
        'automatic_hidden_anatomy_reconstruction':False,'authoring_new_paths':False,
        'review_required':bool(candidates or unresolved or any(row['status']=='near_touch_no_overlap' for row in contacts)),
        'note':'Confidence describes local color agreement only; crossings/medical anatomy require manual review.'}
    if render_assets_dir is not None:
        out=Path(render_assets_dir);out.mkdir(parents=True,exist_ok=True)
        canvas=Image.fromarray(src,'RGBA').convert('RGB')
        over=Image.new('RGBA',(w,h),(0,0,0,0)); mask_draw=np.zeros((h,w,4),dtype=np.uint8)
        for row in contacts:
            if row['overlap_pixels']<=0:continue
            first,second=row['pair']
            overlap=masks[first]&masks[second]
            tint=(24,160,87,140) if row['ordering_resolved_by_graph'] else ((243,158,34,170) if row['status']=='strong_appearance_candidate' else (218,67,67,190))
            mask_draw[overlap]=tint
        over=Image.fromarray(mask_draw,'RGBA')
        canvas=Image.alpha_composite(canvas.convert('RGBA'),over).convert('RGB')
        canvas.save(out/'15_Occlusion_Review.png')
        # Simple explanatory stack as vector text and contours, no embedded image.
        layermap=_stack_svg(manifest,order,edges)
        (out/'16_Occlusion_Stack.svg').write_bytes(etree.tostring(layermap,encoding='utf-8',xml_declaration=True))
    return report

def _stack_svg(manifest,order,edges):
    objs={o['id']:(l,o) for l,o in _objects(manifest)}
    width=600;height=max(160,78+58*len(order))
    root=etree.Element('{%s}svg'%SVG_NS,nsmap={None:SVG_NS})
    root.set('width',str(width));root.set('height',str(height));root.set('viewBox',f'0 0 {width} {height}')
    etree.SubElement(root,'{%s}rect'%SVG_NS,{'width':str(width),'height':str(height),'fill':'#F8FAFC'})
    title=etree.SubElement(root,'{%s}text'%SVG_NS,{'x':'25','y':'36','font-size':'20','fill':'#26364B'});title.text='Layer stack — front to back'
    for i,oid in enumerate(reversed(order)):
        layer,obj=objs[oid];y=53+i*58
        etree.SubElement(root,'{%s}rect'%SVG_NS,{'x':'22','y':str(y),'width':'556','height':'46','rx':'7',
            'fill':'#FFFFFF','stroke':'#CCD6E2'})
        line=etree.SubElement(root,'{%s}text'%SVG_NS,{'x':'34','y':str(y+20),'font-family':'sans-serif',
            'font-size':'14','fill':'#243449'});line.text=f'{i+1:02d}  {oid}'
        desc=etree.SubElement(root,'{%s}text'%SVG_NS,{'x':'35','y':str(y+36),'font-family':'sans-serif','font-size':'11','fill':'#687C90'})
        desc.text=f"source layer: {layer['id']}"
    return root

def form_layer_groups(manifest,elements,ordered,svg_root):
    """Preserve editable semantic layers; split noncontiguous runs if needed."""
    mapping={o['id']:layer for layer,o in _objects(manifest)}
    runs=[]
    for oid in ordered:
        layer=mapping[oid]
        if not runs or runs[-1]['original_layer_id']!=layer['id']:
            runs.append({'original_layer_id':layer['id'],'layer':layer,'object_ids':[]})
        runs[-1]['object_ids'].append(oid)
    seq=defaultdict(int)
    for idx,run in enumerate(runs):
        layer=run['layer'];base=layer['id'];seq[base]+=1
        root_id='zlayer_%03d_%s_%02d'%(idx,base,seq[base])
        group=etree.SubElement(svg_root,'{%s}g'%SVG_NS,id=root_id)
        group.set('{%s}groupmode'%INK_NS,'layer')
        group.set('{%s}label'%INK_NS,layer.get('name_zh',base)+(f' · {seq[base]}' if seq[base]>1 else ''))
        group.set('data-original-layer-id',base)
        group.set('data-name-en',layer.get('name_en',base))
        for oid in run['object_ids']:group.append(elements[oid])
        run['svg_layer_id']=root_id
    return [{k:v for k,v in r.items() if k!='layer'} for r in runs]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',required=True,type=Path)
    p.add_argument('--out',type=Path,help='Output report directory (default: project)')
    p.add_argument('--write-manifest',action='store_true',help='Persist accepted candidate constraints only')
    p.add_argument('--accept-candidates',action='store_true',help='Explicit opt-in: accept strong candidates, still requires visual review')
    a=p.parse_args()
    from build_vector_package import build_object,local_path
    project=a.project.resolve(strict=True)
    manifest=json.loads(local_path(project,'manifest.json').read_text('utf-8'))
    src=local_path(project,manifest['source_image'])
    with Image.open(src) as im:w,h=im.size
    groups={}
    for _,obj in _objects(manifest):
        group,_=build_object(obj,project,w,h,0,'polygon')
        if obj['id'] in groups:raise ValueError('Duplicate object ID')
        groups[obj['id']]=group
    out=(a.out or project).resolve();out.mkdir(parents=True,exist_ok=True)
    report=analyze_scene(manifest,groups,src,w,h,render_assets_dir=out)
    candidates=[{'behind':row['suggested_behind'],'front':row['suggested_front']}
                for row in report['contacts'] if row['status']=='strong_appearance_candidate' and not row['ordering_resolved_by_graph']]
    if a.write_manifest:
        if not a.accept_candidates:raise ValueError('--write-manifest requires explicit --accept-candidates; otherwise edit user-confirmed constraints manually')
        existing={(c['behind'],c['front']) for c in manifest.get('occlusion',{}).get('constraints',[])}
        new=[]
        for c in candidates:
            pair=c['behind'],c['front']
            if pair not in existing:
                new.append({**c,'source':'appearance_candidate_operator_accepted','review_status':'not_anatomically_verified'})
        resolve_stack(manifest,new)  # Reject cycles before touching source files.
        manifest.setdefault('occlusion',{}).setdefault('constraints',[]).extend(new)
        temp=project/'manifest.v24.tmp.json';temp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(project/'manifest.json')
        report['persisted_constraints']=new
    (out/'occlusion_analysis_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(out/'occlusion_analysis_report.json'),
                      'candidate_count':report['candidate_count'],
                      'unresolved_overlap_count':report['unresolved_overlap_count'],
                      'write_manifest':a.write_manifest},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
