#!/usr/bin/env python3
"""localhost-only medical-vector review editor. No cloud, no source-image modifications.

Run: python scripts/interactive_studio.py --project /path/project [--port 8765]
Browser frontend lives in ../webui; all writes are atomic and undoable.
"""
import argparse
import hashlib
import io
import base64
import secrets
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from PIL import Image, ImageDraw
import cv2
import numpy as np
from mask_precision import trace_mask
from build_vector_package import build_object, local_path, safe_id
from occlusion_layers import resolve_stack
from studio_sam2 import SAM2StudioEngine,mask_png
from studio_difference import analyze_project
from sam2_settings import resolve_model_spec

HERE=Path(__file__).resolve().parent
STATIC=HERE.parent/'webui'
PATH_CMD=re.compile(r'^[\s\d\-+eE.,MmLlHhVvCcSsQqTtAaZz]+$')
MAX_BODY=1024*1024
MAX_EDITS=48

def atomic(path, content):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as fd:
        fd.write(content)
        name=fd.name
    os.replace(name,path)

def get_image_size(m,root):
    with Image.open(local_path(root,m['source_image'])) as im:
        size=im.size
    w,h=int(m['canvas']['width']),int(m['canvas']['height'])
    if size!=(w,h):raise ValueError('Reference image and manifest canvas dimensions disagree')
    if m.get('source_sha256') and hashlib.sha256(local_path(root,m['source_image']).read_bytes()).hexdigest()!=m['source_sha256']:
        raise ValueError('Reference image SHA mismatch: source has changed')
    return w,h

def topology(image):
    """Connected components/holes in the active mask; protects medical topology."""
    foreground=(np.asarray(image.convert('L'))>=128).astype(np.uint8)
    n, labels=cv2.connectedComponents(foreground,connectivity=8)
    contours,hierarchy=cv2.findContours(foreground*255,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    holes=0
    if hierarchy is not None:
        for parent in hierarchy[0,:,3]:
            if parent>=0:holes+=1
    return (int(n-1),int(holes))

def records(m):
    return {o['id']:(layer,o) for layer in m.get('layers',[]) for o in layer.get('objects',[])}

class Studio:
    def __init__(self,project,sam2_spec=None,sam2_predictor=None):
        self.root=project.resolve(strict=True)
        self.manifest=self.root/'manifest.json'
        self.history=self.root/'.v25_history'
        self.history.mkdir(exist_ok=True)
        self.lock=threading.RLock()
        self.revision=0
        self.m= self.read()
        self.last_digest=hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        self.size=get_image_size(self.m,self.root)
        with Image.open(local_path(self.root,self.m['source_image'])) as im:
            self.sam2=SAM2StudioEngine(im.copy(),sam2_spec,predictor=sam2_predictor)
        self.pending_sam2={}
        self._ensure_history()

    def read(self):
        m=json.loads(self.manifest.read_text('utf-8'))
        if m.get('schema_version')!='1.0':raise ValueError('Unsupported project schema')
        keys=[o['id'] for l in m.get('layers',[]) for o in l.get('objects',[])]
        if len(keys)!=len(set(keys)):raise ValueError('Duplicate object ids')
        resolve_stack(m)
        return m

    def snapshot(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('manifest.json',self.manifest.read_bytes())
            for _,o in records(self.m).values():
                g=o.get('geometry',{})
                if g.get('type')=='mask_png':
                    rel=g['file']; safe=local_path(self.root,rel)
                    z.write(safe,arcname='project/'+rel)
        return buf.getvalue()

    def _index(self):
        return json.loads((self.history/'index.json').read_text('utf8'))

    def _save_index(self,idx):
        atomic(self.history/'index.json',json.dumps(idx,ensure_ascii=False,indent=2).encode())

    def _ensure_history(self):
        idx=self.history/'index.json'
        if not idx.exists():
            atomic(self.history/'state_000000.zip',self.snapshot())
            self._save_index({'cursor':0,'states':[0], 'next':1})
        else:
            entry=self._index()
            if not (self.history/f"state_{entry['states'][entry['cursor']]:06d}.zip").exists():
                raise ValueError('History is corrupt: missing snapshot')

    def commit(self,new_manifest,changed_mask=None):
        with self.lock:
            get_image_size(new_manifest,self.root)
            resolve_stack(new_manifest)
            atomic(self.manifest,json.dumps(new_manifest,ensure_ascii=False,indent=2).encode('utf8'))
            if changed_mask:
                for rel,data in changed_mask.items():
                    path=(self.root/rel).resolve()
                    if not path.is_relative_to(self.root):raise ValueError('Invalid mask path')
                    atomic(path,data)
            self.m=new_manifest
            self.last_digest=hashlib.sha256(self.manifest.read_bytes()).hexdigest()
            ix=self._index()
            future=ix['states'][ix['cursor']+1:]
            for n in future:(self.history/f'state_{n:06d}.zip').unlink(missing_ok=True)
            ix['states']=ix['states'][:ix['cursor']+1]
            n=ix['next'];ix['next']+=1
            atomic(self.history/f'state_{n:06d}.zip',self.snapshot())
            ix['states'].append(n);ix['cursor']=len(ix['states'])-1
            while len(ix['states'])>MAX_EDITS:
                older=ix['states'].pop(0)
                (self.history/f'state_{older:06d}.zip').unlink(missing_ok=True)
                ix['cursor']-=1
            self._save_index(ix)
            self.revision+=1
            self.pending_sam2.clear()

    def restore(self,delta,expected_revision=None):
        with self.lock:
            if expected_revision is not None and expected_revision!=self.revision:
                raise ValueError('Undo/redo revision changed; reload the page')
            if hashlib.sha256(self.manifest.read_bytes()).hexdigest()!=self.last_digest:
                raise ValueError('Manifest changed outside workbench; stop before undo/redo')
            ix=self._index()
            nextpos=ix['cursor']+delta
            if not 0<=nextpos<len(ix['states']):raise ValueError('No more undo/redo history')
            archive=self.history/f'state_{ix["states"][nextpos]:06d}.zip'
            with zipfile.ZipFile(archive) as z:
                manifest=json.loads(z.read('manifest.json'))
                get_image_size(manifest,self.root)
                resolve_stack(manifest)
                for name in z.namelist():
                    if not name.startswith('project/'):continue
                    rel=name.removeprefix('project/')
                    if not rel or rel.startswith('/') or '..' in Path(rel).parts:raise ValueError('Invalid history file path')
                    dest=(self.root/rel).resolve()
                    if not dest.is_relative_to(self.root):raise ValueError('History path escape')
                    atomic(dest,z.read(name))
                atomic(self.manifest,z.read('manifest.json'))
            ix['cursor']=nextpos; self._save_index(ix)
            self.m=manifest;self.last_digest=hashlib.sha256(self.manifest.read_bytes()).hexdigest();self.revision+=1;self.pending_sam2.clear()

    def public_state(self):
        with self.lock:
            m=self.m; w,h=self.size
            order,edges,_=resolve_stack(m)
            byid=records(m)
            objs=[]
            for oid in order:
                layer,o=byid[oid]
                g=o.get('geometry',{})
                item={'id':oid,'label':o.get('name_zh',oid),'label_en':o.get('name_en',oid),
                      'layer':layer['id'],'type':g.get('type'), 'fill':o.get('fill','none'),
                      'stroke':o.get('stroke','none'),'stroke_width':o.get('stroke_width',1),
                      'opacity':o.get('opacity',1), 'transform':o.get('transform',''),
                      'editable':g.get('type')=='mask_png' or not o.get('transform'),
                      'd':g.get('d','')}
                if g.get('type')=='mask_png':
                    d,_,_,_=trace_mask(local_path(self.root,g['file']),w,h,0,mode='polygon')
                    item['d']=d
                objs.append(item)
            ix=self._index()
            return {'revision':self.revision,'canvas':{'width':w,'height':h},'objects':objs,
                    'constraints':m.get('occlusion',{}).get('constraints',[]),
                    'can_undo':ix['cursor']>0,'can_redo':ix['cursor']<len(ix['states'])-1,
                    'qa_note':'Changes are editable drafts until build_vector_package.py passes quality gates.',
                    'sam2_status':self.sam2.status}

    def apply(self,data):
        with self.lock:
            if data.get('revision')!=self.revision:
                raise ValueError('Project changed in another browser; reload before editing')
            if hashlib.sha256(self.manifest.read_bytes()).hexdigest()!=self.last_digest:
                raise ValueError('Manifest was changed outside the workbench; restart the workbench before editing')
            kind=data.get('kind');self.m=self.read()
            m=json.loads(json.dumps(self.m))
            refs=records(m)
            oid=data.get('object_id')
            if kind in ('mask_brush','path','convert_mask','appearance'):
                if oid not in refs:raise ValueError('Unknown object')
                obj=refs[oid][1];geom=obj.get('geometry',{})
            if kind=='mask_brush':
                if geom.get('type')!='mask_png':raise ValueError('Brush applies to mask objects only')
                mode=data.get('mode');r=data.get('radius');pts=data.get('points')
                if mode not in ('add','erase') or not isinstance(r,(int,float)) or not 0.5<=r<=80:
                    raise ValueError('Invalid brush mode/radius')
                if not isinstance(pts,list) or not 1<=len(pts)<=4000:raise ValueError('Invalid brush points')
                w,h=self.size
                xy=[]
                for p in pts:
                    if not isinstance(p,list) or len(p)!=2 or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in p):raise ValueError('Invalid stroke coordinates')
                    if not (-r<=p[0]<=w+r and -r<=p[1]<=h+r):raise ValueError('Stroke outside canvas')
                    xy.append((round(p[0]),round(p[1])))
                maskfile=local_path(self.root,geom['file'])
                with Image.open(maskfile) as src:
                    im=src.convert('L').point(lambda x:255 if x>=128 else 0)
                initial_topology=topology(im)
                if im.size!=(w,h):raise ValueError('Mask size mismatch')
                dr=ImageDraw.Draw(im);fill=255 if mode=='add' else 0
                thick=max(1,int(round(2*r)))
                if len(xy)>1:dr.line(xy,fill=fill,width=thick,joint='curve')
                for x,y in xy:dr.ellipse((x-r,y-r,x+r,y+r),fill=fill)
                if not im.getbbox():raise ValueError('Cannot erase an entire object; keep an identifiable part')
                if topology(im)!=initial_topology and data.get('allow_topology_change') is not True:
                    raise ValueError('Brush changes connected components or holes; confirm topology override if intentional')
                tmp=io.BytesIO();im.save(tmp,format='PNG')
                self.commit(m,{geom['file']:tmp.getvalue()})
            elif kind=='convert_mask':
                if geom.get('type')!='mask_png':raise ValueError('Object is not a mask')
                d,_,_,_=trace_mask(local_path(self.root,geom['file']),*self.size,0,mode='polygon')
                geom['original_mask_png']=geom['file'];geom.pop('file',None)
                geom['type']='svg_path';geom['d']=d
                obj['fill_rule']='evenodd'
                self.commit(m)
            elif kind=='path':
                if geom.get('type')!='svg_path' or obj.get('transform'):
                    raise ValueError('Path editing requires an untransformed svg_path')
                d=data.get('d')
                if not isinstance(d,str) or not 3<len(d)<200000 or not PATH_CMD.fullmatch(d) or not re.match(r'^\s*[Mm]',d):
                    raise ValueError('Invalid SVG path data')
                geom['d']=d
                # Render and check validity before writing manifest.
                build_object(obj,self.root,*self.size,0,'polygon')
                self.commit(m)
            elif kind=='appearance':
                from build_vector_package import color
                fill=data.get('fill',obj.get('fill','none'))
                stroke=data.get('stroke',obj.get('stroke','none'))
                sw=data.get('stroke_width',obj.get('stroke_width',1))
                op=data.get('opacity',obj.get('opacity',1))
                color(fill);color(stroke)
                if not isinstance(sw,(float,int)) or not math.isfinite(sw) or not 0<=sw<=40:raise ValueError('Invalid stroke width')
                if not isinstance(op,(float,int)) or not math.isfinite(op) or not 0<op<=1:raise ValueError('Invalid opacity')
                obj.update(fill=fill,stroke=stroke,stroke_width=sw,opacity=op)
                build_object(obj,self.root,*self.size,0,'polygon')
                self.commit(m)
            elif kind in ('occlusion_add','occlusion_remove'):
                conf=m.setdefault('occlusion',{});cons=conf.setdefault('constraints',[])
                behind=data.get('behind');front=data.get('front')
                if not isinstance(behind,str) or not isinstance(front,str):raise ValueError('Choose both objects')
                if kind=='occlusion_add':
                    cons.append({'behind':behind,'front':front,'source':'user_confirmed_v25_studio'})
                else:
                    if not any(c.get('behind')==behind and c.get('front')==front for c in cons):raise ValueError('Unknown constraint')
                    conf['constraints']=[c for c in cons if not (c.get('behind')==behind and c.get('front')==front)]
                resolve_stack(m)
                self.commit(m)
            else:raise ValueError('Unknown operation')
            return self.public_state()

    def sam2_preview(self,body):
        """Preview only: Never edit original or instance mask during inference."""
        with self.lock:
            if body.get('revision')!=self.revision:raise ValueError('Stale revision: reload project')
            oid=body.get('object_id')
            entry=records(self.m).get(oid)
            if not entry or entry[1].get('geometry',{}).get('type')!='mask_png':
                raise ValueError('Select an existing editable mask object for SAM2')
            if self.size[0]*self.size[1]>4_000_000:
                raise ValueError('Workbench SAM2 preview limited to 4 million pixels; crop externally first')
            request={**body,'object_id':oid}
            result=self.sam2.preview(request)
            token=secrets.token_hex(16)
            self.pending_sam2={token:{'revision':self.revision,'object_id':oid,
                'masks':{c['index']:c['mask_png'] for c in result['candidates']},
                'scores':{c['index']:c['score'] for c in result['candidates']},
                'points':request.get('points',[]),'box':request.get('box'),
                'model_spec':self.sam2.model_spec,'device':result['device']}}
            return {'proposal_id':token,'revision':self.revision,
                'candidates':[{k:v for k,v in c.items() if k!='mask_png'} for c in result['candidates']],
                'rejected':result['rejected'],'model_device':result['device'],
                'actual_sam2_inference':result['device']!='test_injected',
                'warning':'SAM2 predicted IoU is not anatomical ground truth. Inspect every mask before acceptance.'}

    def sam2_accept(self,body):
        with self.lock:
            if body.get('revision')!=self.revision:raise ValueError('Stale project revision')
            proposal=self.pending_sam2.get(body.get('proposal_id'))
            if proposal is None or proposal['revision']!=self.revision:raise ValueError('Proposal expired or unknown')
            chosen=body.get('candidate_index')
            if type(chosen) is not int or chosen not in proposal['masks']:raise ValueError('Invalid candidate')
            entry=records(self.m).get(proposal['object_id'])
            if not entry or entry[1]['geometry']['type']!='mask_png':raise ValueError('Mask object changed')
            src=local_path(self.root,entry[1]['geometry']['file'])
            candidate=proposal['masks'][chosen]
            with Image.open(src) as old:
                with Image.open(io.BytesIO(candidate)) as fresh:
                    if old.size!=fresh.size:raise ValueError('SAM2 mask size mismatch')
                    if topology(old)!=topology(fresh) and body.get('allow_topology_change') is not True:
                        raise ValueError('SAM2 changes component/hole topology; confirm override after inspection')
            newm=json.loads(json.dumps(self.m))
            self.commit(newm,{entry[1]['geometry']['file']:candidate})
            # Append-only provenance for accepted model suggestions; no patient data upload.
            # Snapshot undo does NOT rewrite audit history, so a prior acceptance remains traceable.
            import datetime
            audit=self.root/'sam2_studio_audit.jsonl'
            event={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'revision':self.revision,'object_id':proposal['object_id'],
                   'candidate_index':chosen,'sam_predicted_iou':proposal['scores'][chosen],
                   'points':proposal['points'],'box':proposal['box'],
                   'model_spec':proposal['model_spec'],'device':proposal['device'],
                   'mask_sha256':hashlib.sha256(candidate).hexdigest(),
                   'operator_confirmation':True,'anatomy_verified_automatically':False}
            with audit.open('a',encoding='utf8') as f:f.write(json.dumps(event,ensure_ascii=False)+'\n')
            return self.public_state()

    def diff_preview(self,body):
        with self.lock:
            if body.get('revision')!=self.revision:raise ValueError('Stale project revision')
            roi=None
            if body.get('object_id'):
                entry=records(self.m).get(body['object_id'])
                if entry is None:raise ValueError('Unknown ROI object')
                g,_=build_object(entry[1],self.root,*self.size,0,'polygon')
                from build_vector_package import visible_bbox
                x,y,w,h=visible_bbox(g,*self.size)
                pad=12;W,H=self.size
                roi=[max(0,x-pad),max(0,y-pad),min(W,x+w+pad),min(H,y+h+pad)]
            result=analyze_project(self.m,self.root,local_path(self.root,self.m['source_image']),
                                   roi=roi,threshold=float(body.get('threshold',15)))
            return {'revision':self.revision,'metrics':result['metrics'],
                'image':'data:image/png;base64,'+base64.b64encode(result['image_png']).decode('ascii')}

    def export(self,allow_draft=False):
        with self.lock:
            stamp=time.strftime('%Y%m%d_%H%M%S')
            base=self.root/'exports_v30'
            base.mkdir(exist_ok=True)
            out=base/f'export_{stamp}_{self.revision:03d}'
            command=[sys.executable,str(HERE/'build_vector_package.py'),'--project',str(self.root),'--out',str(out)]
            if allow_draft:command.append('--allow-draft')
            try:p=subprocess.run(command,text=True,capture_output=True,timeout=180)
            except subprocess.TimeoutExpired:raise ValueError('Export timed out; see project files')
            answer={'ok':p.returncode==0,'out':str(out),'log':(p.stdout+'\n'+p.stderr)[-5000:]}
            if p.returncode!=0:
                answer['warning']='QA failed; do not treat this export as validated.'
                return answer
            # Prepare (not execute) the Illustrator import. No AI file is claimed.
            from illustrator_import import prepare
            import zipfile
            try:
                dest=out/'18_Illustrator_Import'
                info=prepare(self.root,dest)
                with zipfile.ZipFile(out/'08_All_Files.zip','a',compression=zipfile.ZIP_DEFLATED) as z:
                    for f in sorted(dest.rglob('*')):
                        if f.is_file():z.write(f,'18_Illustrator_Import/'+f.relative_to(dest).as_posix())
                answer['illustrator_staging']=str(dest)
                answer['native_ai_created']=False
            except Exception as exc:
                answer['warning']='SVG export passed, but Illustrator staging failed: '+str(exc)
                answer['illustrator_staging_ok']=False
            return answer

class Handler(BaseHTTPRequestHandler):
    server_version='VectorizerStudio/3.1'
    def log_message(self,fmt,*args):pass
    def respond(self,code,data,ctype='application/json'):
        raw=json.dumps(data,ensure_ascii=False).encode() if ctype=='application/json' else data
        self.send_response(code);self.send_header('Content-Type',ctype+'; charset=utf-8' if ctype.startswith('text') or ctype=='application/json' else ctype)
        self.send_header('Content-Length',str(len(raw)));self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        u=urlparse(self.path)
        try:
            if u.path in ('/','/index.html'):
                return self.respond(200,(STATIC/'index.html').read_bytes(),'text/html')
            if u.path in ('/static/app.js','/static/style.css'):
                name=u.path.split('/')[-1]
                return self.respond(200,(STATIC/name).read_bytes(),'text/javascript' if name.endswith('.js') else 'text/css')
            if u.path=='/api/project':return self.respond(200,self.server.studio.public_state())
            if u.path=='/api/source':
                s=self.server.studio
                with Image.open(local_path(s.root,s.m['source_image'])) as im:
                    buffer=io.BytesIO();im.convert('RGBA').save(buffer,'PNG')
                return self.respond(200,buffer.getvalue(),'image/png')
            if u.path=='/api/mask':
                oid=parse_qs(u.query).get('id',[''])[0]
                s=self.server.studio;entry=records(s.m).get(oid)
                if entry is None or entry[1].get('geometry',{}).get('type')!='mask_png':raise ValueError('Unknown mask object')
                path=local_path(s.root,entry[1]['geometry']['file'])
                return self.respond(200,path.read_bytes(),'image/png')
            return self.respond(404,{'error':'Not found'})
        except Exception as e:self.respond(400,{'error':str(e)})
    def do_POST(self):
        host=self.headers.get('Host','')
        origin=self.headers.get('Origin','')
        # Local-only HTTP service. Refuse cross-site browser POST.
        allowed=('127.0.0.1','localhost','[::1]')
        port=self.server.server_port
        approved_origins={f'http://127.0.0.1:{port}',f'http://localhost:{port}'}
        if host.split(':')[0] not in allowed or (origin and origin not in approved_origins):
            return self.respond(403,{'error':'Local origin required'})
        length=int(self.headers.get('Content-Length','0'))
        if length<1 or length>MAX_BODY:return self.respond(413,{'error':'Request size limit exceeded'})
        try:
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):raise ValueError('Expected JSON object')
            s=self.server.studio
            if self.path=='/api/edit': result=s.apply(body)
            elif self.path=='/api/undo':s.restore(-1,body.get('revision'));result=s.public_state()
            elif self.path=='/api/redo':s.restore(1,body.get('revision'));result=s.public_state()
            elif self.path=='/api/export':result=s.export(body.get('allow_draft') is True)
            elif self.path=='/api/sam2/preview':result=s.sam2_preview(body)
            elif self.path=='/api/sam2/accept':result=s.sam2_accept(body)
            elif self.path=='/api/diff':result=s.diff_preview(body)
            else:return self.respond(404,{'error':'Not found'})
            self.respond(200,result)
        except (ValueError,KeyError,TypeError,RuntimeError) as e:self.respond(400,{'error':str(e)})
        except Exception as e:self.respond(500,{'error':type(e).__name__+': '+str(e)})

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',required=True,type=Path)
    p.add_argument('--port',type=int,default=8765)
    p.add_argument('--no-browser',action='store_true')
    p.add_argument('--sam2-hf-model',default=None,help='Explicit opt-in: may download model from Hugging Face')
    p.add_argument('--sam2-config',default=None)
    p.add_argument('--sam2-checkpoint',default=None,type=Path)
    p.add_argument('--sam2-device',default=None,choices=('auto','cpu','cuda','mps'))
    a=p.parse_args()
    if not 1024<=a.port<=65535:p.error('port must be in 1024..65535')
    try:spec=resolve_model_spec(a.sam2_hf_model,a.sam2_config,a.sam2_checkpoint,a.sam2_device)
    except (ValueError,OSError) as exc:p.error(str(exc))
    server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler)
    server.studio=Studio(a.project,sam2_spec=spec)
    url=f'http://127.0.0.1:{a.port}/'
    print('LayerTrace studio: '+url,flush=True)
    print('Edit project: '+str(a.project.resolve()),flush=True)
    if not a.no_browser:
        import webbrowser;webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    server.server_close()

if __name__=='__main__':main()
