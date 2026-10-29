#!/usr/bin/env python3
"""Conservative native-path import from simple SVG (no hidden rasterization).

Unsupported SVG features raise, rather than silently changing visual geometry.
Preserves source paths and transforms. This is not a universal SVG/AI parser.
"""
import io
import json
import math
import re
from pathlib import Path

import cairosvg
from lxml import etree
from PIL import ImageColor

NS='http://www.w3.org/2000/svg'
INK='http://www.inkscape.org/namespaces/inkscape'
SUPPORTED={'svg','g','path','rect','circle','ellipse','line','polyline','polygon','title','desc','metadata'}
SHAPES={'path','rect','circle','ellipse','line','polyline','polygon'}
SKIP={'title','desc','metadata'}
STYLE_KEYS={'fill','stroke','stroke-width','stroke-linecap','stroke-linejoin','fill-rule','opacity','fill-opacity','stroke-opacity',
            'display','visibility','transform'}
DANGEROUS_KEYS={'filter','clip-path','mask','stroke-dasharray','stroke-dashoffset','marker-start','marker-mid','marker-end','paint-order'}

def attr(e,k,default=None):return e.get(k,default)

def length(value):
    if not isinstance(value,str) or not re.fullmatch(r'\s*\d+(?:\.\d+)?(?:px)?\s*',value):
        raise ValueError(f'Unsupported SVG length (only pixel values): {value}')
    return float(value.strip().removesuffix('px'))

def dimensions(root):
    vb=root.get('viewBox')
    values=list(map(float,re.split(r'[\s,]+',vb.strip()))) if vb else None
    if values and (len(values)!=4 or values[2]<=0 or values[3]<=0 or not all(map(math.isfinite,values))):
        raise ValueError('Invalid SVG viewBox')
    width=length(root.get('width')) if root.get('width') else (values[2] if values else None)
    height=length(root.get('height')) if root.get('height') else (values[3] if values else None)
    if not width or not height:raise ValueError('SVG must specify pixels or a viewBox')
    if not float(width).is_integer() or not float(height).is_integer():
        raise ValueError('SVG must use integer pixel canvas for exact raster comparison')
    if values and (abs(values[2]-width)>1e-6 or abs(values[3]-height)>1e-6 or any(abs(x)>1e-6 for x in values[:2])):
        raise ValueError('SVG nontrivial viewBox transform must be flattened in Illustrator first')
    return int(width),int(height)

def safe_svg(source):
    parser=etree.XMLParser(resolve_entities=False,no_network=True,load_dtd=False,huge_tree=False)
    root=etree.parse(str(source),parser).getroot()
    if etree.QName(root).localname!='svg' or etree.QName(root).namespace!=NS:raise ValueError('Not an SVG root')
    for elem in root.iter():
        if not isinstance(elem.tag,str):continue
        name=etree.QName(elem).localname
        if etree.QName(elem).namespace not in (NS,None) or name not in SUPPORTED:
            raise ValueError(f'Unsupported SVG element <{name}>: convert to basic native shapes or authored paths first')
        for k,v in elem.attrib.items():
            key=etree.QName(k).localname
            if key in DANGEROUS_KEYS or key in ('href','src') or 'url(' in v.lower() or 'javascript:' in v.lower():
                raise ValueError(f'Unsupported SVG external/effect attribute {key}')
        if elem.get('class'):
            raise ValueError('CSS classes are not imported; expand appearance to inline attributes')
    return root

def style(e,inherited):
    out=dict(inherited)
    inline={}
    if e.get('style'):
        for s in e.get('style').split(';'):
            if not s.strip():continue
            if ':' not in s:raise ValueError('Bad inline CSS')
            k,v=s.split(':',1);inline[k.strip()]=v.strip()
    keys=set(inline)|{etree.QName(k).localname for k in e.attrib}
    for key in keys:
        if key in STYLE_KEYS and key!='transform':
            val=inline.get(key,e.get(key))
            if val is not None:out[key]=val
        elif key in {'style','id','class','name','label','groupmode','width','height','viewBox','version','xmlns','x','y','cx','cy','rx','ry','r','x1','y1','x2','y2','points','d','transform'}:
            continue
        elif key in {'sodipodi','type','preserveAspectRatio','data-name-en'} or key.startswith('data-'):
            continue
        elif key in DANGEROUS_KEYS:
            raise ValueError('Unsupported style attribute: '+key)
    if out.get('display')=='none' or out.get('visibility')=='hidden':return None
    return out

def fill_hex(value):
    if value=='none':return 'none'
    try:
        val=ImageColor.getrgb(value)
        if len(val)!=3:raise ValueError('RGBA requires opacity and separate vector paths')
        return '#%02X%02X%02X'%tuple(val)
    except (ValueError,KeyError):
        raise ValueError(f'Unsupported SVG paint: {value}; expand paints to #RRGGBB')

def number(elem,key,default=0):return float(elem.get(key,default))

def shape_d(e):
    kind=etree.QName(e).localname
    if kind=='path':return e.get('d','')
    if kind=='rect':
        x,y,w,h=[number(e,k) for k in ('x','y','width','height')]
        if w<=0 or h<=0:return ''
        rx=min(max(number(e,'rx'),0),w/2);ry=min(max(number(e,'ry',e.get('rx','0')),0),h/2)
        if not (rx and ry):return f'M{x:g},{y:g} h{w:g} v{h:g} h{-w:g} Z'
        return f'M{x+rx:g},{y:g} H{x+w-rx:g} A{rx:g},{ry:g} 0 0 1 {x+w:g},{y+ry:g} V{y+h-ry:g} A{rx:g},{ry:g} 0 0 1 {x+w-rx:g},{y+h:g} H{x+rx:g} A{rx:g},{ry:g} 0 0 1 {x:g},{y+h-ry:g} V{y+ry:g} A{rx:g},{ry:g} 0 0 1 {x+rx:g},{y:g} Z'
    if kind in ('circle','ellipse'):
        cx,cy=number(e,'cx'),number(e,'cy')
        rx=number(e,'r') if kind=='circle' else number(e,'rx')
        ry=number(e,'r') if kind=='circle' else number(e,'ry')
        if rx<=0 or ry<=0:return ''
        return f'M{cx-rx:g},{cy:g} A{rx:g},{ry:g} 0 1 0 {cx+rx:g},{cy:g} A{rx:g},{ry:g} 0 1 0 {cx-rx:g},{cy:g} Z'
    if kind=='line':return f'M{number(e,"x1"):g},{number(e,"y1"):g} L{number(e,"x2"):g},{number(e,"y2"):g}'
    if kind in ('polyline','polygon'):
        nums=[float(x) for x in re.split(r'[\s,]+',e.get('points','').strip()) if x]
        if len(nums)<4 or len(nums)%2:raise ValueError('Malformed polygon coordinates')
        pts=' L'.join(f'{nums[i]:g},{nums[i+1]:g}' for i in range(0,len(nums),2))
        return 'M'+pts+(' Z' if kind=='polygon' else '')
    raise ValueError('Unexpected element '+kind)

def import_svg(original):
    tree=safe_svg(original)
    w,h=dimensions(tree)
    imported=[]
    used=set()
    def walk(e,inherited,transforms,layer_id,layer_name):
        name=etree.QName(e).localname
        current=style(e,inherited)
        if current is None:return
        tf=e.get('transform','').strip()
        if tf:transforms=transforms+[tf]
        if name=='g' and (e.get(f'{{{INK}}}groupmode')=='layer'):
            layer_id=e.get('id') or layer_id
            layer_name=e.get(f'{{{INK}}}label') or layer_id
        if name in SHAPES:
            d=shape_d(e)
            if not d.strip():return
            oid=e.get('id') or (e.getparent().get('id') if e.getparent() is not None else None) or 'svg_object'
            oid=re.sub('[^A-Za-z0-9_.-]+','_',oid)
            if not re.match(r'^[A-Za-z_]',oid):oid='v_'+oid
            original_id=oid
            i=2
            while oid in used:oid=f'{original_id}_{i}';i+=1
            used.add(oid)
            fill=fill_hex(current.get('fill','#000000'))
            stroke=fill_hex(current.get('stroke','none'))
            if fill=='none' and stroke=='none':return
            if float(current.get('fill-opacity','1'))!=1 or float(current.get('stroke-opacity','1'))!=1:
                raise ValueError('Separate fill/stroke opacity must be expanded to native paths before import')
            # A simple leaf opacity is preserved; group-compositing may differ for overlapping shapes.
            opacity=float(current.get('opacity','1'))
            if not 0<=opacity<=1:raise ValueError('Bad SVG opacity')
            obj={'id':oid,'name_zh':oid,'name_en':oid,
                 'geometry':{'type':'svg_path','d':d},'fill':fill,'stroke':stroke,
                 'stroke_width':float(current.get('stroke-width',1)),
                 'opacity':opacity,'stroke_linecap':current.get('stroke-linecap','butt'),
                 'stroke_linejoin':current.get('stroke-linejoin','miter'),
                 'fill_rule':current.get('fill-rule','nonzero')}
            if transforms:obj['transform']=' '.join(transforms)
            imported.append((layer_id,layer_name,obj))
        for child in e:
            if isinstance(child.tag,str):walk(child,current,transforms,layer_id,layer_name)
    walk(tree,{},[],'01_Original_Vector','原始矢量对象')
    if not imported:raise ValueError('SVG contains no supported vector objects')
    layers={}
    for lid,zh,obj in imported:
        if lid not in layers:layers[lid]={'id':lid,'name_zh':zh,'name_en':lid,'objects':[]}
        layers[lid]['objects'].append(obj)
    return w,h,list(layers.values())
