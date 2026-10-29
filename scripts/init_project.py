#!/usr/bin/env python3
"""Initialize a semantic SVG tracing project. Does NOT auto-vectorize its contents."""
import argparse
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from PIL import Image
import io
import cairosvg
from svg_source import import_svg


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', required=True, type=Path, help='PNG/JPEG/TIFF or simple real-vector SVG source')
    p.add_argument('--out', required=True, type=Path, help='project directory')
    a = p.parse_args()
    source = a.image.resolve(strict=True)
    svg_input=source.suffix.lower()=='.svg'
    svg_layers=[]
    if svg_input:
        w,h,svg_layers=import_svg(source)  # read and validate native paths before any raster render
        rendered=cairosvg.svg2png(url=str(source),output_width=w,output_height=h)
        rgba=Image.open(io.BytesIO(rendered)).convert('RGBA')
        mode='SVG-vectors'
    else:
        with Image.open(source) as img:
            w,h=img.size
            mode=img.mode
            rgba=img.convert('RGBA')
    sample=rgba.resize((min(w,384),min(h,384)))
    palette=Counter((r//8*8,g//8*8,b//8*8) for r,g,b,alpha in sample.getdata() if alpha>127)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out/'masks').mkdir(exist_ok=True)
    target = a.out/('source.png' if svg_input else f'source{source.suffix.lower()}')
    if target.exists():
        raise SystemExit(f'Will not overwrite existing source file: {target}')
    if svg_input:
        shutil.copy2(source,a.out/'original_source.svg')
        rgba.save(target)
    else:
        shutil.copy2(source, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = {
        'schema_version': '1.0', 'source_image': target.name,
        'canvas': {'width':w,'height':h},
        'source_sha256':digest, 'source_mode':mode,
        'layers':svg_layers, 'modules':[
            {'id':'module_'+str(i+1),'name_zh':l['name_zh'],'layer_ids':[l['id']]}
            for i,l in enumerate(svg_layers)],
        'qa':{'require_line_quality_review':True, 'unresolved_details':['尚未完成语义对象描摹与蒙版/路径构建'], 'illustrator_native_verified':False}
    }
    manifest_path = a.out/'manifest.json'
    if manifest_path.exists():
        raise SystemExit(f'Will not overwrite existing manifest: {manifest_path}')
    if svg_input:
        manifest['original_svg_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
        manifest['qa']['unresolved_details']=['已直接导入源 SVG 的基础矢量路径；仍需核验语义图层、颜色/变换与 Illustrator 兼容性。']
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    report={'source':str(source),'width':w,'height':h,'mode':mode,'source_sha256':digest,
        'rough_palette_8bit_buckets':[
            {'hex':'#%02X%02X%02X'%k,'sample_count':v} for k,v in palette.most_common(16)
        ],
        'warning':'颜色采样仅供参考，不自动解释为对象或准确设计色'}
    (a.out/'source_inspection.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Initialized: {a.out}\nCanvas: {w}x{h}; SHA256: {digest}\n' +
          ('Imported native paths from simple SVG; verify semantic objects and export' if svg_input
           else 'Next: draw/trace semantic objects and populate manifest.json'))

if __name__=='__main__': main()
