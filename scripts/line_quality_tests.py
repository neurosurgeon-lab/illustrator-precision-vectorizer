#!/usr/bin/env python3
"""A pixel-perfect source must still be blocked without a current complete line review."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
from PIL import Image

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'examples'))
from create_editable_v33_demo import create


def checks(root):
    project=create(root/'project')
    def export(name,*options):
        out=root/name
        result=subprocess.run([sys.executable,str(HERE/'build_vector_package.py'),
            '--project',str(project),'--out',str(out),'--require-line-quality-review',*options],capture_output=True,text=True)
        return out,result,json.loads((out/'quality_report.json').read_text())
    out,result,report=export('missing')
    assert result.returncode==2 and not (out/'08_All_Files.zip').exists()
    assert not report['fidelity_failures'] and report['editability']['quality_gates_passed']
    assert report['line_quality']['status']=='blocked' and not report['quality_gates_passed']
    assert Image.open(out/'13_HiRes_Preview.png').size==(1280,960)
    contract=report['line_quality']
    # Synthetic fixture only: never generate approvals for user artwork this way.
    review={'svg_sha256':contract['svg_sha256'],'source_sha256':contract['source_sha256'],
            'reviewed_scale':4,'reviewer':'synthetic_regression_fixture',
            'objects':[{'object_id':oid,'no_unintended_gaps':True,'no_jagged_edges':True,'source_matched':True}
                       for oid in contract['required_object_ids']]}
    path=project/'line_quality_review.json'
    def write(value):path.write_text(json.dumps(value))
    write(review)
    out,result,report=export('reviewed')
    assert result.returncode==0,result.stderr
    assert report['quality_gates_passed'] and report['line_quality']['status']=='reviewed_pass'
    with zipfile.ZipFile(out/'08_All_Files.zip') as bundle:assert '26_Line_Quality_Report.json' in bundle.namelist()
    assert hashlib.sha256((out/'01_Full_Illustration.svg').read_bytes()).hexdigest()==review['svg_sha256']
    incomplete=copy.deepcopy(review);incomplete['objects'].pop();write(incomplete)
    out,result,report=export('missing_object')
    assert result.returncode==2 and not (out/'08_All_Files.zip').exists()
    malformed=copy.deepcopy(review);malformed['objects'][0]['no_jagged_edges']='true';write(malformed)
    out,result,report=export('string_boolean')
    assert result.returncode==2
    stale=copy.deepcopy(review);stale['svg_sha256']='0'*64;write(stale)
    out,result,report=export('stale')
    assert result.returncode==2 and report['line_quality']['failures'][0]['reason']=='line_quality_review_stale'
    write({**review,'reviewed_scale':2})
    out,result,report=export('too_small')
    assert result.returncode==2
    path.unlink()
    out,result,report=export('explicit_draft','--allow-draft')
    assert result.returncode==0 and (out/'08_All_Files.zip').exists() and not report['quality_gates_passed']
    # A manifest requirement also applies when the CLI flag is absent.
    manifest=json.loads((project/'manifest.json').read_text());manifest['qa']['require_line_quality_review']=True
    (project/'manifest.json').write_text(json.dumps(manifest))
    out=root/'manifest_required'
    result=subprocess.run([sys.executable,str(HERE/'build_vector_package.py'),'--project',str(project),'--out',str(out)],capture_output=True,text=True)
    assert result.returncode==2 and not (out/'08_All_Files.zip').exists()


if __name__=='__main__':
    with tempfile.TemporaryDirectory() as directory:checks(Path(directory))
    print('PASS: pixel-pass/review-missing block, 4x preview, complete review, missing objects, strict booleans, stale hash, scale, explicit draft and manifest enforcement')
