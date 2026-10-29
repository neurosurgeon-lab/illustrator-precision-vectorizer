#!/usr/bin/env python3
"""Synthetic non-patient fixture for modal/amodal and occlusion review."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image,ImageDraw
import numpy as np

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    root=a.out.resolve();root.mkdir(parents=True,exist_ok=True)
    (root/'masks').mkdir(exist_ok=True)
    w,h=480,260
    src=Image.new('RGB',(w,h),'white');draw=ImageDraw.Draw(src)
    # Back line runs underneath the housing, and a short nearby fragment.
    draw.line([(42,112),(210,112)],fill='#6B91AB',width=13)
    draw.line([(264,112),(427,112)],fill='#6B91AB',width=13)
    draw.rectangle((211,55,264,175),fill='#C7D7E7',outline='#6B839B',width=3)
    draw.ellipse((224,96,249,121),fill='#EDF3F8',outline='#6B839B',width=2)
    src.save(root/'source.png')
    line=Image.new('L',(w,h),0);ld=ImageDraw.Draw(line)
    ld.line([(42,112),(210,112)],fill=255,width=13)
    ld.line([(264,112),(427,112)],fill=255,width=13)
    line.save(root/'masks'/'wire.png')
    block=Image.new('L',(w,h),0);ImageDraw.Draw(block).rectangle((211,55,264,175),fill=255)
    block.save(root/'masks'/'housing.png')
    circle=Image.new('L',(w,h),0);ImageDraw.Draw(circle).ellipse((224,96,249,121),fill=255)
    circle.save(root/'masks'/'button.png')
    objects=[('wire','导线','masks/wire.png','#6B91AB'),('housing','设备外壳','masks/housing.png','#C7D7E7'),('button','电极触点','masks/button.png','#EDF3F8')]
    layers=[];modules=[]
    for i,(oid,title,file,col) in enumerate(objects):
        lid=f'{i+1:02d}_{oid}'
        layers.append({'id':lid,'name_zh':title,'name_en':oid,'objects':[{'id':oid,'name_zh':title,'name_en':oid,
            'geometry':{'type':'mask_png','file':file},'fill':col,'stroke':'none'}]})
        modules.append({'id':f'mod_{oid}','name_zh':title,'object_ids':[oid]})
    manifest={'schema_version':'1.0','source_image':'source.png',
        'source_sha256':hashlib.sha256((root/'source.png').read_bytes()).hexdigest(),
        'canvas':{'width':w,'height':h},'layers':layers,'modules':modules,
        'qa':{'unresolved_details':['合成演示：曲线的隐藏连接仅供审核，不代表真实医学解剖。']}}
    (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
    completion={'objects':[{'id':'wire','occluder_ids':['housing'],'occluded_endpoints':[[210,112],[264,112]],
                'thickness':13,'approve_hidden':False,'max_hidden_length':90}]}
    (root/'completion_annotations.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2),'utf-8')
    print(root)
if __name__=='__main__':main()
