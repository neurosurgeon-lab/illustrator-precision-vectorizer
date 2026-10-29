#!/usr/bin/env python3
"""Prepare an editable color/linework bundle; optionally run desktop Illustrator on macOS.

Preparing is portable and creates no AI. --run requires an installed, authorized
Illustrator; only its saved/reopened verification report establishes success.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from lxml import etree
from editable_svg import geometry_stats,linework,visible
from build_vector_package import tag,to_xml,INK_NS

HERE=Path(__file__).resolve().parent
ALLOWED={'svg','g','defs','path','circle','ellipse','rect','line','polyline','polygon',
         'linearGradient','radialGradient','stop','clipPath','title','desc','text','tspan'}


def load_svg(path):
    data=Path(path).read_bytes()
    if len(data)>40_000_000:raise ValueError('SVG exceeds 40 MB; simplify editing geometry first')
    parser=etree.XMLParser(resolve_entities=False,no_network=True,remove_comments=True)
    tree=etree.fromstring(data,parser)
    if tree.getroottree().docinfo.doctype:raise ValueError('SVG DTDs/entities are unsupported')
    ids=[n.get('id') for n in tree.iter() if n.get('id')]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate SVG IDs')
    for node in tree.iter():
        if etree.QName(node).localname not in ALLOWED:raise ValueError('Unsupported SVG element: '+etree.QName(node).localname)
        for key,value in node.attrib.items():
            name=etree.QName(key).localname
            if name.lower().startswith('on') or name in ('href','src'):
                raise ValueError('SVG events/external references are unsupported')
            for ref in re.findall(r'url\((.*?)\)',value,re.I):
                ref=ref.strip().strip('"\'')
                if not ref.startswith('#') or ref[1:] not in ids:raise ValueError('Invalid SVG resource reference')
            if 'url' in value.lower() and not re.search(r'url\(',value,re.I):raise ValueError('Invalid resource syntax')
    if etree.QName(tree).localname!='svg':raise ValueError('Expected SVG root')
    box=tree.get('viewBox')
    if box:
        values=[float(v) for v in re.split(r'[ ,]+',box.strip())]
        if len(values)!=4 or values[:2]!=[0,0]:raise ValueError('Use a zero-origin viewBox')
        width,height=values[2:]
    else:
        def dimension(key):
            match=re.fullmatch(r'([\d.]+)(?:px)?',tree.get(key,''))
            if not match:raise ValueError('SVG dimensions must be pixel units')
            return float(match[1])
        width,height=dimension('width'),dimension('height')
    if not all(math.isfinite(v) and 0<v<=100000 for v in (width,height)):raise ValueError('Invalid SVG canvas')
    tree.set('width',f'{width:g}px');tree.set('height',f'{height:g}px')
    tree.set('viewBox',f'0 0 {width:g} {height:g}')
    return tree,width,height


def has_content(node):
    return bool(geometry_stats(node)['visible_geometry_items'] or any(
        etree.QName(n).localname=='text' and visible(n) and ''.join(n.itertext()).strip() for n in node.iter()))


def prepare(svg,out):
    source=Path(svg).expanduser().resolve(strict=True);out=Path(out).expanduser().resolve()
    root,width,height=load_svg(source)
    if not has_content(root):raise ValueError('No visible vector geometry or editable text')
    if out==source or out in source.parents:raise ValueError('Output must not contain the source file')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):raise ValueError('Output directory must be empty')
    out.mkdir(parents=True,exist_ok=True)
    jobs=[]
    variants=[('Color',root),('Linework',linework(root))]
    for mode,tree in variants:
        stats=geometry_stats(tree)
        if not has_content(tree):continue
        parts=[]
        existing={n.get('id') for n in tree.iter() if n.get('id')}
        prefix='native_v33_'
        while any(oid and oid.startswith(prefix) for oid in existing):prefix+='x'
        for node in list(tree):
            if etree.QName(node).localname in ('defs','title','desc'):continue
            if not has_content(node):tree.remove(node);continue
            index=len(parts)+1;oid=f'{prefix}{index:04d}'
            name=node.get(f'{{{INK_NS}}}label') or node.get('data-name-en') or node.get('id') or f'Part {index}'
            wrapper=etree.Element(tag('g'),id=oid);tree.replace(node,wrapper);wrapper.append(node)
            parts.append({'id':oid,'name':name})
        filename=f'{mode}.svg';(out/filename).write_bytes(to_xml(tree))
        jobs.append({'input':filename,'output':f'Native_{mode}.ai',
            'report':f'{mode}_verified.json','preview':f'Illustrator_{mode}.png',
            'width':width,'height':height,'parts':parts,
            'requires_open_stroke':stats['open_stroked_subpaths']>0})
    script=HERE.parent/'illustrator/native_editable.jsx'
    (out/'run_in_illustrator.jsx').write_text('var SPEC='+json.dumps({'jobs':jobs},ensure_ascii=True)+';\n'+script.read_text('utf-8'),encoding='utf-8')
    spec={'version':'1.0.0','native_ai_created':False,'source_svg':source.name,'jobs':jobs,
          'requires_desktop_illustrator':True,'visual_review_required':True}
    (out/'native_jobs.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
    return spec


def run(out,spec):
    if sys.platform!='darwin':raise RuntimeError('--run uses macOS AppleScript; run the prepared JSX manually on other platforms')
    script=Path(out).resolve()/'run_in_illustrator.jsx'
    command='tell application "Adobe Illustrator" to do javascript file (POSIX file '+json.dumps(str(script))+')'
    result=subprocess.run(['osascript','-e',command],capture_output=True,text=True,timeout=180)
    if result.returncode:raise RuntimeError('Illustrator execution failed: '+result.stderr.strip())
    reports=[]
    for job in spec['jobs']:
        report=json.loads((Path(out)/job['report']).read_text('utf-8'))
        if report.get('save_and_reopen_verified') is not True:raise RuntimeError('Missing native verification')
        if not (Path(out)/job['output']).is_file():raise RuntimeError('Native output missing')
        reports.append(report)
    return reports


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--svg',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--run',action='store_true',help='Execute installed desktop Illustrator on macOS')
    args=parser.parse_args()
    spec=prepare(args.svg,args.out)
    if args.run:
        reports=run(args.out,spec)
        print(json.dumps({'native_ai_created':True,'verified_files':[r['ai_file'] for r in reports]},ensure_ascii=False))
    else:print(json.dumps({'native_ai_created':False,'prepared_jobs':len(spec['jobs']),'jsx':str(args.out/'run_in_illustrator.jsx')},ensure_ascii=False))

if __name__=='__main__':main()
