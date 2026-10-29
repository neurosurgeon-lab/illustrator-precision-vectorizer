#!/usr/bin/env python3
"""Optional local OCR -> reviewed editable SVG text layers.

No OCR results are committed automatically. Correct spelling/position/font must
be manually verified; Chinese fonts are not bundled or embedded. No cloud OCR.
"""
import argparse
import json
import re
import hashlib
import math
from pathlib import Path
from lxml import etree
from PIL import Image,ImageDraw
from build_vector_package import tag, INK_NS, safe_id, local_path

_SAFE_FONT=re.compile(r'^[\w\s,\-+\.]{1,160}$',re.UNICODE)

def make_text_items(tesseract_output,confidence_cutoff=65):
    """Convert pytesseract image_to_data dict (injectable in tests) into audit records."""
    items=[]
    n=len(tesseract_output.get('text',[]))
    for i in range(n):
        text=str(tesseract_output['text'][i]).strip()
        if not text:continue
        try: conf=float(tesseract_output['conf'][i])
        except (TypeError,ValueError):conf=-1
        box=[int(tesseract_output[k][i]) for k in ('left','top','width','height')]
        if box[2]<=0 or box[3]<=0:continue
        record={'id':f'ocr_{len(items)+1:04d}','text':text,'bbox':box,'confidence':round(conf,2),
                'status':'review_required' if conf>=confidence_cutoff else 'low_confidence_review',
                'approved':False,'font_family':'sans-serif','font_size':max(8,box[3]),
                'fill':'#333333','engine':'local_tesseract'}
        items.append(record)
    return items


def run_ocr(project,language='eng',min_conf=65,output=None):
    root=Path(project).resolve()
    manifest=json.loads((root/'manifest.json').read_text('utf-8'))
    source=local_path(root,manifest['source_image'])
    if not source.resolve().is_relative_to(root):raise ValueError('Invalid source image path')
    target=Path(output) if output else root/'text_review.json'
    if target.exists():raise ValueError('OCR review already exists; preserve corrections or choose --output with a new path')
    try:
        import pytesseract
    except ImportError as e:
        raise RuntimeError('Optional pytesseract not installed; install with pip and the local Tesseract engine') from e
    from pytesseract import Output
    with Image.open(source) as img:
        ocr=pytesseract.image_to_data(img.convert('RGB'),lang=language,output_type=Output.DICT)
    data={'version':'3.2','engine':'local_tesseract','language':language,
          'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
          'items':make_text_items(ocr,min_conf),
          'notes':'Text and font are suggestions only. Review before approve; OCR must not modify source image.'}
    target.write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8')
    preview=Image.open(source).convert('RGB')
    draw=ImageDraw.Draw(preview)
    for item in data['items']:
        x,y,w,h=item['bbox'];draw.rectangle((x,y,x+w,y+h),outline='#D9534F',width=2)
    preview.save(target.with_suffix('.png'))
    return data


def append_approved_text(svg_root,review_path,source_sha256,w,h):
    """Add *only explicitly approved* OCR text as real editable <text> nodes."""
    path=Path(review_path)
    if not path.exists():return []
    review=json.loads(path.read_text('utf-8'))
    if review.get('source_sha256')!=source_sha256:
        raise ValueError('OCR source changed; re-run text recognition or review source hash')
    items=review.get('items',[])
    if len(items)>3000:raise ValueError('Too many OCR objects')
    active=[]
    ids={node.get('id') for node in svg_root.iter() if node.get('id')}
    for item in items:
        if type(item.get('approved',False)) is not bool:raise ValueError('approved must be a JSON boolean')
        if item.get('approved') is not True:continue
        oid=safe_id(item['id'])
        if 'text_'+oid in ids:raise ValueError('Duplicate OCR/geometry ID')
        ids.add('text_'+oid)
        value=item.get('corrected_text',item.get('text',''))
        if not isinstance(value,str) or not value.strip() or len(value)>4000:raise ValueError('Invalid OCR text content')
        font=str(item.get('font_family','sans-serif'))
        if not _SAFE_FONT.fullmatch(font):raise ValueError('Invalid font family')
        box=item['bbox']
        if len(box)!=4:raise ValueError('Invalid OCR bbox')
        x,y,bw,bh=[float(v) for v in box]
        if any(not (v==v and abs(v)<1e7) for v in (x,y,bw,bh)) or bw<=0 or bh<=0 or x<0 or y<0 or x+bw>w or y+bh>h:
            raise ValueError('OCR bbox outside canvas')
        size=float(item.get('font_size',bh))
        if not math.isfinite(size) or size<=0 or size>500:raise ValueError('Invalid OCR font size')
        fill=str(item.get('fill','#333333'))
        if not re.fullmatch('#[0-9A-Fa-f]{6}',fill):raise ValueError('Invalid OCR text fill')
        layer=etree.SubElement(svg_root,tag('g'),id='text_'+oid)
        layer.set(f'{{{INK_NS}}}label','文字 '+oid)
        layer.set('data-ocr-reviewed','true')
        node=etree.SubElement(layer,tag('text'),x=f'{x:g}',y=f'{y+bh:g}')
        node.set('font-size',f'{size:g}');node.set('font-family',font);node.set('fill',fill)
        node.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
        node.text=value
        active.append({'id':oid,'text':value,'bbox':box,'font_family':font,
                       'requires_visual_font_alignment_check':True})
    return active


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',required=True,type=Path)
    p.add_argument('--languages',default='eng',help='Tesseract language packs, e.g. eng+chi_sim')
    p.add_argument('--min-confidence',type=float,default=65)
    p.add_argument('--output',type=Path,help='New review JSON path; existing review files are never overwritten')
    a=p.parse_args()
    print(json.dumps(run_ocr(a.project,a.languages,a.min_confidence,a.output),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
