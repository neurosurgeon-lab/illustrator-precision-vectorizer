#!/usr/bin/env python3
"""local regression. Mock predictor is never called 'real SAM2'."""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
from interactive_studio import Studio
from studio_difference import difference
from studio_sam2 import validate_prompts
from illustrator_import import prepare

ROOT=Path(__file__).resolve().parent.parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

class FakePredictor:
    def __init__(self,mask):self.mask=mask;self.set_calls=0;self.pred_calls=0
    def set_image(self,image):self.set_calls+=1;self.shape=image.shape
    def predict(self,**kwargs):
        assert kwargs['normalize_coords'] is True
        self.pred_calls+=1
        return np.asarray([self.mask,self.mask]), np.asarray([.82,.91]), None

class V30(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.proj=Path(self.temp.name)/'project';shutil.copytree(ROOT/'examples/demo_project',self.proj)
        with Image.open(self.proj/'masks/head.png') as im:mask=np.asarray(im.convert('L'))>=128
        self.ys,self.xs=np.where(mask)
        self.f=FakePredictor(mask)
        self.s=Studio(self.proj,sam2_predictor=self.f)
        self.original_sha=sha(self.proj/'source.png')
        self.masksha=sha(self.proj/'masks/head.png')
    def call_preview(self):
        cx,cy=int(self.xs[len(self.xs)//2]),int(self.ys[len(self.ys)//2])
        return self.s.sam2_preview({'revision':self.s.revision,'object_id':'head_fill',
            'points':[{'x':cx,'y':cy,'label':1}],'profile':'body'})
    def test_sam2_preview_no_write_and_accept_undo(self):
        a=self.call_preview();self.assertEqual(self.f.set_calls,1)
        self.assertEqual(len(a['candidates']),2)
        self.assertFalse(a['actual_sam2_inference'])
        self.assertEqual(sha(self.proj/'masks/head.png'),self.masksha)
        self.assertEqual(sha(self.proj/'source.png'),self.original_sha)
        self.assertEqual(a['candidates'][0]['score'],.91)
        state=self.s.sam2_accept({'revision':self.s.revision,'proposal_id':a['proposal_id'],
                                  'candidate_index':a['candidates'][0]['index']})
        self.assertTrue(state['can_undo'])
        audit=self.proj/'sam2_studio_audit.jsonl'
        self.assertTrue(audit.is_file())
        self.assertEqual(json.loads(audit.read_text().splitlines()[0])['operator_confirmation'],True)
        self.assertEqual(sha(self.proj/'source.png'),self.original_sha)
        self.s.restore(-1)
        self.assertEqual(sha(self.proj/'masks/head.png'),self.masksha)
    def test_sam2_stale_or_invalid(self):
        a=self.call_preview()
        with self.assertRaisesRegex(ValueError,'Invalid candidate'):
            self.s.sam2_accept({'revision':self.s.revision,'proposal_id':a['proposal_id'],'candidate_index':777})
        with self.assertRaisesRegex(ValueError,'Stale'):
            self.s.sam2_preview({'revision':55,'object_id':'head_fill'})
        self.s.apply({'revision':self.s.revision,'kind':'appearance','object_id':'cap_base',
             'fill':'#AABBCC','stroke':'none','stroke_width':0,'opacity':1})
        with self.assertRaisesRegex(ValueError,'Proposal expired'):
            self.s.sam2_accept({'revision':self.s.revision,'proposal_id':a['proposal_id'],'candidate_index':0})
    def test_sam2_refuse_existing_path(self):
        with self.assertRaisesRegex(ValueError,'existing editable mask'):
            self.s.sam2_preview({'revision':0,'object_id':'cap_base','points':[{'x':2,'y':2,'label':1}]})
    def test_sam2_prompts_boundaries(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            validate_prompts({'points':[{'x':-10,'y':2,'label':1}]},420,320)
        with self.assertRaisesRegex(ValueError,'Invalid bounding'):
            validate_prompts({'box':[20,20,5,6]},420,320)
        with self.assertRaisesRegex(ValueError,'Background-only'):
            validate_prompts({'points':[{'x':1,'y':1,'label':0}]},420,320)
    def test_no_model_explicit_failure(self):
        other=Studio(self.proj)
        with self.assertRaisesRegex(RuntimeError,'not configured|not installed'):
            other.sam2_preview({'revision':0,'object_id':'head_fill','points':[{'x':int(self.xs[0]),'y':int(self.ys[0]),'label':1}]})
    def test_diff_live_and_roi(self):
        one=self.s.diff_preview({'revision':0,'object_id':'head_fill','threshold':20})
        self.assertEqual(one['metrics']['scope'],'ROI')
        self.assertGreater(one['metrics']['pixels_evaluated'],0)
        self.assertTrue(one['image'].startswith('data:image/png;base64,'))
        self.s.apply({'revision':0,'kind':'appearance','object_id':'background',
              'fill':'#000000','stroke':'none','stroke_width':0,'opacity':1})
        two=self.s.diff_preview({'revision':1,'threshold':20})
        self.assertEqual(two['metrics']['scope'],'whole_canvas')
        self.assertGreater(two['metrics']['mae_rgb_0_255'],one['metrics']['mae_rgb_0_255'])
        with self.assertRaisesRegex(ValueError,'Stale'):
            self.s.diff_preview({'revision':0})
    def test_diff_independent_pixels(self):
        a=Image.new('RGBA',(32,32),'white');b=Image.new('RGBA',(32,32),'white')
        self.assertEqual(difference(a,b)['metrics']['mae_rgb_0_255'],0)
        b.putpixel((5,5),(0,0,0,255))
        x=difference(a,b,[0,0,10,10],10)['metrics']
        self.assertGreater(x['mae_rgb_0_255'],0)
        self.assertEqual(x['pixels_evaluated'],100)
    def test_import_staging_no_fake_ai(self):
        folder=Path(self.temp.name)/'ai_stage'
        info=prepare(self.proj,folder)
        self.assertEqual(info['object_count'],12)
        self.assertTrue((folder/'import_v30.jsx').is_file())
        self.assertEqual(len(list(folder.glob('object_*.svg'))),12)
        self.assertFalse((folder/'Native_Illustrator_v30.ai').exists())
        from lxml import etree
        for f in folder.glob('object_*.svg'):
            tree=etree.parse(str(f))
            self.assertEqual(len(tree.xpath('//*[local-name()="g" and @id]')),1)
        with self.assertRaisesRegex(ValueError,'must be empty'):
            prepare(self.proj,folder)
    def test_integrated_export(self):
        x=self.s.export(True)
        self.assertTrue(x['ok'],x['log'])
        base=Path(x['out'])
        self.assertTrue((base/'18_Illustrator_Import'/'import_v30.jsx').exists())
        import zipfile
        with zipfile.ZipFile(base/'08_All_Files.zip') as z:
            self.assertIn('18_Illustrator_Import/import_v30.jsx',z.namelist())
            self.assertEqual(len([n for n in z.namelist() if '18_Illustrator_Import/object_' in n]),12)
if __name__=='__main__':unittest.main(verbosity=2)
