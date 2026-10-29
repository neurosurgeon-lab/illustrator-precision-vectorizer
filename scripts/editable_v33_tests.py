#!/usr/bin/env python3
"""Editing contracts, true linework, native staging, and pixel-pass/missing-stroke regression."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
from lxml import etree
from build_vector_package import root_svg,tag,to_xml
from editable_svg import inspect_editability,linework,geometry_stats
from illustrator_native import prepare,load_svg
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'examples'))
from create_editable_v33_demo import create

HERE=Path(__file__).resolve().parent


def checks(root):
    svg=root_svg(40,40)
    group=etree.SubElement(svg,tag('g'),id='wire',stroke='#334455',style='fill:#FFFFFF;stroke-width:2')
    etree.SubElement(group,tag('path'),d='M2 5 C10 5 20 25 35 25')
    etree.SubElement(group,tag('path'),d='M2 5 L35 25',display='none')
    etree.SubElement(group,tag('path'),d='M2 2 H5 V5 Z',stroke='none')
    result=inspect_editability({'wire':group},{'editable_stroke_object_ids':['wire'],'max_geometry_items_per_object':{'wire':2}})
    assert result['quality_gates_passed'] and result['open_stroked_subpaths']==1
    clean=linework(svg)
    assert len(list(clean.iter(tag('path'))))==1 and geometry_stats(clean)['filled_items']==0
    assert not inspect_editability({'wire':group},{'max_geometry_items_per_object':{'wire':1}})['quality_gates_passed']
    # A hidden reference guide must never satisfy the visible wire contract.
    hidden=copy.deepcopy(group)
    for node in hidden:node.set('display','none')
    assert not inspect_editability({'wire':hidden},{'editable_stroke_object_ids':['wire']})['quality_gates_passed']
    # Resource geometry stays in defs; visible stroke clipping must remain valid.
    defs=etree.SubElement(svg,tag('defs'));clip=etree.SubElement(defs,tag('clipPath'),id='clip')
    etree.SubElement(clip,tag('rect'),width='40',height='40')
    group.set('clip-path','url(#clip)')
    assert linework(svg).find('.//'+tag('clipPath')+'/'+tag('rect')) is not None
    text_group=etree.SubElement(svg,tag('g'),id='reviewed_text')
    etree.SubElement(text_group,tag('text'),x='5',y='20').text='Reviewed OCR'
    source=root/'sample.svg';source.write_bytes(to_xml(svg))
    jobs=prepare(source,root/'native')
    assert len(jobs['jobs'])==2 and not list((root/'native').glob('*.ai'))
    assert all(job['requires_open_stroke'] for job in jobs['jobs'])
    assert len(jobs['jobs'][0]['parts'])==2 and len(jobs['jobs'][1]['parts'])==1,'Approved text must survive color staging'
    with source.open('wb') as f:f.write(b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><image href="private.png"/></svg>')
    try:load_svg(source)
    except ValueError:pass
    else:raise AssertionError('Raster embed accepted')
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><path id="a"/><path id="a"/></svg>')
    try:load_svg(source)
    except ValueError:pass
    else:raise AssertionError('Duplicate IDs accepted')
    project=create(root/'demo');out=root/'export'
    command=[sys.executable,str(HERE/'build_vector_package.py'),'--project',str(project),'--out',str(out)]
    subprocess.run(command,check=True,capture_output=True,text=True)
    with zipfile.ZipFile(out/'08_All_Files.zip') as z:
        assert '24_Editable_Linework.svg' in z.namelist() and '25_Editability_Report.json' in z.namelist()
    report=json.loads((out/'quality_report.json').read_text())
    assert report['quality_gates_passed'] and report['editability']['open_stroked_subpaths']==1
    manifest=json.loads((project/'manifest.json').read_text())
    wire=manifest['layers'][-1]['objects'][0]
    # Same rendered pixels, but the declared wire is now a filled closed silhouette.
    import cv2
    import numpy as np
    from PIL import Image
    import io,cairosvg
    from build_vector_package import build_object
    stage=root_svg(320,240);stage.append(build_object(wire,project,320,240,0,'polygon')[0])
    rendered=Image.open(io.BytesIO(cairosvg.svg2png(bytestring=to_xml(stage)))).convert('RGBA')
    contours,_=cv2.findContours((np.array(rendered)[:,:,3]>127).astype('uint8'),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    from mask_precision import contour_poly
    wire['geometry']['d']=' '.join(contour_poly(c,0) for c in contours if len(c)>=3)
    wire['fill']='#405C73';wire['stroke']='none'
    (project/'manifest.json').write_text(json.dumps(manifest))
    failed=root/'filled_wire'
    result=subprocess.run(command[:-1]+[str(failed)],capture_output=True,text=True)
    assert result.returncode!=0 and not (failed/'08_All_Files.zip').exists()
    report=json.loads((failed/'quality_report.json').read_text())
    assert not report['fidelity_failures'],'This regression must pass pixel QA while failing editing structure'
    assert not report['editability']['quality_gates_passed'] and report['editability']['failures'][0]['object_id']=='wire'
    draft=root/'draft'
    subprocess.run(command[:-1]+[str(draft),'--allow-draft'],check=True,capture_output=True,text=True)
    assert not json.loads((draft/'quality_report.json').read_text())['quality_gates_passed']
    assert (draft/'08_All_Files.zip').exists()

if __name__=='__main__':
    with tempfile.TemporaryDirectory() as directory:checks(Path(directory))
    print('PASS: visible stroke contracts, geometry budgets, resource-safe linework, native staging and missing-stroke export protection')
