#!/usr/bin/env python3
"""deterministic synthetic regression tests; NOT real medical/SAM2 validation."""
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw
from subpixel_bezier import refine,process as subpixel_process,topology
from variable_width import fit_variable,process as width_process

BASE=Path(__file__).resolve().parents[1]

def synthetic_circle(hole=False):
    w,h,s=180,130,4
    im=Image.new('RGB',(w*s,h*s),'white');d=ImageDraw.Draw(im)
    d.ellipse((24*s+1,18*s+2,118*s-2,110*s-1),fill='#64A5A1')
    if hole:d.ellipse((58*s+1,52*s,83*s,79*s+2),fill='#FFFFFF')
    im=im.resize((w,h),Image.Resampling.LANCZOS)
    pix=np.asarray(im.convert('RGBA'))
    delta=np.linalg.norm(pix[:,:,:3].astype('float32')-np.array([100,165,161]),axis=2)
    mask=delta<75
    return pix,mask

def make_project(folder,rgba,mask,object_id='obj',fill='#64A5A1'):
    folder.mkdir(parents=True,exist_ok=True)
    Image.fromarray(rgba,'RGBA').save(folder/'source.png')
    (folder/'masks').mkdir(exist_ok=True)
    Image.fromarray(mask.astype('uint8')*255).save(folder/'masks'/(object_id+'.png'))
    h,w=mask.shape
    man={'schema_version':'1.0','source_image':'source.png','canvas':{'width':w,'height':h},
         'layers':[{'id':'medical_layer','name_zh':'医学结构','objects':[{'id':object_id,
           'name_zh':'待检查结构','fill':fill,'stroke':'none',
           'geometry':{'type':'mask_png','file':'masks/'+object_id+'.png'}}]}],
         'modules':[{'id':'structure','name_zh':'独立结构','object_ids':[object_id]}],
         'qa':{'fidelity_thresholds':{'max_mae_rgb':255,'max_mae_alpha':255,
             'max_changed_pixel_fraction':1,'max_alpha_changed_fraction':1,'max_edge_mismatch_fraction':1}}}
    (folder/'manifest.json').write_text(json.dumps(man,ensure_ascii=False,indent=2),'utf-8')


def run():
    image,mask=synthetic_circle()
    d,q,_=refine(mask,image,scale=3)
    assert q['passed'] and 'C ' in d and q['selected']['anchor_count']<120
    assert any(p['native']['iou']>=.975 for p in q['trials'])
    # A source with clearly non-flat interior must not be interpreted as a two-color AA edge.
    photo=image.copy()
    yy,xx=np.indices(mask.shape)
    photo[mask,0]=np.clip(70+1.5*xx[mask],0,255).astype('uint8')
    photo[mask,1]=np.clip(40+.9*yy[mask],0,255).astype('uint8')
    try:refine(mask,photo)
    except ValueError as ex:assert 'Non-flat' in str(ex) or 'contrast' in str(ex)
    else:raise AssertionError('Gradient / photo-like image was improperly accepted')
    # Antialiased ring retains its hole and source connected-component count.
    ring,rm=synthetic_circle(hole=True)
    dr,qr,_=refine(rm,ring,min_native_iou=.95)
    assert qr['passed'] and topology(rm)=={'components':1,'holes':1}
    assert qr['selected']['topology']==topology(rm)
    # Alpha silhouette without invented pixels.
    source=np.zeros_like(image)
    source[:,:,:3]=[100,165,161]
    source[:,:,3]=(mask.astype('uint8')*255)
    da,qa,_=refine(mask,source,min_native_iou=.95)
    assert qa['passed'] and qa['evidence']['model']=='original_alpha'
    # Variable width taper must beat the best single stroke by a clear margin.
    taper=np.zeros((170,350),np.uint8)
    for x in range(25,326):
        t=(x-25)/300
        y=int(83+12*math.sin(t*math.pi*1.5))
        r=int(round(2+6*t))
        cv2.circle(taper,(x,y),r,255,-1)
    vw,profiles,vq=fit_variable(taper>0,minimum_iou=.8)
    assert vq['passed'] and vq['mask_iou']>.90
    assert vq['improvement_over_uniform_iou']>.10
    assert 1.9<vq['width_dynamic_range_p90_over_p10']<4
    assert profiles and ' L ' in vw
    # Connected crossings are NOT silently classified as two separate cables.
    crossing=np.zeros((130,190),np.uint8)
    cv2.line(crossing,(20,62),(170,62),255,7);cv2.line(crossing,(98,15),(98,115),255,7)
    _,_,cq=fit_variable(crossing>0,minimum_iou=.2)
    assert cq['junction_count']>=1 and cq['warnings']
    # Project write-back and actual visible+hidden SVG authoring.
    with tempfile.TemporaryDirectory() as root:
        root=Path(root)
        proj=root/'circle';make_project(proj,image,mask)
        r1=subpixel_process(proj,'obj',write_manifest=True)
        assert r1['passed'] and r1['committed']
        assert json.loads((proj/'manifest.json').read_text())['layers'][0]['objects'][0]['geometry']['type']=='svg_path'
        pr2=root/'taper';rgba=np.full((170,350,4),255,dtype='uint8');rgba[taper>0,:3]=[100,165,161]
        make_project(pr2,rgba,taper>0)
        r2=width_process(pr2,'obj',write_manifest=True)
        assert r2['qa']['passed'] and r2['geometry']['centerline_profiles']
        manifest=json.loads((pr2/'manifest.json').read_text());o=manifest['layers'][0]['objects'][0]
        assert o['fill_rule']=='nonzero' and o['stroke']=='none'
        outfile=root/'taper_output'
        subprocess.run([sys.executable,str(BASE/'scripts/build_vector_package.py'),'--project',str(pr2),
                        '--out',str(outfile),'--allow-draft'],check=True,capture_output=True)
        assert (outfile/'14_Variable_Width_Profiles.json').exists()
        xml=(outfile/'01_Full_Illustration.svg').read_text('utf-8')
        assert 'data-centerline-guide="true"' in xml and 'display="none"' in xml
        assert ' <' not in str(r2['geometry']['d'])
        import zipfile
        with zipfile.ZipFile(outfile/'08_All_Files.zip') as z:
            assert '14_Variable_Width_Profiles.json' in z.namelist()
        # Invalid/noisy annotation cannot mutate the source project.
        noisy=root/'noisy';rand=np.random.default_rng(42).integers(20,220,size=image.shape,dtype='uint8')
        make_project(noisy,rand,mask)
        before=(noisy/'manifest.json').read_bytes()
        try:subpixel_process(noisy,'obj',write_manifest=True)
        except ValueError:pass
        else:raise AssertionError('Noisy source was allowed to commit')
        assert (noisy/'manifest.json').read_bytes()==before
    print('PASS: 9 precision test groups (subpixel AA, photo guard, hole preservation, alpha, taper advantage, crossing guard, project writeback, SVG/ZIP profile, failed commit rollback)')

if __name__=='__main__':run()
