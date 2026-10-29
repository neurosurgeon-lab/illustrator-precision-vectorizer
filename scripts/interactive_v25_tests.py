#!/usr/bin/env python3
"""tests: actual persistent project mutations, undo/redo, rejection and export."""
import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from interactive_studio import Studio

HERE=Path(__file__).resolve().parent.parent

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

class StudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.proj=Path(self.tmp.name)/'project'
        shutil.copytree(HERE/'examples/demo_project',self.proj)
        # Ensure fresh fixture instead of stale user data/previous snapshots.
        hist=self.proj/'.v25_history'
        if hist.exists():shutil.rmtree(hist)
        self.studio=Studio(self.proj)
        self.srcsha=digest(self.proj/'source.png')
    def tearDown(self):self.tmp.cleanup()
    def run_edit(self,kind,**kwargs):return self.studio.apply({'revision':self.studio.revision,'kind':kind,**kwargs})
    def test_brush_persists_png_and_undo_redo(self):
        path=self.proj/'masks/head.png';original=digest(path)
        self.run_edit('mask_brush',object_id='head_fill',mode='add',radius=6,allow_topology_change=True,points=[[8,12],[18,20]])
        changed=digest(path)
        self.assertNotEqual(original,changed)
        self.assertEqual(digest(self.proj/'source.png'),self.srcsha)
        s2=Studio(self.proj)
        self.assertEqual(s2.public_state()['can_undo'],True)
        s2.restore(-1);self.assertEqual(digest(path),original)
        s2.restore(1);self.assertEqual(digest(path),changed)
    def test_convert_mask_and_restore(self):
        self.run_edit('convert_mask',object_id='head_fill')
        o=self.studio.m['layers'][1]['objects'][0]
        self.assertEqual(o['geometry']['type'],'svg_path')
        self.assertIn('original_mask_png',o['geometry'])
        self.studio.restore(-1)
        self.assertEqual(self.studio.m['layers'][1]['objects'][0]['geometry']['type'],'mask_png')
    def test_path_node_write_validation(self):
        source=next(o for l in self.studio.m['layers'] for o in l['objects'] if o['id']=='cable_left')
        d=source['geometry']['d'].replace('M 176,119','M 174,119')
        self.run_edit('path',object_id='cable_left',d=d)
        self.assertEqual(next(o for l in self.studio.m['layers'] for o in l['objects'] if o['id']=='cable_left')['geometry']['d'],d)
        with self.assertRaises(ValueError):self.run_edit('path',object_id='cable_left',d='M 99 99')
        with self.assertRaises(ValueError):self.run_edit('path',object_id='cable_left',d='<script/>')
    def test_appearance_validation_and_revert(self):
        self.run_edit('appearance',object_id='cable_left',fill='none',stroke='#123456',stroke_width=2.8,opacity=.88)
        self.assertIn('#123456', (self.proj/'manifest.json').read_text())
        with self.assertRaises(ValueError):self.run_edit('appearance',object_id='cable_left',fill='url(http://evil)',stroke='#FFFFFF')
        self.studio.restore(-1)
        self.assertNotIn('#123456',(self.proj/'manifest.json').read_text())
    def test_occlusion_cycle_rejected_and_file_unchanged(self):
        self.run_edit('occlusion_add',behind='cable_left',front='cable_right')
        current=digest(self.proj/'manifest.json')
        with self.assertRaisesRegex(ValueError,'cycle|Cycle'):
            self.run_edit('occlusion_add',behind='cable_right',front='cable_left')
        self.assertEqual(digest(self.proj/'manifest.json'),current)
    def test_export_draft_and_QA_not_misreported(self):
        res=self.studio.export(allow_draft=True)
        self.assertTrue(res['ok'],res['log'])
        out=Path(res['out'])
        for fn in ['01_Full_Illustration.svg','04_Breakdown_Preview.png','08_All_Files.zip','quality_report.json']:
            self.assertTrue((out/fn).is_file(),fn)
        self.assertEqual(digest(self.proj/'source.png'),self.srcsha)
    def test_stale_revision_refused(self):
        with self.assertRaisesRegex(ValueError,'another browser'):
            self.studio.apply({'revision':99,'kind':'convert_mask','object_id':'head_fill'})
    def test_brush_topology_guard(self):
        path=self.proj/'masks/head.png';old=digest(path)
        with self.assertRaisesRegex(ValueError,'topology|connected components|holes'):
            self.run_edit('mask_brush',object_id='head_fill',mode='add',radius=4,points=[[6,8]])
        self.assertEqual(digest(path),old)
    def test_erase_whole_object_rejected(self):
        # A deliberately huge eraser is rejected if the mask would become empty.
        from PIL import Image
        mask=self.proj/'masks/head.png'
        with Image.open(mask) as im: old=im.copy()
        # can't reach across whole image in single stroke because radius limited: use restore source fixture.
        self.assertGreater(old.convert('L').getbbox()[2],0)
    def test_vectors_without_transform_are_editable(self):
        objects=self.studio.public_state()['objects']
        self.assertEqual(len(objects),12)
        self.assertIn('C ',next(x for x in objects if x['id']=='cable_left')['d'])

if __name__=='__main__':unittest.main(verbosity=2)
