#!/usr/bin/env python3
"""Generate a small SYNTHETIC (not patient-derived) smoke-test picture and manifest."""
from pathlib import Path
from PIL import Image,ImageDraw
import cairosvg
import json
root=Path(__file__).resolve().parent/'demo_project';root.mkdir(parents=True,exist_ok=True)
(root/'masks').mkdir(exist_ok=True)
w,h=420,320
head=Image.new('L',(w,h),0)
d=ImageDraw.Draw(head)
d.ellipse([143,81,287,274],fill=255)
head.save(root/'masks'/'head.png')

# Hand paths for the cap and wires; masks are used only for one semantic object.
cap='M 149,154 C 145,98 177,68 216,67 C 270,65 298,99 284,153 C 244,135 197,133 149,154 Z'
edge='M 149,154 C 186,137 249,135 284,153'
wire1='M 176,119 C 116,127 92,174 83,208 C 77,232 65,242 43,250'
wire2='M 255,117 C 300,128 340,180 346,211 C 351,231 367,246 389,254'

layers=[
 {'id':'00_background','name_zh':'背景','name_en':'Background','objects':[
     {'id':'background','name_zh':'白色背景','name_en':'White BG','geometry':{'type':'svg_path','d':f'M 0,0 H {w} V {h} H 0 Z'},'bbox':[0,0,w,h],'fill':'#FFFFFF','stroke':'none'}]},
 {'id':'01_head','name_zh':'头部基础填色','name_en':'Head Fill','objects':[
     {'id':'head_fill','name_zh':'头部','name_en':'Head','geometry':{'type':'mask_png','file':'masks/head.png'},'fill':'#FDEEE7','stroke':'none'}]},
 {'id':'02_cap','name_zh':'脑电帽','name_en':'EEG Cap','objects':[
     {'id':'cap_base','name_zh':'帽体','name_en':'Cap Base','geometry':{'type':'svg_path','d':cap},'bbox':[145,65,154,92],'fill':'#BBD4EA','stroke':'#8FADCA','stroke_width':2},
     {'id':'cap_edge','name_zh':'帽体下缘','name_en':'Cap Lower Rim','geometry':{'type':'svg_path','d':edge},'bbox':[148,134,137,22],'fill':'none','stroke':'#8FADCA','stroke_width':2}]},
 {'id':'03_electrodes','name_zh':'独立电极','name_en':'Electrodes','objects':[]},
 {'id':'04_cables','name_zh':'导线','name_en':'Cables','objects':[
     {'id':'cable_left','name_zh':'左侧导线','name_en':'Left Cable','geometry':{'type':'svg_path','d':wire1},'bbox':[43,117,135,136],'fill':'none','stroke':'#7195B7','stroke_width':3},
     {'id':'cable_right','name_zh':'右侧导线','name_en':'Right Cable','geometry':{'type':'svg_path','d':wire2},'bbox':[255,117,134,137],'fill':'none','stroke':'#7195B7','stroke_width':3}]}
]
coords=[(176,118),(215,93),(255,118)]
for idx,(cx,cy) in enumerate(coords,1):
 for name,r,fill,stroke in [('outer',12,'#F7FAFD','#7195B7'),('contact',5,'#7195B7','none')]:
  layers[3]['objects'].append({'id':f'electrode_{idx:02d}_{name}',
      'name_zh':f'电极 {idx} '+('外圈' if name=='outer' else '接触点'),'name_en':f'Electrode {idx} {name}',
      'geometry':{'type':'svg_path','d':f'M {cx-r},{cy} A {r},{r} 0 1 0 {cx+r},{cy} A {r},{r} 0 1 0 {cx-r},{cy} Z'},
      'bbox':[cx-r,cy-r,2*r,2*r],'fill':fill,'stroke':stroke,'stroke_width':2 if name=='outer' else 0})
modules=[
 {'id':'head','name_zh':'头部填色','layer_ids':['01_head']},
 {'id':'cap','name_zh':'帽体与轮廓','layer_ids':['02_cap']},
 {'id':'electrodes','name_zh':'6 个独立电极部件','layer_ids':['03_electrodes']},
 {'id':'wires','name_zh':'两根独立导线','layer_ids':['04_cables']},
]
manifest={'schema_version':'1.0','source_image':'source.png','canvas':{'width':w,'height':h},
          'layers':layers,'modules':modules,
          'qa':{'unresolved_details':['示例仅用于测试工具链，不构成真实医学解剖学复刻。'],
                 'illustrator_native_verified':False}}
(root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
# Independent render for smoke test reference; similar enough to assess mask tracing.
SVG='http://www.w3.org/2000/svg'
from lxml import etree
svg=etree.Element('{%s}svg'%SVG, nsmap={None:SVG},width=str(w),height=str(h),viewBox=f'0 0 {w} {h}')
for layer in layers:
 for obj in layer['objects']:
  geo=obj['geometry']
  if geo['type']=='mask_png':
   # Only the synthetic reference contains a filled ellipse; not raster-embedded in any deliverable.
   etree.SubElement(svg,'{%s}ellipse'%SVG,cx='215',cy='177.5',rx='72',ry='96.5',fill=obj['fill'])
  else:
   etree.SubElement(svg,'{%s}path'%SVG,d=geo['d'],fill=obj.get('fill','none'),stroke=obj.get('stroke','none'),
       **{'stroke-width':str(obj.get('stroke_width',1)),'stroke-linecap':'round','stroke-linejoin':'round'})
cairosvg.svg2png(bytestring=etree.tostring(svg),write_to=str(root/'source.png'))
print('Created synthetic fixture:',root)
