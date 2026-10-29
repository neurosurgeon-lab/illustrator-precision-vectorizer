#!/usr/bin/env python3
"""Generate a NONCLINICAL, reproducible precision and variable-width example."""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]

def run(*args):subprocess.run([sys.executable,*map(str,args)],check=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path)
    root=p.parse_args().out.resolve();root.mkdir(parents=True,exist_ok=True)
    w,h,s=440,295,4
    big=Image.new('RGB',(w*s,h*s),'white');d=ImageDraw.Draw(big)
    skin='#FDEEE7';nerve='#64A5A1';accent='#9DBBD9'
    d.ellipse((61*s+1,36*s+2,216*s-1,268*s-2),fill=skin)
    # Nonanatomical illustrative taper; intentionally not a real vagus nerve.
    for x in range(249*s,416*s):
        t=(x-249*s)/(167*s)
        y=int((154+19*math.sin(1.5*math.pi*t))*s)
        r=int((2.2+5.1*t)*s)
        d.ellipse((x-r,y-r,x+r,y+r),fill=nerve)
    # A small separate device with a white interior / hole illustrates independent parts.
    d.ellipse((287*s,39*s,366*s,105*s),fill=accent)
    d.ellipse((307*s,54*s,345*s,91*s),fill='white')
    orig=big.resize((w,h),Image.Resampling.LANCZOS)
    src=root/'schematic_reference.png';orig.save(src)
    proj=root/'project'
    run(ROOT/'scripts/init_project.py','--image',src,'--out',proj)
    (proj/'masks').mkdir(exist_ok=True)
    a=np.asarray(orig.convert('RGB')).astype('float32')
    def m(color,threshold):
        return np.linalg.norm(a-np.array(color),axis=2)<threshold
    body=m([253,238,231],11);wire=m([100,165,161],62);device=m([157,187,217],63)
    # This demo knows its intended *single* device instance: discard tiny
    # anti-alias color-ring artifacts, never apply this to unknown anatomy.
    import cv2
    n,lab,stats,_=cv2.connectedComponentsWithStats(device.astype('uint8'),connectivity=8)
    device=(lab==(1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))))
    for name,mask in [('body',body),('nerve',wire),('device',device)]:
        Image.fromarray(mask.astype('uint8')*255).save(proj/'masks'/f'{name}.png')
    man=json.loads((proj/'manifest.json').read_text('utf-8'))
    man['layers']=[
       {'id':'00_background','name_zh':'背景','objects':[{'id':'white_background',
          'name_zh':'白色背景','geometry':{'type':'svg_path','d':f'M 0 0 H {w} V {h} H 0 Z'},
          'fill':'#FFFFFF','stroke':'none'}]},
       {'id':'01_body','name_zh':'主体填色','objects':[{'id':'body','name_zh':'主体轮廓','fill':skin,
          'stroke':'none','geometry':{'type':'mask_png','file':'masks/body.png'}}]},
       {'id':'02_nerve','name_zh':'变线宽神经示意','objects':[{'id':'nerve','name_zh':'神经样细线（非解剖图）',
          'fill':nerve,'stroke':'none','geometry':{'type':'mask_png','file':'masks/nerve.png'}}]},
       {'id':'03_device','name_zh':'设备环','objects':[{'id':'device','name_zh':'设备环示意',
          'fill':accent,'stroke':'none','geometry':{'type':'mask_png','file':'masks/device.png'}}]},
    ]
    man['modules']=[{'id':'body','name_zh':'亚像素轮廓主体','object_ids':['body']},
        {'id':'nerve','name_zh':'变线宽中心路径','object_ids':['nerve']},
        {'id':'device','name_zh':'带内孔设备','object_ids':['device']}]
    man['qa']['required_object_ids']=['white_background','body','nerve','device']
    # Synthetic demo only: quality report still retains numerical fidelity checks.
    man['qa']['fidelity_thresholds']={'max_mae_rgb':6,'max_mae_alpha':4,
        'max_changed_pixel_fraction':.10,'max_alpha_changed_fraction':.03,
        'max_edge_mismatch_fraction':.14}
    man['qa']['key_regions']=[{'name':'tapered_nerve','bbox':[238,127,192,76],
        'max_mae_rgb':10,'max_changed_pixel_fraction':.20,'max_mae_alpha':4}]
    (proj/'manifest.json').write_text(json.dumps(man,ensure_ascii=False,indent=2),'utf-8')
    run(ROOT/'scripts/subpixel_bezier.py','--project',proj,'--object-id','body','--write-manifest')
    run(ROOT/'scripts/subpixel_bezier.py','--project',proj,'--object-id','device','--min-native-iou','.94','--min-super-iou','.94','--write-manifest')
    run(ROOT/'scripts/variable_width.py','--project',proj,'--object-id','nerve','--write-manifest')
    run(ROOT/'scripts/build_vector_package.py','--project',proj,'--out',root/'export',
       '--hires-scale','2','--include-source-project','--allow-draft')
    print('Nonclinical precision demo:',root)
if __name__=='__main__':main()
