#!/usr/bin/env python3
"""Inspect real editing structure and derive a dedicated visible stroke SVG."""
import copy
import json
import re
from lxml import etree

SHAPES={'path','circle','ellipse','rect','line','polyline','polygon'}


def visible(node):
    for ancestor in [node,*node.iterancestors()]:
        style=dict(re.findall(r'([\w-]+)\s*:\s*([^;]+)',ancestor.get('style','')))
        if style.get('display',ancestor.get('display'))=='none':return False
        if style.get('visibility',ancestor.get('visibility')) in ('hidden','collapse'):return False
        if float(style.get('opacity',ancestor.get('opacity','1')))==0:return False
        if etree.QName(ancestor).localname=='defs':return False
    return True


def property_value(node,key,default):
    for ancestor in [node,*node.iterancestors()]:
        style=dict(re.findall(r'([\w-]+)\s*:\s*([^;]+)',ancestor.get('style','')))
        value=style.get(key,ancestor.get(key))
        if value is not None:return value.strip()
    return default


def open_subpaths(node):
    name=etree.QName(node).localname
    if name in ('line','polyline'):return 1
    if name!='path':return 0
    return sum(not re.search('[Zz]',part) for part in re.findall(r'[Mm][^Mm]*',node.get('d','')))


def geometry_stats(root):
    shapes=[n for n in root.iter() if etree.QName(n).localname in SHAPES and visible(n)]
    strokes=[n for n in shapes if property_value(n,'stroke','none')!='none'
             and float(property_value(n,'stroke-width','1'))>0
             and float(property_value(n,'stroke-opacity','1'))>0]
    return {'visible_geometry_items':len(shapes),'visible_stroked_items':len(strokes),
            'open_stroked_subpaths':sum(open_subpaths(n) for n in strokes),
            'filled_items':sum(property_value(n,'fill','black')!='none' and float(property_value(n,'fill-opacity','1'))>0 for n in shapes),
            'path_command_count':sum(len(re.findall(r'[MmLlHhVvCcSsQqTtAaZz]',n.get('d',''))) for n in shapes)}


def inspect_editability(elements,qa=None):
    qa=qa or {}
    required=qa.get('editable_stroke_object_ids',[])
    if not isinstance(required,list) or any(not isinstance(oid,str) for oid in required):
        raise ValueError('editable_stroke_object_ids must be a list of object IDs')
    budgets=qa.get('max_geometry_items_per_object',{})
    if not isinstance(budgets,dict) or any(type(v) is not int or v<1 for v in budgets.values()):
        raise ValueError('max_geometry_items_per_object must map IDs to positive integers')
    objects={oid:geometry_stats(group) for oid,group in elements.items()}
    failures=[]
    for oid in required:
        if oid not in objects or objects[oid]['open_stroked_subpaths']==0:
            failures.append({'object_id':oid,'reason':'required_visible_open_stroke_missing'})
    for oid,budget in budgets.items():
        if oid not in objects or objects[oid]['visible_geometry_items']>budget:
            failures.append({'object_id':oid,'reason':'declared_geometry_budget_not_met','maximum':budget,
                             'observed':objects.get(oid,{}).get('visible_geometry_items')})
    return {'objects':objects,'geometry_items':sum(v['visible_geometry_items'] for v in objects.values()),
            'open_stroked_subpaths':sum(v['open_stroked_subpaths'] for v in objects.values()),
            'stroke_requirements_declared':bool(required),
            'editing_contract_status':'declared_strokes_checked' if required else 'no_stroke_contract_declared','failures':failures,'quality_gates_passed':not failures,
            'manual_part_boundary_and_anchor_review_required':True,
            'native_illustrator_verified':False,
            'interpretation':'Pixel fidelity and editing structure are separate checks; counts do not prove semantic editability.'}


def linework(root):
    result=copy.deepcopy(root)
    for node in list(result.iter()):
        if etree.QName(node).localname not in SHAPES:continue
        if any(etree.QName(a).localname=='defs' for a in node.iterancestors()):continue
        stroke=property_value(node,'stroke','none')
        if not visible(node) or stroke=='none' or float(property_value(node,'stroke-width','1'))<=0 or float(property_value(node,'stroke-opacity','1'))<=0:
            node.getparent().remove(node)
        else:
            # Preserve inherited source styling; remove only fill from visible stroke geometry.
            style=node.get('style','')
            style=re.sub(r'(?<![\w-])fill\s*:[^;]*(;|$)','',style)
            if style:node.set('style',style)
            else:node.attrib.pop('style',None)
            node.set('fill','none')
    # Dedicated linework excludes OCR fills and hidden centreline helpers.
    for node in list(result.xpath('//*[local-name()="text" or local-name()="tspan"]')):
        if node.getparent() is not None:node.getparent().remove(node)
    return result
