#!/usr/bin/env python3
"""Weight-free integration tests. A deterministic mock is NOT real SAM2 inference."""
from pathlib import Path
import json
import tempfile
import cv2
import numpy as np
from PIL import Image
from medical_mask_postprocess import refine_mask
from sam2_medical_segment import select_prediction,run

class FakeSAM2Predictor:
    def __init__(self,replies):self.replies=replies;self.calls=[];self.images=[]
    def set_image(self,image):
        assert image.shape[-1]==3
        self.images.append(image.copy())
    def predict(self,point_coords=None,point_labels=None,box=None,multimask_output=True,normalize_coords=True):
        self.calls.append((point_coords,point_labels,box,normalize_coords))
        masks,scores=self.replies[len(self.calls)-1]
        return np.array(masks),np.asarray(scores),None

def init_project(root,img):
    root.mkdir(exist_ok=True,parents=True)
    Image.fromarray(img).save(root/'source.png');h,w=img.shape[:2]
    (root/'manifest.json').write_text(json.dumps({'schema_version':'1.0','source_image':'source.png',
            'canvas':{'width':w,'height':h},'layers':[],'modules':[],'qa':{}},ensure_ascii=False),encoding='utf8')

with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    h,w=140,220
    img=np.full((h,w,4),255,np.uint8)
    cv2.circle(img,(35,45),15,(244,135,100,255),-1)
    cv2.circle(img,(130,45),15,(244,135,100,255),-1)
    left=np.zeros((h,w),bool);cv2.circle(left.view(np.uint8),(35,45),15,1,-1)
    right=np.zeros((h,w),bool);cv2.circle(right.view(np.uint8),(130,45),15,1,-1)
    # Multiple masks, one with highest score but wrong seed, must be rejected.
    ann={'id':'electrode_a','profile':'electrode','bbox':[5,20,60,60],
         'fg_points':[[35,45]],'bg_points':[[14,45]]}
    pred=np.stack([right,left,left],axis=0)
    valid,qa=select_prediction(img,ann,pred,[.99,.78,.94],.5)
    assert np.array_equal(valid,left) and qa['chosen_candidate']==2
    assert qa['sam_predicted_iou']==.94 and qa['ground_truth_iou'] is None
    # Holes are preserved, not filled by morphological repair.
    ring=np.zeros((h,w),np.uint8)
    cv2.circle(ring,(35,105),21,1,-1)
    cv2.circle(ring,(35,105),12,0,-1)
    out,qa=refine_mask(ring,img,{'id':'ring','profile':'electrode','bbox':[8,78,57,55],
                              'fg_points':[[35,86]],'max_area_fraction':.4})
    assert not out[105,35] and qa['post_refinement']['holes']>=1
    # Thin line, no morph closure by default. Missing segment -> FAIL not a fabricated bridge.
    broken=np.zeros((h,w),np.uint8)
    cv2.line(broken,(50,101),(87,101),1,3)
    cv2.line(broken,(99,101),(138,101),1,3)
    try:
        refine_mask(broken,img,{'id':'broken_nerve','profile':'nerve','fg_points':[[70,101],[110,101]]})
    except ValueError as exc:assert 'components' in str(exc)
    else:raise AssertionError('Disconnected nerve was secretly connected')
    checked,qa=refine_mask(broken,img,{'id':'broken_nerve','profile':'nerve',
                       'fg_points':[[70,101],[110,101]],'allow_disconnected':True})
    assert qa['post_refinement']['component_count']==2 and not checked[101,93]
    # Conservative color-assisted edge refinement: only adjacent matching ink.
    ink=np.full((h,w,4),255,dtype=np.uint8)
    cv2.line(ink,(40,120),(100,120),(80,135,150,255),3)
    candidate=np.zeros((h,w),np.uint8)
    cv2.line(candidate,(46,120),(94,120),1,3)
    refined,info=refine_mask(candidate,ink,{'id':'nerve_color_refine','profile':'nerve',
        'fg_points':[[70,120]],'bbox':[35,114,71,13],
        'color_refine':True,'refine_radius_px':2,'refine_lab_tolerance':3,
        'max_added_fraction':.4})
    assert refined.sum()>candidate.sum() and info['added_fraction']>0
    assert not refined[120,35] and not refined[120,110]
    # Invalid negative prompt must veto mask, even if predictor score high.
    try:select_prediction(img,{'id':'veto','profile':'electrode',
              'fg_points':[[35,45]],'bg_points':[[35,45]]},[left],[.99])
    except ValueError:pass
    else:raise AssertionError('Negative prompt was ignored')
    # Full project transaction: two same-color electrodes remain separate objects.
    project=td/'samproj';init_project(project,img)
    spec={'instances':[
        {'id':'electrode_1','name_zh':'左电极','profile':'electrode',
         'bbox':[5,20,60,60],'fg_points':[[35,45]],'bg_points':[[5,5]],'layer_id':'01_electrodes'},
        {'id':'electrode_2','name_zh':'右电极','profile':'electrode',
         'bbox':[100,20,60,60],'fg_points':[[130,45]],'bg_points':[[95,5]],'layer_id':'01_electrodes'}]}
    specpath=td/'anno.json';specpath.write_text(json.dumps(spec,ensure_ascii=False),encoding='utf8')
    mock=FakeSAM2Predictor([([left],[.96]),([right],[.91])])
    report=run(project,specpath,predictor=mock,min_score=.5)
    assert report['instance_count']==2 and report['actual_sam2_inference'] is False
    assert len(mock.images)==1 and len(mock.calls)==2 and mock.calls[0][3] is True
    assert mock.calls[0][2].tolist()==[5,20,65,80] and mock.calls[0][1].tolist()==[1,0]
    manifest=json.loads((project/'manifest.json').read_text('utf8'))
    assert len(manifest['layers'])==1 and len(manifest['modules'])==2 and len(manifest['layers'][0]['objects'])==2
    assert (project/'sam2_previews/electrode_1.png').exists()
    assert (project/'masks/electrode_1.png').exists() and (project/'sam2_segmentation_report.json').exists()
    # Overlap failure is transactional: no masks, layer changes, report written.
    failproj=td/'overlap';init_project(failproj,img)
    same=FakeSAM2Predictor([([left],[.95]),([left],[.95])])
    # Second ROI must be wide enough to include left mask, use separate annotation.
    spec['instances'][1]['bbox']=[5,20,160,60];spec['instances'][1]['fg_points']=[[35,45]]
    specpath.write_text(json.dumps(spec,ensure_ascii=False),encoding='utf8')
    try:run(failproj,specpath,predictor=same)
    except ValueError as exc:assert 'overlapping' in str(exc)
    else:raise AssertionError('Overlapping visible layers accepted without explicit consent')
    assert not (failproj/'masks').exists() and json.loads((failproj/'manifest.json').read_text('utf8'))['layers']==[]
    # Verify real adapter API call signatures against upstream-shaped module stubs.
    # This is NOT equivalent to testing real weights/model behavior.
    import sys,types
    import torch  # Import before patch.dict(sys.modules) to retain PyTorch singleton modules.
    import importlib.util
    if importlib.util.find_spec('sam2') is not None:
        from sam2.utils.transforms import SAM2Transforms
        transforms=SAM2Transforms(resolution=1024,mask_threshold=0)
        actual=transforms.transform_coords(torch.tensor([[210.,160.]]),normalize=True,orig_hw=(320,420))
        assert torch.allclose(actual,torch.tensor([[512.,512.]])), 'Image pixel center must map to encoder center'
    from unittest.mock import patch
    import sam2_medical_segment as adapter
    calls=[]
    bmod=types.ModuleType('sam2.build_sam')
    bmod.build_sam2_hf=lambda model,device: calls.append(('hf',model,device)) or object()
    bmod.build_sam2=lambda cfg,ckpt,device: calls.append(('ckpt',cfg,str(ckpt),device)) or object()
    pmod=types.ModuleType('sam2.sam2_image_predictor')
    class StubPredictor:
        def __init__(self,model):self.model=model
    pmod.SAM2ImagePredictor=StubPredictor
    with patch.dict(sys.modules,{'sam2':types.ModuleType('sam2'),
                                 'sam2.build_sam':bmod,'sam2.sam2_image_predictor':pmod}):
        pred,device=adapter.load_sam2_predictor(hf_model='facebook/sam2.1-hiera-tiny',device='cpu')
        assert isinstance(pred,StubPredictor) and device=='cpu'
        assert calls[-1]==('hf','facebook/sam2.1-hiera-tiny','cpu')
        ck=td/'mock_not_real_model.pt';ck.write_text('NOT A MODEL')
        pred,device=adapter.load_sam2_predictor(config='configs/sam2.1/sam2.1_hiera_t.yaml',checkpoint=ck,device='cpu')
        assert calls[-1][0]=='ckpt' and calls[-1][-1]=='cpu'
    # The CLI without installed upstream SAM2 MUST be explicit, not fall back silently.
    import importlib.util
    if importlib.util.find_spec('sam2') is None:
        try:
            from sam2_medical_segment import load_sam2_predictor
            load_sam2_predictor('facebook/sam2.1-hiera-tiny')
        except RuntimeError as exc:assert 'SAM2 not installed' in str(exc)
        else:raise AssertionError('Missing official model was silently substituted')
    print('PASS: 7 SAM2-adapter/postprocess integration groups (mock only; NO real model inference)')
