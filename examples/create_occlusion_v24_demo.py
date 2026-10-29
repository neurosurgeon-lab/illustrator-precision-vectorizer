#!/usr/bin/env python3
"""Nonclinical schematic: source stack is known; input Manifest intentionally mis-ordered.

The demo does not infer hidden anatomy. All paths were authored before source raster.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_vector_package import build_object,render,root_svg


def make_demo(root,strict=True):
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    w,h=390,265
    source=root/'synthetic_reference.png'
    Image.new('RGB',(w,h),'white').save(source)
    project=root/'project'
    subprocess.run([sys.executable,str(ROOT/'scripts/init_project.py'),'--image',str(source), '--out',str(project)],check=True,capture_output=True)
    man=json.loads((project/'manifest.json').read_text('utf-8'))
    def item(name,d,fill='none',stroke='none',sw=1,hidden=False):
        return {'id':name,'name_zh':name.replace('_',' '),'name_en':name,
            'geometry':{'type':'svg_path','d':d},'fill':fill,'stroke':stroke,'stroke_width':sw,
            'stroke_linecap':'round','inferred_hidden':hidden,
            'geometry_provenance':'author_supplied_vector'}
    man['layers']=[
      {'id':'L00_background','name_zh':'背景','objects':[item('background','M 0 0 H 390 V 265 H 0 Z','#FFFFFF')]},
      {'id':'L01_body','name_zh':'头肩示意','objects':[item('body','M 78 227 C 49 202 56 137 72 95 C 93 42 161 37 186 86 C 203 125 201 187 231 227 Z','#FDEEE7', '#C6ADB0',1.7)]},
      # One semantic device layer contains two pieces that need splitting into non-contiguous z-runs.
      {'id':'L02_device','name_zh':'设备部件','objects':[
           item('device_base','M 186 67 H 264 Q 273 67 273 76 V 107 Q 273 116 264 116 H 186 Q 177 116 177 107 V 76 Q 177 67 186 67 Z','#CFDBE9','#7692AE',2),
           item('electrode_cap','M 255 144 A 25 25 0 1 1 205 144 A 25 25 0 1 1 255 144 Z','#AFBED4','#5D7794',2)]},
      {'id':'L03_nerve','name_zh':'神经样曲线','objects':[
           item('nerve','M 118 68 C 127 100 155 109 173 146 C 194 177 223 172 258 213',stroke='#62A6A1',sw=11)]},
      {'id':'L04_wire','name_zh':'连接导线','objects':[
           item('wire','M 70 199 C 131 191 162 173 195 162 C 248 144 287 115 341 130',stroke='#7B95BB',sw=10)]}
    ]
    man['modules']=[{'id':'m_body','name_zh':'主体与背景','object_ids':['body']},
        {'id':'m_device','name_zh':'独立设备部件','object_ids':['device_base','electrode_cap']},
        {'id':'m_nerve','name_zh':'神经样线条','object_ids':['nerve']},
        {'id':'m_wire','name_zh':'独立导线','object_ids':['wire']}]
    # Ground truth is the author-created drawing, not inferred geometry.
    right=['background','body','device_base','nerve','wire','electrode_cap']
    elements={obj['id']:build_object(obj,project,w,h,0,'polygon')[0]
              for l in man['layers'] for obj in l['objects']}
    svg=root_svg(w,h)
    for oid in right:svg.append(elements[oid])
    render(svg,source)
    render(svg,project/'source.png')
    man['source_sha256']=hashlib.sha256((project/'source.png').read_bytes()).hexdigest()
    man['occlusion']={'constraints':[
       {'behind':'device_base','front':'nerve','source':'user_confirmed'},
       {'behind':'nerve','front':'wire','source':'user_confirmed'},
       {'behind':'wire','front':'electrode_cap','source':'user_confirmed'}],
       'exclude_from_inference':['background']}
    man['qa']={'require_resolved_occlusions':strict,
       'required_object_ids':right,
       'fidelity_thresholds':{'max_mae_rgb':1,'max_mae_alpha':1,
          'max_changed_pixel_fraction':.005,'max_alpha_changed_fraction':.005,
          'max_edge_mismatch_fraction':.01},
       'unresolved_details':['Synthetic source authored from full vector geometry; hidden line segments are not inferred from raster.'],
       'illustrator_native_verified':False}
    (project/'manifest.json').write_text(json.dumps(man,ensure_ascii=False,indent=2),encoding='utf-8')
    return project


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path)
    args=p.parse_args()
    root=args.out.resolve();proj=make_demo(root,strict=False)
    subprocess.run([sys.executable,str(ROOT/'scripts/occlusion_layers.py'), '--project',str(proj),
                    '--out',str(root/'occlusion_analysis')],check=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/build_vector_package.py'),
         '--project',str(proj),'--out',str(root/'export'),'--hires-scale','2',
         '--include-source-project'],check=True)
    print('Generated nonclinical overlap demo in',root)

if __name__=='__main__':main()
