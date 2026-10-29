#!/usr/bin/env python3
"""Batch behavior checks with real export subprocesses and isolated settings."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from batch_vectorize import process_batch
from sam2_settings import resolve_model_spec,settings_path

FIXTURE=Path(__file__).resolve().parents[1]/'examples/demo_project'


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def test_existing_projects_continue_after_failure(self):
        source=self.root/'inputs';source.mkdir()
        bad=source/'a_bad';shutil.copytree(FIXTURE,bad)
        manifest=json.loads((bad/'manifest.json').read_text('utf-8'));manifest['layers']=[]
        (bad/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        good=source/'b_good';shutil.copytree(FIXTURE,good)
        before=hashlib.sha256((good/'manifest.json').read_bytes()).hexdigest()
        result=process_batch(source,self.root/'out',projects=True)
        self.assertEqual([r['status'] for r in result['items']],['failed','success'])
        self.assertTrue((self.root/'out/b_good/export/08_All_Files.zip').is_file())
        self.assertEqual(hashlib.sha256((good/'manifest.json').read_bytes()).hexdigest(),before)
        self.assertTrue((self.root/'out/batch_summary.csv').is_file())

    def test_unannotated_images_initialize_separately(self):
        source=self.root/'images';source.mkdir()
        for name in ['same.png','same.jpg']:shutil.copyfile(FIXTURE/'source.png',source/name)
        result=process_batch(source,self.root/'out')
        self.assertEqual(result['counts'],{'needs_annotations':2})
        for name in ['same.png','same.jpg']:
            self.assertTrue((self.root/'out'/name/'project/manifest.json').is_file())
            self.assertFalse((self.root/'out'/name/'export/08_All_Files.zip').exists())

    def test_output_protection(self):
        source=self.root/'images';source.mkdir();shutil.copyfile(FIXTURE/'source.png',source/'one.png')
        out=self.root/'out';out.mkdir();marker=out/'keep.txt';marker.write_text('keep')
        with self.assertRaisesRegex(ValueError,'empty'):process_batch(source,out)
        self.assertEqual(marker.read_text(),'keep')
        with self.assertRaisesRegex(ValueError,'outside'):process_batch(source,source/'exports')

    def test_draft_is_not_reported_as_quality_pass(self):
        source=self.root/'projects';source.mkdir();project=source/'one';shutil.copytree(FIXTURE,project)
        manifest=json.loads((project/'manifest.json').read_text('utf-8'))
        manifest['layers'][0]['objects'][0]['fill']='#000000'
        (project/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        result=process_batch(source,self.root/'out',projects=True,allow_draft=True)
        self.assertEqual(result['items'][0]['status'],'draft')
        self.assertFalse(result['items'][0]['quality_gates_passed'])

    def test_local_model_selection_and_explicit_override(self):
        checkpoint=self.root/'model.pt';checkpoint.write_bytes(b'fixture')
        setting=self.root/'sam2.json';setting.write_text(json.dumps({'checkpoint':str(checkpoint),'config':'configs/sam2.1/sam2.1_hiera_b+.yaml','device':'mps'}))
        with patch('sam2_settings.settings_path',return_value=setting):
            self.assertEqual(resolve_model_spec()['checkpoint'],str(checkpoint.resolve()))
            self.assertEqual(resolve_model_spec(device='cpu')['device'],'cpu')
            spec=resolve_model_spec(hf_model='facebook/sam2.1-hiera-tiny')
            self.assertIsNone(spec['checkpoint'])
            self.assertEqual(spec['device'],'auto')
            with self.assertRaisesRegex(ValueError,'both config and checkpoint'):resolve_model_spec(checkpoint=checkpoint)
            with self.assertRaisesRegex(ValueError,'OR local'):resolve_model_spec(hf_model='x',checkpoint=checkpoint,config='x')

    def test_portable_settings_and_existing_codex_config(self):
        with patch.dict('os.environ',{'XDG_CONFIG_HOME':str(self.root/'config'),'CODEX_HOME':str(self.root/'codex')},clear=True):
            self.assertEqual(settings_path(),self.root/'config/layertrace/sam2.json')
            legacy=self.root/'codex/skill-config/illustrator-precision-vectorizer/sam2.json'
            legacy.parent.mkdir(parents=True);legacy.write_text('{}')
            self.assertEqual(settings_path(),legacy)
            with patch.dict('os.environ',{'LAYERTRACE_CONFIG_HOME':str(self.root/'shared')}):
                self.assertEqual(settings_path(),self.root/'shared/sam2.json')


if __name__=='__main__':unittest.main(verbosity=2)
