#!/usr/bin/env python3
"""nonclinical geometry, batch and OCR regression tests (no real OCR model)."""
from pathlib import Path
import json
import sys
import tempfile
import hashlib
import zipfile
import numpy as np
import cv2
from PIL import Image, ImageDraw
from lxml import etree
from amodal_completion import propose_short_gaps,infer_occluded_connection,generate,components
from text_recognition import make_text_items,append_approved_text,run_ocr
from build_vector_package import root_svg,to_xml
from batch_vectorize import process_batch
from subprocess import run

HERE=Path(__file__).resolve().parent

def test_gap_and_fragments():
    m=np.zeros((65,120),bool);m[30:35,8:63]=1;m[30:35,69:77]=1
    suggestions,candidate=propose_short_gaps(m,max_gap=10,max_fragment_fraction=.3)
    assert suggestions[0]['status']=='proposed_short_gap',suggestions
    assert len(components(candidate)[0])==1
    blocked=np.zeros_like(m);blocked[30:35,63:70]=True
    suggestion,other=propose_short_gaps(m,max_gap=10,forbidden=blocked)
    assert suggestion[0]['status']=='blocked_other_object' and np.array_equal(m,other)
    suggestions,_=propose_short_gaps(m,max_gap=2)
    assert suggestions[0]['status']=='needs_manual_review'
    assert len(components(m)[0])==2

def test_hidden_only_in_occluder():
    m=np.zeros((70,120),bool);m[30:33,10:48]=1;m[30:33,73:101]=1
    oc=np.zeros_like(m);oc[20:43,45:78]=1
    inferred=infer_occluded_connection(m,oc,[[47,31],[73,31]],2)
    assert inferred.sum()>0 and not (inferred&~oc).any() and not (inferred&m).any()
    try:infer_occluded_connection(m,oc,[[50,31],[73,31]],2)
    except ValueError:pass
    else:raise AssertionError('Nonobserved start must be rejected')

def project_fixture(root):
    p=root/'project';(p/'masks').mkdir(parents=True)
    im=Image.new('RGB',(140,90),'white');d=ImageDraw.Draw(im)
    d.rectangle((10,33,51,38),fill='#6688AA');d.rectangle((70,33,110,38),fill='#6688AA')
    d.rectangle((52,17,69,54),fill='#CC8866')
    src=p/'source.png';im.save(src)
    m=np.zeros((90,140),np.uint8);m[33:39,10:52]=255;m[33:39,70:111]=255
    Image.fromarray(m).save(p/'masks/line.png')
    mask=np.zeros_like(m);mask[17:55,52:70]=255
    Image.fromarray(mask).save(p/'masks/block.png')
    man={'schema_version':'1.0','source_image':'source.png','source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),
         'canvas':{'width':140,'height':90},'layers':[
         {'id':'01_line','name_zh':'导线','objects':[{'id':'line','name_zh':'导线','geometry':{'type':'mask_png','file':'masks/line.png'},'fill':'#6688AA','stroke':'none'}]},
         {'id':'02_block','name_zh':'设备','objects':[{'id':'block','name_zh':'设备','geometry':{'type':'mask_png','file':'masks/block.png'},'fill':'#CC8866','stroke':'none'}]}],
         'modules':[{'id':'m1','name_zh':'线','object_ids':['line']},{'id':'m2','name_zh':'遮挡物','object_ids':['block']}],
         'qa':{}}
    (p/'manifest.json').write_text(json.dumps(man,ensure_ascii=False),encoding='utf-8')
    return p

def test_amodal_dual_and_review(tmp):
    project=project_fixture(tmp)
    output=tmp/'export'
    run([sys.executable,str(HERE/'build_vector_package.py'),'--project',str(project),'--out',str(output),'--allow-draft'],check=True,capture_output=True,text=True)
    cfg={'objects':[{'id':'line','occluder_ids':['block'],'occluded_endpoints':[[51,35],[70,35]],'thickness':5}]}
    # Separate invocation uses existing modal SVG, never overwrites it.
    a=tmp/'completion.json';a.write_text(json.dumps(cfg),'utf-8')
    before=(output/'01_Full_Illustration.svg').read_bytes()
    report=generate(project,output,a)
    assert before==(output/'18_Modal_Illustration.svg').read_bytes()
    assert report['modal_source_unchanged']
    assert report['objects'][0]['occlusion_hypothesis']['status']=='awaits_explicit_approval'
    cand=etree.parse(str(output/'22_Unapproved_Completion_Candidates.svg'))
    assert cand.xpath('//*[local-name()="path" and @data-proposal-unapproved="true"]')
    approved=dict(cfg);approved['objects']=[dict(cfg['objects'][0],approve_hidden=True)]
    a.write_text(json.dumps(approved),'utf-8')
    report=generate(project,output,a)
    assert report['objects'][0]['approved_hidden_pixels']>0
    am=etree.parse(str(output/'19_Amodal_Isolated_Objects.svg'))
    assert am.xpath('//*[local-name()="path" and @data-inferred="true"]')
    assert before==(output/'01_Full_Illustration.svg').read_bytes()
    with zipfile.ZipFile(output/'08_All_Files.zip') as z:
        for name in ['18_Modal_Illustration.svg','19_Amodal_Isolated_Objects.svg','22_Unapproved_Completion_Candidates.svg']:
            assert name in z.namelist(),name

def test_ocr_review():
    fake={'text':['VNS','', '神经','2A'],'left':[5,0,33,60],'top':[8,0,8,8],
          'width':[22,0,20,10],'height':[11,0,12,10],'conf':['97','-1','87','40']}
    review=make_text_items(fake,confidence_cutoff=70)
    assert len(review)==3 and review[-1]['status']=='low_confidence_review'
    review[0]['approved']=True;review[0]['corrected_text']='VNS-DBS';review[0]['font_family']='Arial'
    review[1]['approved']=False
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'text_review.json'
        payload={'source_sha256':'abc','items':review}
        path.write_text(json.dumps(payload,ensure_ascii=False),'utf-8')
        svg=root_svg(140,90)
        active=append_approved_text(svg,path,'abc',140,90)
        assert len(active)==1 and active[0]['text']=='VNS-DBS'
        assert etree.fromstring(to_xml(svg)).xpath('//*[local-name()="text" and text()="VNS-DBS"]')
        try:append_approved_text(root_svg(140,90),path,'BAD_HASH',140,90)
        except ValueError:pass
        else:raise AssertionError('OCR source hash mismatch not rejected')
        review[0]['corrected_text']='<script>unsafe</script>'
        path.write_text(json.dumps({'source_sha256':'abc','items':review},ensure_ascii=False),'utf-8')
        svg=root_svg(140,90);append_approved_text(svg,path,'abc',140,90)
        assert not svg.xpath('//*[local-name()="script"]')

def test_ocr_layer_in_full_and_amodal(tmp):
    project=project_fixture(tmp)
    man=json.loads((project/'manifest.json').read_text('utf-8'))
    review={'source_sha256':man['source_sha256'], 'items':[{'id':'ocr_0001','text':'VNS',
      'corrected_text':'VNS 120 Hz','bbox':[15,7,90,17],'confidence':98,
      'font_family':'DejaVu Sans','font_size':17,'fill':'#222222','approved':True}]}
    (project/'text_review.json').write_text(json.dumps(review),'utf-8')
    out=tmp/'export'
    run([sys.executable,str(HERE/'build_vector_package.py'),'--project',str(project),
         '--out',str(out),'--allow-draft'],check=True,capture_output=True,text=True)
    for name in ['01_Full_Illustration.svg','02_Layer_Breakdown.svg','19_Amodal_Isolated_Objects.svg']:
        tree=etree.parse(str(out/name))
        assert tree.xpath('//*[local-name()="text" and text()="VNS 120 Hz"]'),name
    report=json.loads((out/'quality_report.json').read_text('utf-8'))
    assert report['reviewed_editable_text_count']==1
    assert json.loads((out/'20_Completion_Report.json').read_text('utf-8'))['reviewed_text_count']==1
    with zipfile.ZipFile(out/'08_All_Files.zip') as z:
        assert not any('text_review.json'==f for f in z.namelist())


def test_batch_isolation(tmp):
    folder=tmp/'incoming';folder.mkdir()
    Image.new('RGB',(80,60),'white').save(folder/'no_annotations.png')
    project=project_fixture(tmp/'seed')
    # batch input supports existing project folder; no manual JSON necessary.
    import shutil
    shutil.copytree(project,folder/'prepared_project')
    report=process_batch(folder,tmp/'batch_exports',mixed=True,allow_draft=True)
    states={r['status'] for r in report['items']}
    assert 'needs_annotations' in states,report
    assert 'draft' in states,report
    for r in report['items']:
        if r['status']=='draft':
            with zipfile.ZipFile(Path(r['output'])/'export/08_All_Files.zip') as z:
                assert '19_Amodal_Isolated_Objects.svg' in z.namelist()
    assert (tmp/'batch_exports/batch_summary.csv').exists()

def test_review_boundaries_and_recursive_batch(tmp):
    import shutil
    folder=tmp/'inputs';folder.mkdir()
    for name in ('a','b'):
        (folder/name).mkdir()
        Image.new('RGB',(80,60),'white').save(folder/name/'same.png')
    project=project_fixture(tmp/'seed')
    shutil.copytree(project,folder/'prepared')
    completion=tmp/'completion';completion.mkdir()
    settings={'objects':[{'id':'line','occluder_ids':['block'],'occluded_endpoints':[[51,35],[70,35]],
                         'thickness':5,'approve_hidden':True}]}
    (completion/'prepared.completion.json').write_text(json.dumps(settings))
    prior=folder/'prepared/prior_review.json';prior.write_text('{}')
    (folder/'prepared/completion_annotations.json').symlink_to(prior.resolve())
    source_hashes={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
    report=process_batch(folder,tmp/'out',mixed=True,recursive=True,completion_annotations=completion,allow_draft=True)
    assert len(report['items'])==3 and report['counts']['needs_annotations']==2,report
    assert (tmp/'out/a/same.png/project/manifest.json').exists()
    assert (tmp/'out/b/same.png/project/manifest.json').exists()
    after={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
    assert source_hashes==after,'Input projects were modified'
    export=tmp/'out/prepared/export'
    with zipfile.ZipFile(export/'08_All_Files.zip') as z:
        assert len(z.namelist())==len(set(z.namelist()))
        for name in ('19_Amodal_Isolated_Objects.svg','20_Completion_Report.json','23_Amodal_Approval_Review.svg'):
            assert z.read(name)==(export/name).read_bytes(),'Stale packaged completion: '+name
        assert json.loads(z.read('20_Completion_Report.json'))['objects'][0]['approved_hidden_pixels']>0
    bad=tmp/'invalid.json'
    settings['objects'][0]['approve_hidden']='false'
    bad.write_text(json.dumps(settings))
    try:generate(project,export,bad)
    except ValueError as exc:assert 'boolean' in str(exc)
    else:raise AssertionError('String approval accepted')
    review=project/'text_review.json'
    review.write_text(json.dumps({'source_sha256':'abc','items':[{'approved':'false'}]}))
    try:append_approved_text(root_svg(140,90),review,'abc',140,90)
    except ValueError as exc:assert 'boolean' in str(exc)
    else:raise AssertionError('String OCR approval accepted')
    original=review.read_bytes()
    try:run_ocr(project)
    except ValueError as exc:assert 'already exists' in str(exc)
    else:raise AssertionError('Existing OCR review overwritten')
    assert review.read_bytes()==original
    # Project-relative files must not escape the source project.
    from amodal_completion import visible_mask
    try:visible_mask(project,{'geometry':{'type':'mask_png','file':'../outside.png'}},140,90)
    except ValueError as exc:assert 'escapes' in str(exc)
    else:raise AssertionError('Mask path escape accepted')


def test_transformed_completion(tmp):
    from amodal_completion import visible_mask
    project=project_fixture(tmp)
    manifest=json.loads((project/'manifest.json').read_text())
    spec=manifest['layers'][0]['objects'][0];spec['transform']='translate(3 0)'
    (project/'manifest.json').write_text(json.dumps(manifest))
    raw=visible_mask(project,spec,140,90)
    assert not raw[35,10] and raw[35,13],'Mask ignored source transform'
    settings={'objects':[{'id':'line','occluder_ids':['block'],'occluded_endpoints':[[51,35],[73,35]],'thickness':4,'approve_hidden':True}]}
    (project/'completion_annotations.json').write_text(json.dumps(settings))
    out=tmp/'export'
    run([sys.executable,str(HERE/'build_vector_package.py'),'--project',str(project),'--out',str(out),'--allow-draft'],check=True,capture_output=True,text=True)
    am=etree.parse(str(out/'19_Amodal_Isolated_Objects.svg'))
    inferred=am.xpath('//*[local-name()="path" and @data-inferred="true"]')[0]
    assert inferred.getparent().get('transform') is None,'Canvas-space addition was transformed twice'
    assert am.xpath('//*[local-name()="g" and @transform="translate(3 0)"]'),'Original transform lost'
    cand=etree.parse(str(out/'22_Unapproved_Completion_Candidates.svg'))
    assert len(cand.xpath('//*[local-name()="g" and @data-amodal-panel]'))==2


def main():
    test_gap_and_fragments();print('PASS gap repair proposed, forbidden region protected')
    test_hidden_only_in_occluder();print('PASS hidden hypothesis stays under occluder')
    with tempfile.TemporaryDirectory() as t:test_amodal_dual_and_review(Path(t))
    print('PASS modal unchanged, amodal approved, unapproved candidate visible, ZIP')
    test_ocr_review();print('PASS OCR JSON review and editable, XML-safe text')
    with tempfile.TemporaryDirectory() as t:test_ocr_layer_in_full_and_amodal(Path(t))
    print('PASS approved OCR included as independent text in full/breakdown/amodal SVG')
    with tempfile.TemporaryDirectory() as t:test_batch_isolation(Path(t))
    print('PASS batch mixed prepared/unannotated jobs and failure isolation')
    with tempfile.TemporaryDirectory() as t:test_review_boundaries_and_recursive_batch(Path(t))
    print('PASS strict approvals, recursive isolation, source protection, fresh ZIP and OCR review preservation')
    with tempfile.TemporaryDirectory() as t:test_transformed_completion(Path(t))
    print('PASS transformed geometry and canvas-space additions retain independent coordinates')

if __name__=='__main__':main()
