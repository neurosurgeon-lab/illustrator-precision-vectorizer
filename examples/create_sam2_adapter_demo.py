#!/usr/bin/env python3
"""Generate a *mock* SAM2 adapter E2E demo; NO model weights, NO actual inference."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from sam2_medical_segment import run
from centerline_trace import process as centerline

class MockPredictor:
    """Deterministic colored-mask fixture to validate API wiring, not SAM2 quality."""
    def set_image(self,image):self.image=np.asarray(image)
    def predict(self,point_coords=None,point_labels=None,box=None,multimask_output=True,normalize_coords=True):
        assert normalize_coords is True
        assert point_coords is not None and 1 in point_labels
        first=np.asarray(point_coords[np.where(point_labels==1)[0][0]],dtype=int)
        x,y=first
        color=self.image[y,x].copy()
        base=np.all(self.image==color,axis=2)
        if box is not None:
            x1,y1,x2,y2=map(int,box)
            allowed=np.zeros_like(base);allowed[y1:y2,x1:x2]=True
            base &= allowed
        false=np.zeros_like(base)
        partial=base.copy();partial[:,::11]=False
        return np.stack([false,base,partial]),np.array([.99,.96,.85]),None

def call(*args):subprocess.run([sys.executable,*map(str,args)],check=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    arg=ap.parse_args();out=arg.out.resolve();out.mkdir(parents=True,exist_ok=True)
    W,H=460,320
    img=Image.new('RGB',(W,H),'#FFFFFF');d=ImageDraw.Draw(img)
    d.ellipse((104,33,211,180),fill='#FDEEE7')
    d.rectangle((136,158,181,230),fill='#FDEEE7')
    d.polygon([(133,214),(181,213),(254,262),(289,319),(71,319),(86,256)],fill='#FDEEE7')
    d.line([(159,208),(159,145),(132,109)],fill='#67A5A1',width=6)
    d.line([(159,145),(183,105)],fill='#67A5A1',width=6)
    d.line([(159,206),(218,211),(272,241),(336,243)],fill='#6686B2',width=6)
    d.ellipse((311,218,370,270),fill='#BACDDF')
    d.ellipse((331,230,353,256),fill='#E9F1F8')
    d.ellipse((123,100,142,119),fill='#E7A9A6')
    d.ellipse((175,98,194,118),fill='#E7A9A6')
    ref=out/'schematic_reference.png';img.save(ref)
    proj=out/'project'
    call(ROOT/'scripts/init_project.py','--image',ref,'--out',proj)
    specs={'instances':[
      {'id':'body','name_zh':'人体轮廓填色','profile':'body','layer_id':'01_body','bbox':[67,29,224,291],
       'fg_points':[[157,75]],'max_area_fraction':.7},
      {'id':'nerve','name_zh':'神经可见分支','profile':'nerve','layer_id':'02_nerve','bbox':[124,100,67,116],
       'fg_points':[[159,179]],'max_area_fraction':.25},
      {'id':'lead','name_zh':'设备导线','profile':'lead','layer_id':'03_lead','bbox':[151,198,190,60],
       'fg_points':[[233,219]],'max_area_fraction':.25},
      {'id':'device','name_zh':'刺激器壳体','profile':'device','layer_id':'04_device','bbox':[307,215,65,60],
       'fg_points':[[321,241]],'max_area_fraction':.2},
      {'id':'device_center','name_zh':'刺激器中心装饰','profile':'device','layer_id':'05_device_detail','bbox':[327,227,31,32],
       'fg_points':[[340,240]],'max_area_fraction':.08},
      {'id':'electrode_1','name_zh':'电极1','profile':'electrode','layer_id':'06_electrodes','bbox':[120,97,27,27],
       'fg_points':[[132,108]],'max_area_fraction':.08},
      {'id':'electrode_2','name_zh':'电极2','profile':'electrode','layer_id':'06_electrodes','bbox':[172,95,27,27],
       'fg_points':[[184,107]],'max_area_fraction':.08}]
    }
    ann=out/'sam2_annotations.json';ann.write_text(json.dumps(specs,ensure_ascii=False,indent=2),encoding='utf8')
    report=run(proj,ann,predictor=MockPredictor(),min_score=.5)
    assert not report['actual_sam2_inference'] and report['instance_count']==7
    trace_reports=[]
    for obj in ('nerve','lead'):
        tr=centerline(proj,obj,mode='adaptive-bezier',min_iou=.78,write_manifest=True,allow_draft=False)
        trace_reports.append((obj,tr['qa']['iou']))
    mp=proj/'manifest.json';man=json.loads(mp.read_text('utf8'))
    man['layers'].insert(0,{'id':'00_background','name_zh':'白色背景','objects':[{
        'id':'background_white','name_zh':'白色背景',
        'geometry':{'type':'svg_path','d':f'M 0 0 H {W} V {H} H 0 Z'},
        'fill':'#FFFFFF','stroke':'none'}]})
    man['modules'].insert(0,{'id':'background_module','name_zh':'背景','layer_ids':['00_background']})
    man.setdefault('qa',{})['required_object_ids']=['background_white','body','device','electrode_1','electrode_2']
    mp.write_text(json.dumps(man,indent=2,ensure_ascii=False),encoding='utf8')
    call(ROOT/'scripts/build_vector_package.py','--project',proj,'--out',out/'export',
         '--allow-draft','--hires-scale','2','--include-source-project')
    # Three-panel demo image, clearly marked mock. Exact source/preview come from code.
    a=Image.open(ref).convert('RGB');b=Image.open(proj/'sam2_previews/nerve.png').convert('RGB')
    c=Image.open(out/'export/03_Full_Preview.png').convert('RGB');c=c.resize((W,H))
    panel=Image.new('RGB',(W*3, H+50),'white');dd=ImageDraw.Draw(panel)
    for i,(im,name) in enumerate([(a,'A  Synthetic reference'),(b,'B  Mock adapter mask QA'),(c,'C  Editable SVG render')]):
        panel.paste(im,(i*W,50));dd.text((i*W+15,15),name,fill='#152533')
    panel.save(out/'sam2_adapter_demo_mock_only.png')
    (out/'DEMO_NOT_REAL_SAM2.txt').write_text('This demo uses a deterministic injected fake predictor; it does not measure or run Meta SAM2 weights.\n',encoding='utf8')
    print(json.dumps({'demo':str(out),'instances':len(report['instances']),
            'real_sam2':False,'centerlines':trace_reports},ensure_ascii=False))
if __name__=='__main__':main()
