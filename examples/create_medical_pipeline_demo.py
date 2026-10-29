#!/usr/bin/env python3
"""Create a reproducible nonclinical schematic to exercise guided segmentation + tracing.

All shapes are synthetic (not medically accurate or suitable for procedural use).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
INIT=ROOT/'scripts/init_project.py'
SEG=ROOT/'scripts/medical_instance_segment.py'
TRACE=ROOT/'scripts/centerline_trace.py'
BUILD=ROOT/'scripts/build_vector_package.py'


def run(*args):
    subprocess.run([sys.executable,*map(str,args)],check=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    img=Image.new('RGB',(520,340),'white'); d=ImageDraw.Draw(img)
    skin='#FDEEE7';nerve='#64A5A1';cable='#6686B2';electrode='#E5A29E';device='#B3C9DE'
    # Generic head + neck + shoulders silhouette: intentionally schematic.
    d.ellipse([127,33,240,182],fill=skin)
    d.rectangle([156,160,210,260],fill=skin)
    d.polygon([(155,225),(217,224),(277,262),(311,340),(90,340),(104,266)],fill=skin)
    d.line([(183,221),(183,151)],fill=nerve,width=6)
    d.line([(183,151),(156,119)],fill=nerve,width=6)
    d.line([(183,151),(209,117)],fill=nerve,width=6)
    d.line([(183,212),(245,220),(284,244),(343,251)],fill=cable,width=6)
    d.ellipse([319,225,373,279],fill=device)
    d.ellipse([334,239,358,265],fill='#E9F1F8')
    d.ellipse([149,113,164,127],fill=electrode)
    d.ellipse([201,111,216,125],fill=electrode)
    orig=out/'schematic_reference.png';img.save(orig)
    project=out/'project';run(INIT,'--image',orig,'--out',project)
    instructions={'instances':[
       {'id':'body_visible','name_zh':'人体可见填色','name_en':'Body visible fill','method':'seed_lab','bbox':[82,25,237,315], 'fg_points':[[180,80],[183,272]], 'lab_tolerance':1,'layer_id':'01_body'},
       {'id':'nerve_trunk','name_zh':'神经示意线','name_en':'Nerve schematic','method':'seed_lab','bbox':[145,108,72,121], 'fg_points':[[183,176],[170,135],[196,135]], 'lab_tolerance':1, 'layer_id':'02_nerve'},
       {'id':'lead_wire','name_zh':'设备导线','name_en':'Lead cable','method':'seed_lab','bbox':[174,205,173,58], 'fg_points':[[242,220]], 'lab_tolerance':1,'layer_id':'03_lead'},
       {'id':'pulse_generator','name_zh':'刺激器外壳','name_en':'Device housing','method':'seed_lab','bbox':[317,222,60,60], 'fg_points':[[325,245]], 'lab_tolerance':1, 'layer_id':'04_device'},
       {'id':'generator_center','name_zh':'刺激器中心','name_en':'Device center','method':'seed_lab','bbox':[330,235,35,35], 'fg_points':[[345,250]], 'lab_tolerance':1,'layer_id':'05_device_detail'},
       {'id':'electrode_01','name_zh':'电极一','name_en':'Electrode 01','method':'seed_lab','bbox':[145,107,23,25], 'fg_points':[[155,120]], 'lab_tolerance':1,'layer_id':'06_electrodes'},
       {'id':'electrode_02','name_zh':'电极二','name_en':'Electrode 02','method':'seed_lab','bbox':[197,105,24,25], 'fg_points':[[209,119]], 'lab_tolerance':1,'layer_id':'06_electrodes'}]}
    ann=out/'annotations.json';ann.write_text(json.dumps(instructions,ensure_ascii=False,indent=2),encoding='utf-8')
    run(SEG,'--project',project,'--annotations',ann)
    # Keep nerve & wire source masks intact on disk while converting edit geometry
    # to center paths; the generator should be able to accept stroke objects.
    run(TRACE,'--project',project,'--object-id','nerve_trunk','--write-manifest','--min-iou','.80')
    run(TRACE,'--project',project,'--object-id','lead_wire','--write-manifest','--min-iou','.80')
    manpath=project/'manifest.json';man=json.loads(manpath.read_text('utf-8'))
    man['layers'].insert(0,{'id':'00_background','name_zh':'白色背景','objects':[
        {'id':'background_white','name_zh':'背景','geometry':{'type':'svg_path','d':'M 0 0 H 520 V 340 H 0 Z'},
         'fill':'#FFFFFF','stroke':'none'}]})
    man['modules'].insert(0,{'id':'background_module','name_zh':'背景','layer_ids':['00_background']})
    man['qa']['required_object_ids']=['background_white','body_visible','pulse_generator','electrode_01','electrode_02']
    manpath.write_text(json.dumps(man,ensure_ascii=False,indent=2),encoding='utf-8')
    run(BUILD,'--project',project,'--out',out/'export','--allow-draft','--hires-scale','2','--include-source-project')
    print('Synthetic demo ready:',out)

if __name__=='__main__':main()
