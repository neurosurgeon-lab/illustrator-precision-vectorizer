#!/usr/bin/env python3
"""conservative fragment/gap detection and reviewable amodal object completion.

Visible (modal) geometry is never modified by this module. Missing regions are
hypotheses, marked inferred and kept separate from the original SVG objects.
No anatomical, biomechanical or device structure is invented without review.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw
from lxml import etree
from build_vector_package import (root_svg, tag, INK_NS, to_xml, render,
                                  build_object, component_fit, union_boxes, visible_bbox, safe_id, local_path)


def components(mask, min_area=1):
    count, labels, stats, centroids=cv2.connectedComponentsWithStats(mask.astype('uint8'),8)
    result=[]
    for label in range(1,count):
        x,y,w,h,area=map(int,stats[label])
        if area>=min_area:
            result.append({'label':label,'area':area,'bbox':[x,y,w,h],
                           'centroid':[round(float(z),2) for z in centroids[label]]})
    return result,labels


def nearest_boundary(mask_a,mask_b):
    # The nearest 8-connected pixel pair. Returned gap is in pixels.
    # Reverse nearest-neighbor transform permits O(n) instead of O(N^2).
    dist,nearest=cv2.distanceTransformWithLabels((~mask_a).astype('uint8'),cv2.DIST_L2,3,cv2.DIST_LABEL_PIXEL)
    ys,xs=np.nonzero(mask_b)
    k=int(np.argmin(dist[ys,xs]));y2,x2=int(ys[k]),int(xs[k])
    y1,x1=int(np.argwhere(mask_a)[0][0]),int(np.argwhere(mask_a)[0][1])
    # Recover exact nearest pixel in small local neighborhood around target.
    radius=int(math.ceil(float(dist[y2,x2])+2))
    y0=max(0,y2-radius);y3=min(mask_a.shape[0],y2+radius+1)
    x0=max(0,x2-radius);x3=min(mask_a.shape[1],x2+radius+1)
    pts=np.argwhere(mask_a[y0:y3,x0:x3])
    if len(pts):
        delta=(pts[:,0]+y0-y2)**2+(pts[:,1]+x0-x2)**2
        j=int(np.argmin(delta));y1,x1=map(int,pts[j]+[y0,x0])
    return (x1,y1),(x2,y2),float(math.hypot(x2-x1,y2-y1))


def propose_short_gaps(mask,max_gap=12,min_fragment=3,max_fragment_fraction=.25,forbidden=None):
    m=np.asarray(mask,dtype=bool)
    comp,labels=components(m)
    comp.sort(key=lambda c:c['area'],reverse=True)
    if not comp:return [],m.copy()
    main=comp[0]; proposals=[];candidate=m.copy()
    for frag in comp[1:]:
        if frag['area']<min_fragment:continue
        a=(labels==main['label'])
        b=(labels==frag['label'])
        p,q,d=nearest_boundary(a,b)
        if d>max_gap or frag['area']>main['area']*max_fragment_fraction:
            proposals.append({'fragment_label':frag['label'],'status':'needs_manual_review',
                              'gap_px':round(d,2),'fragment_area':frag['area']})
            continue
        bridge=np.zeros(m.shape,np.uint8)
        cv2.line(bridge,p,q,255,1,cv2.LINE_8)
        bridge=bridge.astype(bool)&~m
        if forbidden is not None and (bridge&forbidden).any():
            status='blocked_other_object'
        else:
            status='proposed_short_gap'
            candidate|=bridge
        proposals.append({'fragment_label':frag['label'],'status':status,'gap_px':round(d,2),
                          'fragment_area':frag['area'],'endpoints':[list(p),list(q)],
                          'added_pixels':int(bridge.sum()) if status=='proposed_short_gap' else 0})
    return proposals,candidate


def propose_boundary_notches(mask,radius=3,max_pixels=80):
    """Suggest filling tiny inward contour notches; never auto-approve.

    Morphological closing may erase true mechanical slots / anatomical features,
    so this function only proposes a review layer.
    """
    m=np.asarray(mask,bool)
    if not 1<=radius<=12:raise ValueError('Notch radius must be 1..12')
    k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(radius*2+1,radius*2+1))
    closed=cv2.morphologyEx(m.astype('uint8'),cv2.MORPH_CLOSE,k)>0
    added=closed&~m
    parts,labels=components(added)
    selected=np.zeros_like(m)
    candidates=[]
    for part in parts:
        if part['area']<=max_pixels:
            selected|=labels==part['label']
            candidates.append({'status':'proposed_contour_notch','pixel_count':part['area'],
                               'bbox':part['bbox'],'requires_manual_review':True})
    return candidates,selected


def infer_guided_hidden(mask,occluder,guide,thickness=2,max_length=200,polygon=False):
    """Guide-based hidden region. Explicit artist points, not generative anatomy."""
    m=np.asarray(mask,bool);occ=np.asarray(occluder,bool)
    if m.shape!=occ.shape:raise ValueError('Occluder shape mismatch')
    if not isinstance(guide,list) or not (3 if polygon else 2)<=len(guide)<=64:
        raise ValueError('Invalid guide vertex count')
    h,w=m.shape;points=[]
    for p in guide:
        if not isinstance(p,list) or len(p)!=2 or any(not isinstance(z,(int,float)) or not math.isfinite(z) for z in p):
            raise ValueError('Invalid guide point')
        x,y=[int(round(t)) for t in p]
        if not 0<=x<w or not 0<=y<h:raise ValueError('Guide point outside image')
        points.append([x,y])
    if not polygon:
        if not m[points[0][1],points[0][0]] or not m[points[-1][1],points[-1][0]]:
            raise ValueError('Guide endpoints must match observable object')
        length=sum(math.dist(a,b) for a,b in zip(points[:-1],points[1:]))
        if length>max_length:raise ValueError('Guided completion exceeds maximum length')
    proposal=np.zeros(m.shape,np.uint8)
    if polygon:
        cv2.fillPoly(proposal,[np.array(points,np.int32)],255)
    else:
        cv2.polylines(proposal,[np.array(points,np.int32)],False,255,max(1,int(thickness)),cv2.LINE_8)
    added=(proposal>0)&occ&~m
    if not added.any():raise ValueError('Guided completion has no hidden region')
    return added


def infer_occluded_connection(mask, occluder, endpoints, thickness=2, max_length=120):
    """Only draw a user-identified corridor, and ONLY under provided occluder.

    endpoints need to be on observable mask and on opposite sides of occluder.
    No generative completion of anatomy is attempted; straight geometry is
    an *explicitly labelled* hypothesis. Approval is required before inclusion.
    """
    m=np.asarray(mask,bool); occ=np.asarray(occluder,bool)
    if m.shape!=occ.shape:raise ValueError('Occluder dimensions differ')
    if len(endpoints)!=2:raise ValueError('Exactly two annotated endpoints required')
    p,q=[[int(v) for v in xy] for xy in endpoints]
    h,w=m.shape
    for x,y in [p,q]:
        if not (0<=x<w and 0<=y<h) or not m[y,x]:
            raise ValueError('Endpoints must lie on observed object pixels')
    dist=math.dist(p,q)
    if dist>max_length or dist<2:raise ValueError('Endpoint separation outside safe range')
    bridge=np.zeros(m.shape,np.uint8)
    cv2.line(bridge,tuple(p),tuple(q),255,max(1,int(thickness)),cv2.LINE_8)
    inferred=(bridge>0)&occ&~m
    if inferred.sum()<1:raise ValueError('No occluded candidate: endpoints/occluder do not overlap')
    if not ((bridge>0)&occ).any():raise ValueError('No occluder intersection')
    return inferred


def load_binary(path,size):
    with Image.open(path) as im:
        if im.size!=size:raise ValueError(f'Image size mismatch: {path}')
        return np.array(im.convert('L'))>=128


def visible_mask(project,object_spec,w,h):
    geom=object_spec.get('geometry',{})
    if geom.get('type')=='mask_png' and not object_spec.get('transform'):
        return load_binary(local_path(project,geom['file']),(w,h))
    # SVG paths: use alpha rendering, no guessed hidden pixels.
    group,_=build_object(object_spec,project,w,h,1,'polygon')
    svg=root_svg(w,h);svg.append(group)
    import cairosvg,io
    png=cairosvg.svg2png(bytestring=to_xml(svg))
    return np.asarray(Image.open(io.BytesIO(png)).convert('RGBA').getchannel('A'))>=128


def generate(project,out,annotations=None,max_gap=12,elements=None):
    """Generate non-destructive amodal candidates and two-mode outputs.

    The original modal SVG must already be in output directory. The amodal
    sheet shows FULL isolated objects with dashed inferred path overlays; an
    amodal-composite preview leaves foreground occluders in place by design.
    """
    project=Path(project).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((project/'manifest.json').read_text('utf-8'))
    import hashlib
    source=local_path(project,manifest['source_image'])
    expected_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    if manifest.get('source_sha256') and manifest['source_sha256']!=expected_hash:
        raise ValueError('Source SHA256 does not match manifest')
    modal=out/'01_Full_Illustration.svg'
    if not modal.exists():raise ValueError('Export modal SVG first via build_vector_package.py')
    w=int(manifest['canvas']['width']);h=int(manifest['canvas']['height'])
    with Image.open(source) as im:
        if im.size!=(w,h):raise ValueError('Canvas must match source image')
    specs={o['id']:o for l in manifest.get('layers',[]) for o in l['objects']}
    config=json.loads(Path(annotations).read_text('utf-8')) if annotations else {}
    config_objects={}
    for obj in config.get('objects',[]):
        oid=obj['id']
        if oid not in specs or oid in config_objects:raise ValueError('Unknown or duplicate completion object ID')
        for key in ('approve_short_gaps','approve_notches','approve_hidden','exclude_other_objects'):
            if key in obj and type(obj[key]) is not bool:raise ValueError(key+' must be a JSON boolean')
        if sum(obj.get(key) is not None for key in ('occluded_endpoints','hidden_guide','hidden_polygon'))>1:
            raise ValueError('Choose only one hidden region method')
        config_objects[oid]=obj
    if elements is None:
        tree=etree.parse(str(modal),etree.XMLParser(resolve_entities=False,no_network=True))
        groups={g.get('id'):g for g in tree.iter(tag('g'))}
        elements={oid:groups['obj_'+oid if oid[0].isdigit() else oid] for oid in specs}
    for old in list(out.glob('18_inferred_*.png'))+list(out.glob('22_proposal_*.png')):old.unlink()
    masks={oid:visible_mask(project,spec,w,h) for oid,spec in specs.items()}
    objects={}; candidate_objects={}; reports=[]; review=Image.open(local_path(project,manifest['source_image'])).convert('RGB').copy()
    draw=ImageDraw.Draw(review)
    for oid,spec in specs.items():
        raw=masks[oid]
        settings=config_objects.get(oid,{})
        other=np.zeros((h,w),bool)
        occluders=settings.get('occluder_ids',[])
        for blocker in occluders:
            if blocker not in specs or blocker==oid:raise ValueError(f'{oid}: invalid occluder {blocker}')
            other |= masks[blocker]
        forb=np.zeros((h,w),bool)
        if settings.get('exclude_other_objects',True):
            for other_id,other_spec in specs.items():
                if other_id!=oid:forb|=masks[other_id]
        proposals,patched=propose_short_gaps(raw,max_gap=int(settings.get('max_gap',max_gap)),forbidden=forb)
        notch_proposals,notch_pixels=propose_boundary_notches(raw,
              radius=int(settings.get('notch_radius',3)),max_pixels=int(settings.get('max_notch_area',80)))
        # Short gap suggestions are never included until explicitly approved.
        approved_gaps=bool(settings.get('approve_short_gaps',False))
        bridge=(patched&~raw) if approved_gaps else np.zeros(raw.shape,bool)
        accepted_notches=(notch_pixels&~forb) if settings.get('approve_notches',False) else np.zeros(raw.shape,bool)
        inferred=np.zeros((h,w),bool)
        hypothesis=None
        if settings.get('occluded_endpoints') is not None:
            inferred=infer_occluded_connection(raw,other,settings['occluded_endpoints'],
                     thickness=int(settings.get('thickness',2)),max_length=float(settings.get('max_hidden_length',120)))
            hypothesis={'pixel_count':int(inferred.sum()),'status':'approved_inferred' if settings.get('approve_hidden',False) else 'awaits_explicit_approval',
                        'method':'straight_under_declared_occluder','endpoints':settings['occluded_endpoints']}
        if settings.get('hidden_guide') is not None or settings.get('hidden_polygon') is not None:
            if hypothesis:raise ValueError('Choose either endpoints or a guided hidden region, not both')
            is_polygon=settings.get('hidden_polygon') is not None
            guide=settings.get('hidden_polygon') if is_polygon else settings['hidden_guide']
            inferred=infer_guided_hidden(raw,other,guide,thickness=int(settings.get('thickness',2)),
                         max_length=float(settings.get('max_hidden_length',200)),polygon=is_polygon)
            hypothesis={'pixel_count':int(inferred.sum()),'status':'approved_inferred' if settings.get('approve_hidden',False) else 'awaits_explicit_approval',
                        'method':'artist_guided_polygon' if is_polygon else 'artist_guided_polyline',
                        'guide_points':guide}
        if settings.get('approve_hidden',False) and not hypothesis:
            raise ValueError(f'{oid}: approve_hidden without evidence / annotated endpoints')
        additions=bridge | accepted_notches | (inferred if settings.get('approve_hidden',False) else np.zeros(raw.shape,bool))
        composite=raw|additions
        # Visible mask is exactly original. Amodal has additions only on approved objects.
        group=copy.deepcopy(elements[oid])
        if additions.any():
            # Inferred pixels use canvas coordinates; retain any source transform only on original geometry.
            if group.get('transform'):
                transformed=etree.Element(tag('g'),transform=group.attrib.pop('transform'))
                for child in list(group):transformed.append(child)
                group.append(transformed)
            from mask_precision import trace_mask
            target=out/f'18_inferred_{safe_id(oid)}.png'
            Image.fromarray((additions*255).astype('uint8'),'L').save(target)
            d,_,_,_=trace_mask(target,w,h,0.35,mode='polygon')
            overlay=etree.SubElement(group,tag('path'),d=d)
            overlay.set('fill',spec.get('fill','#999999') if spec.get('fill') not in ('none',None) else '#999999')
            overlay.set('stroke','none');overlay.set('data-inferred','true')
            overlay.set('data-approval','explicit')
            ys,xs=np.where(additions)
            for x,y in zip(xs[::max(1,len(xs)//50)],ys[::max(1,len(ys)//50)]):draw.point((int(x),int(y)),fill='#D97937')
        objects[oid]=group
        # Separate proposal layer: NEVER implies approval; dotted orange paths
        # show exactly what would be reconstructed after the user's inspection.
        candidate_group=copy.deepcopy(group)
        proposals_only=((patched&~raw)&~bridge)|(notch_pixels&~accepted_notches)|(inferred&~additions)
        if proposals_only.any():
            from mask_precision import trace_mask
            proposal_file=out/f'22_proposal_{safe_id(oid)}.png'
            Image.fromarray((proposals_only*255).astype('uint8'),'L').save(proposal_file)
            proposed_d,_,_,_=trace_mask(proposal_file,w,h,0.35,mode='polygon')
            node=etree.SubElement(candidate_group,tag('path'),d=proposed_d)
            node.set('fill','#EE9C45');node.set('fill-opacity','0.35')
            node.set('stroke','#BA581A');node.set('stroke-width','1.4')
            node.set('stroke-dasharray','4 3');node.set('data-proposal-unapproved','true')
        candidate_objects[oid]=candidate_group
        reports.append({'id':oid,'component_count':len(components(raw)[0]),'fragment_proposals':proposals,'notch_proposals':notch_proposals,
            'occlusion_hypothesis':hypothesis,'approved_short_gap_pixels':int(bridge.sum()),'approved_notch_pixels':int(accepted_notches.sum()),
            'approved_hidden_pixels':int((inferred&additions).sum()),
            'modal_unchanged':True,'manual_review_required':bool(proposals or notch_proposals or hypothesis),
            'topology_before':len(components(raw)[0]),'topology_amodal':len(components(composite)[0])})
    # approved OCR text must also be separately editable on Amodal sheet.
    from text_recognition import append_approved_text
    text_root=root_svg(w,h)
    reviewed_text=append_approved_text(text_root,project/'text_review.json',expected_hash,w,h)
    for item in text_root:
        tid=item.get('id')
        if tid in objects:raise ValueError('Duplicate OCR/geometry ID')
        objects[tid]=item;candidate_objects[tid]=copy.deepcopy(item)
        specs[tid]={'name_zh':'文字 '+tid,'name_en':'Reviewed text','fill':'none'}
    # True, unchanged modal SVG copied for explicit pairing.
    modal=out/'01_Full_Illustration.svg'
    if not modal.exists():raise ValueError('Export modal SVG first via build_vector_package.py')
    (out/'18_Modal_Illustration.svg').write_bytes(modal.read_bytes())
    # Preserve object identity & semantic editability on an isolated amodal sheet.
    n=len(objects);cols=min(4,max(2,math.ceil(math.sqrt(n))));rows=math.ceil(n/cols)
    pw,ph=410,340;sheet=root_svg(cols*pw,rows*ph)
    etree.SubElement(sheet,tag('rect'),x='0',y='0',width=str(cols*pw),height=str(rows*ph),fill='#FFFFFF')
    for index,(oid,g) in enumerate(objects.items()):
        x=(index%cols)*pw;y=(index//cols)*ph
        etree.SubElement(sheet,tag('rect'),x=str(x),y=str(y),width=str(pw),height=str(ph),fill='#FFFFFF',stroke='#DCE2E7')
        label=etree.SubElement(sheet,tag('text'),x=str(x+15),y=str(y+26),fill='#30465C',**{'font-size':'15','font-family':'PingFang SC, Noto Sans CJK SC, sans-serif'})
        label.text=f'{index+1:02d}  {specs[oid].get("name_zh",oid)}'
        bb=visible_bbox(g,w,h)
        fitted=etree.SubElement(sheet,tag('g'),transform=component_fit(bb,x+pw/2,y+ph/2+16,pw-40,ph-76))
        fitted.set('data-amodal-panel',oid)
        fitted.append(copy.deepcopy(g))
    (out/'19_Amodal_Isolated_Objects.svg').write_bytes(to_xml(sheet))
    proposal_sheet=copy.deepcopy(sheet)
    panels=proposal_sheet.xpath('//*[local-name()="g" and @data-amodal-panel]')
    if len(panels)==len(candidate_objects):
        for panel,(oid,cg) in zip(panels,candidate_objects.items()):
            for item in list(panel):panel.remove(item)
            panel.append(copy.deepcopy(cg))
    (out/'22_Unapproved_Completion_Candidates.svg').write_bytes(to_xml(proposal_sheet))
    render(proposal_sheet,out/'22_Unapproved_Completion_Candidates.png')
    render(sheet,out/'19_Amodal_Isolated_Objects.png')
    # Reviewer-specific SVG shows approved hidden additions in dashed orange.
    reviewer=copy.deepcopy(sheet)
    for element in reviewer.xpath('//*[local-name()="path" and @data-inferred="true"]'):
        element.set('stroke','#D97937');element.set('stroke-width','1.5')
        element.set('stroke-dasharray','3 3');element.set('fill-opacity','0.70')
    (out/'23_Amodal_Approval_Review.svg').write_bytes(to_xml(reviewer))
    render(reviewer,out/'23_Amodal_Approval_Review.png')
    review.save(out/'21_Completion_Review.png')
    report={'version':'3.2','total_objects':n,'modal_source_unchanged':True,'amodal_requires_review':True,
            'inferences_not_anatomical_truth':True,'reviewed_text_count':len(reviewed_text),
            'objects':reports}
    (out/'20_Completion_Report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--annotations',type=Path)
    p.add_argument('--max-gap',type=int,default=12)
    a=p.parse_args()
    print(json.dumps(generate(a.project,a.out,a.annotations,a.max_gap),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
