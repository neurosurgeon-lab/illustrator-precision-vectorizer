#!/usr/bin/env python3
"""occlusion adversarial tests (all synthetic, not medical validation)."""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from lxml import etree

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'examples'))
from create_occlusion_v24_demo import make_demo
from occlusion_layers import resolve_stack,analyze_scene,form_layer_groups
from build_vector_package import build_object,root_svg


def expect_error(function, fragment=''):
    try:function()
    except ValueError as ex:
        assert fragment.lower() in str(ex).lower(),(fragment,str(ex))
    else:raise AssertionError('Expected validation failure')


def run():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);proj=make_demo(root/'baseline',strict=False)
        mpath=proj/'manifest.json'
        man=json.loads(mpath.read_text('utf-8'))
        src=proj/'source.png';w,h=Image.open(src).size
        obj={o['id']:build_object(o,proj,w,h,0,'polygon')[0] for l in man['layers'] for o in l['objects']}
        # 1: explicit semantic ordering correct; separate device segments.
        ordered,edges,_=resolve_stack(man)
        assert ordered==['background','body','device_base','nerve','wire','electrode_cap'],ordered
        svg=root_svg(w,h)
        runs=form_layer_groups(man,obj,ordered,svg)
        assert [r['original_layer_id'] for r in runs].count('L02_device')==2
        assert len(svg.xpath('//*[local-name()="g" and @data-original-layer-id]'))==6
        # 2: image-evidence candidates + background exclusion + evidence limitations.
        report=analyze_scene(man,obj,src,w,h)
        assert report['candidate_count']>=2
        assert 'background' in report['background_like_excluded']
        assert report['automatic_hidden_anatomy_reconstruction'] is False
        strong=[r for r in report['contacts'] if r['status']=='strong_appearance_candidate']
        assert any(row['pair']==['electrode_cap','wire'] and row['suggested_front']=='electrode_cap' for row in strong)
        # 3: cycle fail in DAG, prevent partial changes.
        cycle=copy.deepcopy(man)
        cycle['occlusion']['constraints'].append({'behind':'electrode_cap','front':'device_base','source':'user_confirmed'})
        expect_error(lambda:resolve_stack(cycle),'cycle')
        # 4: typo/missing reason constraints rejected.
        bad=copy.deepcopy(man)
        bad['occlusion']['constraints'][0]['front']='missing'
        expect_error(lambda:resolve_stack(bad),'invalid occlusion constraint')
        bad=copy.deepcopy(man);bad['occlusion']['constraints'][0].pop('source')
        expect_error(lambda:resolve_stack(bad),'source')
        # 5: ambiguous same-colored crossing cannot be decided by pixel matching.
        small=copy.deepcopy(man)
        # Make the reference fully opaque white but mask colors near identical.
        altered=copy.deepcopy(obj)
        identical=copy.deepcopy(altered['wire'])
        identical.xpath('//*[local-name()="path"]')[0].set('stroke','#62A6A1')
        altered['wire']=identical
        sub=analyze_scene(small,altered,src,w,h)
        cross=next(r for r in sub['contacts'] if r['pair']==['nerve','wire'])
        assert cross['status']!='strong_appearance_candidate'
        # 6: crossing path without any overlap cannot be connected or ordered.
        minimal={'layers':[{'id':'L1','objects':[{'id':'first'},{'id':'second'}]}],
                 'occlusion':{'constraints':[]}}
        one=etree.Element('{http://www.w3.org/2000/svg}g',id='first')
        etree.SubElement(one,'{http://www.w3.org/2000/svg}path',d='M 5 5 H 45',fill='none',stroke='#226699',**{'stroke-width':'3'})
        two=etree.Element('{http://www.w3.org/2000/svg}g',id='second')
        etree.SubElement(two,'{http://www.w3.org/2000/svg}path',d='M 5 25 H 45',fill='none',stroke='#AA5511',**{'stroke-width':'3'})
        white=root/'plain.png';Image.new('RGBA',(50,40),'white').save(white)
        mini=analyze_scene(minimal,{'first':one,'second':two},white,50,40)
        assert mini['candidate_count']==0 and not mini['contacts']
        # 7: translucent intersections cannot be asserted as opaque front/back.
        tr=copy.deepcopy(obj)
        tr['wire']=copy.deepcopy(obj['wire'])
        tr['wire'].xpath('//*[local-name()="path"]')[0].set('opacity','.45')
        transparent=analyze_scene(man,tr,src,w,h)
        assert all(r.get('suggested_front')!='wire' for r in transparent['contacts'])
        # 8: a wholly three-way overlap has zero independent two-object pixels;
        # local evidence must remain ambiguous.
        three={'layers':[{'id':'L','objects':[{'id':v} for v in ('one','two','three')]}],
               'occlusion':{'constraints':[]}}
        triple={}
        for k,col in [('one','#C33333'),('two','#3B914A'),('three','#5679C4')]:
            g=etree.Element('{http://www.w3.org/2000/svg}g',id=k)
            etree.SubElement(g,'{http://www.w3.org/2000/svg}path',d='M 8 8 H 30 V 30 H 8 Z',fill=col)
            triple[k]=g
        three_report=analyze_scene(three,triple,white,50,40)
        assert three_report['candidate_count']==0
        assert all(r['sample_pixels']==0 for r in three_report['contacts'])
        # 9: --write-manifest without explicit acceptance must refuse and NOT mutate.

        original=mpath.read_bytes()
        cmd=[sys.executable,str(ROOT/'scripts/occlusion_layers.py'),'--project',str(proj)]
        refused=subprocess.run(cmd+['--write-manifest'],capture_output=True,text=True)
        assert refused.returncode!=0 and mpath.read_bytes()==original
        # 10: accepting only candidates, but never hidden paths; accepted precedence checked.
        accepted=subprocess.run(cmd+['--accept-candidates','--write-manifest'],capture_output=True,text=True)
        assert accepted.returncode==0,accepted.stderr
        after=json.loads(mpath.read_text('utf-8'))
        assert len(after['layers'])==len(man['layers'])
        assert all(o['geometry']['d']==orig['geometry']['d'] for (_,o),(_,orig) in zip(
           ((l,o) for l in after['layers'] for o in l['objects']),
           ((l,o) for l in man['layers'] for o in l['objects'])))
        assert len(after['occlusion']['constraints'])>len(man['occlusion']['constraints'])
        assert all(row.get('review_status')=='not_anatomically_verified'
                for row in after['occlusion']['constraints'][len(man['occlusion']['constraints']):])
        resolve_stack(after)
        # 11: strict gate blocks unresolved overlap with perfect raster agreement.
        strict_proj=make_demo(root/'strict',strict=True)
        out=root/'strict_export'
        builder=[sys.executable,str(ROOT/'scripts/build_vector_package.py'),
                 '--project',str(strict_proj),'--out',str(out)]
        blocked=subprocess.run(builder,capture_output=True,text=True)
        assert blocked.returncode!=0 and not (out/'08_All_Files.zip').exists(),blocked.stderr
        assert (out/'quality_report.json').exists()
        failed=json.loads((out/'quality_report.json').read_text('utf-8'))
        assert failed['quality_gates_passed'] is False
        assert any(r['reason']=='unresolved_visible_overlap' for r in failed['geometry_failures'])
        # 12: reverse a color-supported ordering without a graph cycle:
        # must be reported and block ZIP even if strict global QA was disabled.
        wrong_proj=make_demo(root/'contradiction',strict=False)
        wrongpath=wrong_proj/'manifest.json'
        wrong=json.loads(wrongpath.read_text('utf-8'))
        for row in wrong['occlusion']['constraints']:
            if row['behind']=='wire' and row['front']=='electrode_cap':
                row['behind'],row['front']='electrode_cap','wire'
        wrongpath.write_text(json.dumps(wrong,ensure_ascii=False,indent=2),'utf-8')
        wo=root/'wrong_export'
        bad_result=subprocess.run([sys.executable,str(ROOT/'scripts/build_vector_package.py'),
            '--project',str(wrong_proj),'--out',str(wo)],capture_output=True,text=True)
        assert bad_result.returncode!=0 and not (wo/'08_All_Files.zip').exists(),bad_result.stderr
        wrong_report=json.loads((wo/'quality_report.json').read_text('utf-8'))
        assert any(x['reason']=='explicit_order_conflicts_with_strong_visible_color_evidence'
            for x in wrong_report['geometry_failures'])
        # 13: valid explicit constraints reproduce reference with zero measured error,

        # and user can inspect actual SVG runs + provenance.
        proj2=make_demo(root/'valid',strict=False)
        out2=root/'valid_export'
        good=subprocess.run([sys.executable,str(ROOT/'scripts/build_vector_package.py'),
                             '--project',str(proj2),'--out',str(out2)],capture_output=True,text=True)
        assert good.returncode==0,good.stderr
        qa=json.loads((out2/'quality_report.json').read_text('utf-8'))
        assert qa['image_comparison']['mae_rgb_0_255']<.001
        assert qa['occlusion_v24_summary']['svg_layer_run_count']==6
        assert qa['occlusion_v24_summary']['no_hidden_anatomy_generated'] is True
        svg=etree.parse(str(out2/'01_Full_Illustration.svg'))
        assert len(svg.xpath('//*[local-name()="g" and @data-original-layer-id]'))==6
        import zipfile
        with zipfile.ZipFile(out2/'08_All_Files.zip') as z:
            assert {'15_Occlusion_Review.png','16_Occlusion_Stack.svg','17_Occlusion_Report.json'}.issubset(z.namelist())
    print('PASS: 13 occlusion groups (DAG, preserved layer runs, color evidence, ambiguity, no hidden paths, opt-in acceptance, strict QA, SVG+ZIP)')

if __name__=='__main__':run()
