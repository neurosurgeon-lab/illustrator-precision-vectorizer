'use strict';
const NS='http://www.w3.org/2000/svg';
const $=id=>document.getElementById(id);
let data=null, selected=null, tool='select', view='overlay', hidden=new Set(), pointer=null;
let zoom=1, position={x:0,y:0}, editableSegments=null, guideNodes=[];
let samPoints=[],samBox=null,samProposal=null,diffData=null;
const S=$('artboard'), P=$('paths'), G=$('guides'), L=$('liveStroke');
const esc=val=>String(val).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function el(tag,attrs={},parent=null){const n=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,String(v)));if(parent)parent.appendChild(n);return n;}
async function request(path,body){const res=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const msg=await res.json();if(!res.ok)throw Error(msg.error||'操作失败');return msg;}
function error(e){$('status').textContent='错误：'+e.message;$('status').style.color='#aa4141';window.setTimeout(()=>{$('status').style.color='';},4000);}
function note(msg){$('status').textContent=msg;}
async function load(){try{const res=await fetch('/api/project',{cache:'no-store'});if(!res.ok)throw Error('Cannot load project');data=await res.json();if(!selected||!data.objects.some(x=>x.id===selected))selected=data.objects.find(x=>x.type!=='svg_path'||!x.id.toLowerCase().includes('background'))?.id||data.objects[0]?.id;setSize();paint();}catch(e){error(e);}}
function obj(){return data?.objects.find(x=>x.id===selected);}
function setSize(){const {width:w,height:h}=data.canvas;S.setAttribute('viewBox',`0 0 ${w} ${h}`);$('backgrid').setAttribute('width',w);$('backgrid').setAttribute('height',h);$('reference').setAttribute('width',w);$('reference').setAttribute('height',h);$('differenceOverlay').setAttribute('width',w);$('differenceOverlay').setAttribute('height',h);$('samOverlay').setAttribute('width',w);$('samOverlay').setAttribute('height',h);setZoom();}
function setZoom(){if(!data)return;let {width:w,height:h}=data.canvas;const a=w/zoom,b=h/zoom;position.x=Math.max(0,Math.min(w-a,position.x));position.y=Math.max(0,Math.min(h-b,position.y));S.setAttribute('viewBox',`${position.x} ${position.y} ${a} ${b}`);$('zoomText').textContent=Math.round(zoom*100)+'%';}
function coords(e){const point=S.createSVGPoint();point.x=e.clientX;point.y=e.clientY;const matrix=S.getScreenCTM();if(!matrix)return {x:0,y:0};const p=point.matrixTransform(matrix.inverse());return {x:p.x,y:p.y};}
function styleModes(){const original=view==='reference', mask=view==='mask', overlay=view==='overlay', difference=view==='difference';$('reference').setAttribute('visibility',view==='vector'||mask||difference?'hidden':'visible');
 $('differenceOverlay').setAttribute('visibility',difference&&diffData?'visible':'hidden');
 $('samOverlay').setAttribute('visibility',samProposal&&view!=='difference'?'visible':'hidden');P.setAttribute('opacity',original?'0':overlay?'0.85':'1');P.setAttribute('visibility',original||difference?'hidden':'visible');G.setAttribute('visibility',tool==='anchors'&&!original?'visible':'hidden');}
function paint(){if(!data)return;const o=obj();P.replaceChildren();G.replaceChildren();L.replaceChildren();$('objectCount').textContent=data.objects.length+' 个';$('saveState').textContent='已保存 · 修订 '+data.revision;$('undo').disabled=!data.can_undo;$('redo').disabled=!data.can_redo;
 data.objects.forEach(x=>{if(hidden.has(x.id))return;if(view==='mask'&&x.id!==selected)return;const outlined=view==='overlay';const p=el('path',{d:x.d,fill:outlined?'none':view==='mask'?'#418ab6':x.fill,stroke:outlined?(x.id===selected?'#e16c59':'#1986b0'):x.stroke,'stroke-width':outlined?(x.id===selected?2:1.2):x.stroke_width,'stroke-linecap':'round','stroke-linejoin':'round','fill-rule':'evenodd',opacity:x.opacity,'data-id':x.id,transform:x.transform||''},P);if(x.id===selected&&!['reference','mask'].includes(view))p.classList.add('selected-path');});
 if(o){$('selectedName').textContent=o.label+' · '+o.id;$('fillColor').value=o.fill;$('strokeColor').value=o.stroke;$('strokeWidth').value=o.stroke_width;$('opacity').value=o.opacity;$('pathData').value=o.type==='svg_path'?o.d:'';$('convert').disabled=o.type!=='mask_png';$('applyPath').disabled=o.type!=='svg_path'||!!o.transform;$('pathData').disabled=o.type!=='svg_path'||!!o.transform;}
 renderList();renderConstraints();renderGuides();renderSamPrompts();styleModes();$('samStatus').textContent='SAM2：'+data.sam2_status+' · 当前提示点 '+samPoints.length+' 个';$('brushCursor').setAttribute('visibility','hidden');}
function renderList(){const layers=new Map();for(const x of data.objects){if(!layers.has(x.layer))layers.set(x.layer,[]);layers.get(x.layer).push(x);}const box=$('layerList');box.replaceChildren();for(const [layer,items] of layers){const head=document.createElement('div');head.className='layer-heading';head.textContent=layer;box.appendChild(head);for(const x of items){const row=document.createElement('div');row.className='layer-item'+(selected===x.id?' active':'');row.title=x.id;const sw=document.createElement('span');sw.className='swatch';sw.style.background=x.fill!=='none'?x.fill:x.stroke!=='none'?x.stroke:'#fff';row.appendChild(sw);const label=document.createElement('span');label.className='obj-label';label.textContent=x.label;row.appendChild(label);const eye=document.createElement('button');eye.className='eye';eye.textContent=hidden.has(x.id)?'◌':'◉';eye.title='仅切换工作台显示，不修改交付文件';eye.onclick=e=>{e.stopPropagation();hidden.has(x.id)?hidden.delete(x.id):hidden.add(x.id);paint();};row.appendChild(eye);row.onclick=()=>{if(selected!==x.id)clearSam();selected=x.id;diffData=null;paint();};box.appendChild(row);}}}
function renderConstraints(){for(const id of ['behind','front']){const select=$(id);const previous=select.value;select.replaceChildren();for(const x of data.objects){const option=document.createElement('option');option.value=x.id;option.textContent=x.label+' / '+x.id;select.appendChild(option);}if(data.objects.some(x=>x.id===previous))select.value=previous;else if(id==='behind'&&selected)select.value=selected;else if(id==='front')select.selectedIndex=Math.min(1,select.options.length-1);}const c=$('constraintList');c.replaceChildren();data.constraints.forEach(row=>{const div=document.createElement('div');div.className='constraint';const span=document.createElement('span');span.textContent=`${row.behind} → ${row.front}`;div.appendChild(span);const b=document.createElement('button');b.textContent='删除';b.onclick=()=>mutate({kind:'occlusion_remove',behind:row.behind,front:row.front},'已删除层级关系');div.appendChild(b);c.appendChild(div);});}
function setTool(t){tool=t;document.querySelectorAll('[data-tool]').forEach(b=>b.classList.toggle('active',b.dataset.tool===t));S.dataset.tool=t;paint();note(t==='anchors'?'拖动蓝色节点与空心手柄；只支持 M/L/C/Q 绝对坐标':'已切换工具：'+t);}
function setView(v){view=v;document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===v));paint();}
async function mutate(changed,success){if(!data)return;try{document.body.style.cursor='wait';const state=await request('/api/edit',{revision:data.revision,...changed});data=state;samProposal=null;diffData=null;paint();note(success||'已保存');}catch(e){error(e);await load();}finally{document.body.style.cursor='';}}
function parseSimple(d){ // Only path commands we can edit without changing semantics.
 const tokens=d.match(/[MLCQZmlcqzAaHhVvSsTt]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?/g);
 if(!tokens||!tokens.length)return null;
 if(/[aAhHvVsStTmlcqz]/.test(tokens.filter(t=>/^[A-Za-z]$/.test(t)).join('')))return null;
 const size={M:2,L:2,C:6,Q:4,Z:0};let i=0,c=null,segments=[];
 while(i<tokens.length){if(/^[MLCQZ]$/.test(tokens[i]))c=tokens[i++];else if(!c||c==='Z')return null;if(!size.hasOwnProperty(c))return null;if(c==='Z'){segments.push({cmd:'Z',numbers:[]});c=null;continue;}
  let count=size[c],num=[];for(let j=0;j<count;j++){if(i>=tokens.length||/^[A-Za-z]$/.test(tokens[i]))return null;num.push(Number(tokens[i++]));}
  if(!num.every(Number.isFinite))return null;segments.push({cmd:c,numbers:num});if(c==='M')c='L';if(segments.length>5000)return null;}
 return segments;
}
function stringifySegments(segs){return segs.map(s=>s.cmd==='Z'?'Z':s.cmd+' '+s.numbers.map(n=>Number(n.toFixed(3))).join(' ')).join(' ');}
function renderGuides(){G.replaceChildren();guideNodes=[];editableSegments=null;const o=obj();if(tool!=='anchors'||!o||o.type!=='svg_path'||o.transform)return;editableSegments=parseSimple(o.d);if(!editableSegments){note('此路径含圆弧/相对命令等，节点拖动未启用；保留原始路径，可通过源码精修。');return;}
 let last=null;editableSegments.forEach((seg,index)=>{if(seg.cmd==='Z')return;const n=seg.numbers;const anchorIdx=seg.cmd==='C'?4:seg.cmd==='Q'?2:0;
  const anchor={x:n[anchorIdx],y:n[anchorIdx+1],index,coord:anchorIdx};
  if(seg.cmd==='C'||seg.cmd==='Q'){for(let c=0;c<anchorIdx;c+=2){const p={x:n[c],y:n[c+1],index,coord:c};if(last&&c===0)el('line',{x1:last.x,y1:last.y,x2:p.x,y2:p.y,class:'guide'},G);if(c===2)el('line',{x1:anchor.x,y1:anchor.y,x2:p.x,y2:p.y,class:'guide'},G);drawHandle(p,false);}}
  drawHandle(anchor,true);last=anchor;});}
function drawHandle(p,isAnchor){const circle=el('circle',{cx:p.x,cy:p.y,r:4, class:isAnchor?'handle anchor':'handle','data-seg':p.index,'data-coord':p.coord},G);circle.addEventListener('pointerdown',e=>{e.stopPropagation();pointer={kind:'handle',seg:p.index,coord:p.coord};S.setPointerCapture(e.pointerId);});}
function resetStroke(){pointer=null;L.replaceChildren();$('brushCursor').setAttribute('visibility','hidden');}
function brushLine(){L.replaceChildren();if(!pointer||pointer.kind!=='brush')return;const p=pointer.points;if(!p.length)return;let d='M '+p[0].join(' ');for(let i=1;i<p.length;i++)d+=' L '+p[i].join(' ');el('path',{d,fill:'none',stroke:tool==='brush-erase'?'#e86b70':'#1a9c9f','stroke-width':2*Number($('radius').value),'stroke-linecap':'round',opacity:'.5'},L);}
S.addEventListener('pointerdown',e=>{if(!data||e.button!==0)return;const p=coords(e);if(tool==='brush-add'||tool==='brush-erase'){if(obj()?.type!=='mask_png'){note('先选择左侧的蒙版对象');return;}pointer={kind:'brush',points:[[p.x,p.y]],id:selected};S.setPointerCapture(e.pointerId);brushLine();return;}if(tool==='sam-pos'||tool==='sam-neg'){
   if(obj()?.type!=='mask_png'){note('SAM2 提示仅支持所选蒙版对象');return;}
   samPoints.push({x:Math.max(0,Math.min(data.canvas.width-1,p.x)),y:Math.max(0,Math.min(data.canvas.height-1,p.y)),label:tool==='sam-pos'?1:0});
   samProposal=null;renderSamPrompts();note('提示点 '+samPoints.length+' 个');return;
 }
 if(tool==='sam-box'){
   pointer={kind:'sam-box',start:[p.x,p.y],end:[p.x,p.y]};S.setPointerCapture(e.pointerId);renderSamPrompts();return;
 }
 if(tool==='select'){const id=e.target.getAttribute('data-id');if(id){if(selected!==id)clearSam();selected=id;diffData=null;paint();}return;}});
S.addEventListener('pointermove',e=>{if(!data)return;const p=coords(e);$('coord').textContent=`x ${p.x.toFixed(1)} / y ${p.y.toFixed(1)}`;if(tool.startsWith('brush')){const circle=$('brushCursor');circle.setAttribute('cx',p.x);circle.setAttribute('cy',p.y);circle.setAttribute('r',$('radius').value);circle.setAttribute('visibility','visible');}
 if(!pointer)return;if(pointer.kind==='brush'){const points=pointer.points;const prev=points[points.length-1];if(Math.hypot(prev[0]-p.x,prev[1]-p.y)>=0.4&&points.length<4000)points.push([p.x,p.y]);brushLine();}
 else if(pointer.kind==='sam-box'){pointer.end=[p.x,p.y];renderSamPrompts();}
 else if(pointer.kind==='handle'&&editableSegments){const ns=editableSegments[pointer.seg].numbers;ns[pointer.coord]=p.x;ns[pointer.coord+1]=p.y;const d=stringifySegments(editableSegments);const node=[...P.children].find(x=>x.getAttribute('data-id')===selected);if(node)node.setAttribute('d',d);$('pathData').value=d;if(obj())obj().d=d;renderGuides();}});
S.addEventListener('pointerup',async e=>{if(!pointer)return;const temp=pointer;resetStroke();if(temp.kind==='brush'){if(temp.points.length<1)return;await mutate({kind:'mask_brush',object_id:temp.id,mode:tool==='brush-add'?'add':'erase',radius:Number($('radius').value),allow_topology_change:$('allowTopology').checked,points:temp.points},'蒙版笔画已写入 PNG，并生成撤销快照');}
 else if(temp.kind==='sam-box'){const a=temp.start,b=temp.end;const xy=[Math.max(0,Math.min(a[0],b[0])),Math.max(0,Math.min(a[1],b[1])),Math.min(data.canvas.width,Math.max(a[0],b[0])),Math.min(data.canvas.height,Math.max(a[1],b[1]))];if(xy[2]-xy[0]>2&&xy[3]-xy[1]>2)samBox=xy;samProposal=null;renderSamPrompts();}
 else if(temp.kind==='handle'){const d=$('pathData').value;await mutate({kind:'path',object_id:selected,d},'Bézier 节点调整已写入 SVG Path');}});
S.addEventListener('pointercancel',()=>{resetStroke();load();});
$('radius').oninput=e=>$('radiusValue').textContent=e.target.value+' px';
document.querySelectorAll('[data-tool]').forEach(b=>b.addEventListener('click',()=>setTool(b.dataset.tool)));
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));
$('applyPath').onclick=()=>{if(obj()?.type!=='svg_path')return;mutate({kind:'path',object_id:selected,d:$('pathData').value},'路径已保存');};
$('applyStyle').onclick=()=>mutate({kind:'appearance',object_id:selected,fill:$('fillColor').value.trim(),stroke:$('strokeColor').value.trim(),stroke_width:Number($('strokeWidth').value),opacity:Number($('opacity').value)},'颜色与描边已保存');
$('convert').onclick=()=>{if(obj()?.type==='mask_png'&&window.confirm('将蒙版轮廓复制到可编辑 SVG 路径？原始蒙版文件保留，且可以撤销。'))mutate({kind:'convert_mask',object_id:selected},'蒙版已转为 SVG Path；原始 PNG 仍保留');};
$('addOrder').onclick=()=>mutate({kind:'occlusion_add',behind:$('behind').value,front:$('front').value},'遮挡次序已写入 Manifest');
$('undo').onclick=async()=>{try{data=await request('/api/undo',{revision:data.revision});clearSam();diffData=null;paint();note('已撤销并恢复工程快照');}catch(e){error(e);}};
$('redo').onclick=async()=>{try{data=await request('/api/redo',{revision:data.revision});clearSam();diffData=null;paint();note('已恢复后续工程快照');}catch(e){error(e);}};
$('export').onclick=async()=>{const b=$('export');b.disabled=true;const log=$('exportLog');log.style.display='block';log.textContent='正在运行完整 SVG 组装与 QA…';try{const r=await request('/api/export',{allow_draft:$('allowDraft').checked});log.textContent=(r.ok?'导出成功：':'质量门禁未通过：')+'\n'+r.out+'\n'+r.log;note(r.ok?'导出完成；检查质量报告':'导出被质量门禁拦截');}catch(e){log.textContent=e.message;error(e);}finally{b.disabled=false;}};
$('zoomIn').onclick=()=>{zoom=Math.min(8,zoom*1.4);setZoom();};$('zoomOut').onclick=()=>{zoom=Math.max(1,zoom/1.4);setZoom();};$('zoomReset').onclick=()=>{zoom=1;position={x:0,y:0};setZoom();};
S.addEventListener('wheel',e=>{if(e.ctrlKey||e.metaKey){e.preventDefault();zoom=Math.max(1,Math.min(8,zoom*(e.deltaY<0?1.15:1/1.15)));setZoom();}},{passive:false});
window.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'&&!['TEXTAREA','INPUT'].includes(document.activeElement.tagName)){e.preventDefault();(e.shiftKey?$('redo'):$('undo')).click();}});

function renderSamPrompts(){
 const target=$('samPrompts');target.replaceChildren();
 for(const p of samPoints){el('circle',{cx:p.x,cy:p.y,r:4,fill:p.label===1?'#29b66b':'#e34c4c',stroke:'#fff','stroke-width':1.5},target);}
 const box=pointer?.kind==='sam-box'?(()=>{const a=pointer.start,b=pointer.end;return [Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.abs(a[0]-b[0]),Math.abs(a[1]-b[1])];})():samBox?[samBox[0],samBox[1],samBox[2]-samBox[0],samBox[3]-samBox[1]]:null;
 if(box)el('rect',{x:box[0],y:box[1],width:box[2],height:box[3],fill:'none',stroke:'#dc8b20','stroke-width':2,'stroke-dasharray':'5 3'},target);
}
function clearSam(){samPoints=[];samBox=null;samProposal=null;$('samOverlay').setAttribute('visibility','hidden');$('samCandidate').replaceChildren();renderSamPrompts();note('SAM2 提示已清空');}
$('samClear').onclick=clearSam;
$('samPreviewButton').onclick=async()=>{
 if(!obj()||obj().type!=='mask_png')return note('先选择已有蒙版对象');
 const b=$('samPreviewButton');b.disabled=true;
 try{
  const r=await request('/api/sam2/preview',{revision:data.revision,object_id:selected,points:samPoints,box:samBox,profile:$('samProfile').value});
  samProposal=r;const picker=$('samCandidate');picker.replaceChildren();
  for(const c of r.candidates){const opt=document.createElement('option');opt.value=String(c.index);opt.textContent=`候选 ${c.index} · 预测质量 ${c.score.toFixed(3)} · ${c.pixel_count} px`;picker.appendChild(opt);}
  showSamCandidate();note(`SAM2：${r.candidates.length} 个候选，${r.rejected.length} 个拒绝 · ${r.model_device}`);
 }catch(e){error(e);}finally{b.disabled=false;}
};
function showSamCandidate(){if(!samProposal)return;const c=samProposal.candidates.find(x=>String(x.index)===$('samCandidate').value);if(!c){$('samOverlay').setAttribute('visibility','hidden');return;}$('samOverlay').setAttribute('href',c.data_uri);$('samOverlay').setAttribute('visibility','visible');}
$('samCandidate').onchange=showSamCandidate;
$('samAccept').onclick=async()=>{if(!samProposal)return note('请先生成并审核候选蒙版');if(!window.confirm('确认蒙版边界、端点、电极内孔和遮挡均正确？写回后可撤销。'))return;
 try{data=await request('/api/sam2/accept',{revision:data.revision,proposal_id:samProposal.proposal_id,candidate_index:Number($('samCandidate').value),allow_topology_change:$('samAllowTopology').checked});clearSam();diffData=null;paint();note('已将 SAM2 结果写入所选蒙版，可撤销');}catch(e){error(e);}
};
$('diffCompute').onclick=async()=>{const b=$('diffCompute');b.disabled=true;try{const r=await request('/api/diff',{revision:data.revision,object_id:$('diffScope').value==='selected'?selected:null,threshold:Number($('diffThreshold').value)});diffData=r;$('differenceOverlay').setAttribute('href',r.image);$('diffMetrics').style.display='block';$('diffMetrics').textContent=JSON.stringify(r.metrics,null,2);setView('difference');note('热图计算完成：这是像素差异，不是医学解剖精度');}catch(e){error(e);}finally{b.disabled=false;}};

load();
