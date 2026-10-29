#!/usr/bin/env python3
"""Assisted color-connected segmentation with one user/model-confirmed seed per object.

This is NOT semantic image understanding. Anti-aliased/overlapping objects, wires,
shadows and color reuse often require manual repair. No automatic medical labels.
"""
import argparse
import json
import re
from pathlib import Path
import cv2
import numpy as np
from PIL import Image


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,required=True)
    p.add_argument('--seeds',type=Path,required=True,help='JSON {objects:[{id,x,y,name_zh,layer_id,tolerance?}]}')
    p.add_argument('--max-area-fraction',type=float,default=.75)
    a=p.parse_args()
    root=a.project.resolve(); manifest_path=root/'manifest.json'
    man=json.loads(manifest_path.read_text('utf-8'))
    if man.get('layers'):raise ValueError('Project already has layers; refusing to overwrite hand-edited manifest')
    source=(root/man['source_image']).resolve()
    if not source.is_relative_to(root) or not source.is_file():raise ValueError('Invalid source file')
    rgba=np.asarray(Image.open(source).convert('RGBA'))
    h,w=rgba.shape[:2];rgb=rgba[:,:,:3]
    lab=cv2.cvtColor(rgb,cv2.COLOR_RGB2LAB).astype(np.int16)
    seeds=json.loads(a.seeds.read_text('utf-8'))['objects']
    layers={}
    (root/'masks').mkdir(exist_ok=True)
    for ob in seeds:
        oid=ob['id'];x=int(ob['x']);y=int(ob['y'])
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*',oid):raise ValueError('Unsafe object ID')
        if not (0<=x<w and 0<=y<h):raise ValueError(f'{oid}: seed outside image')
        tol=float(ob.get('tolerance',10.0))
        if not 0<=tol<=70:raise ValueError('tolerance must be 0..70 LAB units (OpenCV 8-bit)')
        # Local Lab Euclidean difference; this is not CIEDE2000.
        d=np.sqrt(np.square(lab.astype(float)-lab[y,x].astype(float)).sum(axis=-1))
        candidate=((d<=tol)&(rgba[:,:,3]>=128)).astype(np.uint8)
        n,labels,stats,_=cv2.connectedComponentsWithStats(candidate,8)
        component=labels[y,x]
        if component==0:raise ValueError(f'{oid}: seed has no eligible foreground')
        mask=(labels==component).astype(np.uint8)*255
        count=int(mask.sum()//255)
        if count>=w*h*a.max_area_fraction:
            raise ValueError(f'{oid}: region occupies {count/(w*h):.1%}; check whether you selected background')
        Image.fromarray(mask).save(root/'masks'/f'{oid}.png')
        pixels=rgb[mask>0].reshape(-1,3)
        color=np.median(pixels,axis=0).round().astype('uint8')
        hex_color='#'+''.join(f'{int(v):02X}' for v in color)
        lid=ob.get('layer_id','01_assisted_fills')
        if lid not in layers:layers[lid]={'id':lid,'name_zh':ob.get('layer_name_zh','辅助分割填色'),'objects':[]}
        layers[lid]['objects'].append({'id':oid,'name_zh':ob.get('name_zh',oid),'name_en':ob.get('name_en',oid),
            'geometry':{'type':'mask_png','file':f'masks/{oid}.png'},'fill':hex_color,'stroke':'none',
            'notes':f'Seed-assisted LAB segmentation x={x} y={y} tolerance={tol}; manual verification required'})
        print(f'{oid}: {count} pixels, {hex_color}, layer {lid}')
    man['layers']=list(layers.values());man['modules']=[{'id':'module_'+str(i+1),'name_zh':v['name_zh'],'layer_ids':[lid]} for i,(lid,v) in enumerate(layers.items())]
    man.setdefault('qa',{}).setdefault('unresolved_details',[]).append('种子点颜色分割仅是辅助路径，尚未人工验证全部边界和对象完整性。')
    manifest_path.write_text(json.dumps(man,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Added seed masks and draft layer manifest; audit each object before release')


if __name__=='__main__':main()
