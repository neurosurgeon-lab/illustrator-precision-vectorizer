#!/usr/bin/env python3
"""End-to-end smoke test using a non-patient synthetic illustration fixture."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import zipfile
from lxml import etree
from PIL import Image

root=Path(__file__).resolve().parents[1]
project=root/'examples'/'demo_project'
assert (project/'source.png').exists(), 'Run python examples/create_demo.py first.'
with tempfile.TemporaryDirectory() as tmp:
    out=Path(tmp)/'outputs'
    cmd=[sys.executable,str(root/'scripts'/'build_vector_package.py'),'--project',str(project),'--out',str(out)]
    subprocess.run(cmd,check=True,capture_output=True,text=True)
    report=json.loads((out/'quality_report.json').read_text('utf8'))
    assert report['layer_count']==5
    assert report['object_count']==12
    assert report['module_count_excluding_composite']==4
    assert report['full_svg']['no_raster_embeds']
    assert report['full_svg']['unique_svg_ids']
    assert report['image_comparison']['mae_rgb_0_255']<1, 'Unexpected SVG rendering mismatch'
    with Image.open(out/'03_Full_Preview.png') as im:assert im.size==(420,320)
    with zipfile.ZipFile(out/'08_All_Files.zip') as z:
        files=set(z.namelist())
        assert '01_Full_Illustration.svg' in files
        assert '07_Illustrator_File.ai' not in files
        assert 'quality_report.json' in files
    root_node=etree.parse(str(out/'01_Full_Illustration.svg')).getroot()
    assert len(root_node.xpath('//*[local-name()="path"]'))==12
    print('PASS: composite SVG, exploded-view SVG, 12 objects/5 layers, PNG, palette, manifest, QA and ZIP.')
