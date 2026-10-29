/* Native editable SVG importer. SPEC is generated locally by illustrator_native.py. */
(function(){
var previous=app.userInteractionLevel;
function quote(s){s=String(s);var out='"',bs=String.fromCharCode(92);for(var i=0;i<s.length;i++){var c=s.charAt(i),code=s.charCodeAt(i);if(code===34||code===92)out+=bs+c;else if(code<32)out+=bs+'u'+('0000'+code.toString(16)).slice(-4);else out+=c;}return out+'"';}
function json(v){if(v===null)return 'null';if(typeof v==='string')return quote(v);if(typeof v==='number'||typeof v==='boolean')return String(v);var a=[],k;if(v instanceof Array){for(k=0;k<v.length;k++)a.push(json(v[k]));return '['+a.join(',')+']';}for(k in v)if(v.hasOwnProperty(k))a.push(quote(k)+':'+json(v[k]));return '{'+a.join(',')+'}';}
function write(path,value){var f=new File(path);f.encoding='UTF-8';if(!f.open('w'))throw Error('Cannot write report');f.write(json(value));f.close();}
function stats(doc){var r={layers:doc.layers.length,paths:doc.pathItems.length,text_frames:doc.textFrames.length,raster_items:doc.rasterItems.length,placed_items:doc.placedItems.length,stroked_paths:0,open_stroked_paths:0,anchors:0,layer_names:[]};for(var i=0;i<doc.layers.length;i++)r.layer_names.push(doc.layers[i].name);for(i=0;i<doc.pathItems.length;i++){var p=doc.pathItems[i];r.anchors+=p.pathPoints.length;if(p.stroked){r.stroked_paths++;if(!p.closed)r.open_stroked_paths++;}}return r;}
var doc=null;
var jobs=SPEC.jobs;
var base=new File($.fileName).parent;
for(var ji=0;ji<jobs.length;ji++){
 for(var fi=0;fi<4;fi++){var field=['input','output','report','preview'][fi];jobs[ji][field]=new File(base.fsName+'/'+jobs[ji][field]).fsName;}
}
for(var k=0;k<jobs.length;k++){
 if(new File(jobs[k].output).exists||new File(jobs[k].report).exists)throw Error('Output/report already exists');
 for(var di=0;di<app.documents.length;di++){
  try{var path=app.documents[di].fullName.fsName;if(path===new File(jobs[k].input).fsName||path===new File(jobs[k].output).fsName)throw Error('Input or output already open in Illustrator');}
  catch(e){if(e.message==='Input or output already open in Illustrator')throw e;}
 }
}
var results=[];
for(var jobIndex=0;jobIndex<jobs.length;jobIndex++){
var job=jobs[jobIndex];
try{
app.userInteractionLevel=UserInteractionLevel.DONTDISPLAYALERTS;
var input=new File(job.input),output=new File(job.output);
if(output.exists)throw Error('Native AI already exists; refusing overwrite');
doc=app.open(input);if(!doc)throw Error('SVG import failed');
var roots={},i,j,g;
for(i=0;i<doc.groupItems.length;i++){g=doc.groupItems[i];if(g.parent.typename==='Layer')roots[g.name.replace(/ /g,'_')]=g;}
var originalLayers=[];for(i=0;i<doc.layers.length;i++)originalLayers.push(doc.layers[i]);
var imported=[];
for(i=0;i<job.parts.length;i++){
 var part=job.parts[i];g=roots[part.id];
 if(!g)throw Error('Missing part group: '+part.id);
 var layer=doc.layers.add();layer.name=part.name;g.move(layer,ElementPlacement.PLACEATEND);g.name=part.id;imported.push(part.id);
}
for(i=0;i<originalLayers.length;i++){if(originalLayers[i].pageItems.length!==0)throw Error('Unassigned imported geometry remains');originalLayers[i].remove();}
if(imported.length!==job.parts.length||doc.layers.length!==job.parts.length)throw Error('Layer count mismatch');
if(Math.abs(doc.width-job.width)>.01||Math.abs(doc.height-job.height)>.01)throw Error('Canvas mismatch');
var before=stats(doc);if(before.raster_items||before.placed_items)throw Error('Unexpected raster or placed artwork');
var strokeTest=false,anchorTest=false;
for(i=0;i<doc.pathItems.length;i++){
 var path=doc.pathItems[i];if(!path.stroked||path.closed||path.pathPoints.length<2)continue;
 var sw=path.strokeWidth;path.strokeWidth=sw+1;if(Math.abs(path.strokeWidth-sw-1)>.001)throw Error('Stroke width editing failed');path.strokeWidth=sw;strokeTest=true;
 var pt=path.pathPoints[0],a=pt.anchor,l=pt.leftDirection,r=pt.rightDirection;pt.anchor=[a[0]+.25,a[1]];if(Math.abs(pt.anchor[0]-a[0]-.25)>.001)throw Error('Anchor editing failed');pt.anchor=a;pt.leftDirection=l;pt.rightDirection=r;anchorTest=true;break;
}
if(job.requires_open_stroke&&(!strokeTest||!anchorTest))throw Error('Required editable open stroke missing');
var options=new IllustratorSaveOptions();options.pdfCompatible=true;options.compressed=true;
doc.saveAs(output,options);doc.close(SaveOptions.DONOTSAVECHANGES);doc=null;
if(!output.exists||output.length<1000)throw Error('AI save failed');
doc=app.open(output);var reopened=stats(doc);
if(reopened.paths!==before.paths||reopened.text_frames!==before.text_frames||reopened.layers!==before.layers||reopened.anchors!==before.anchors||reopened.stroked_paths!==before.stroked_paths||reopened.open_stroked_paths!==before.open_stroked_paths||reopened.raster_items||reopened.placed_items)throw Error('AI reopen verification failed');
var png=new ExportOptionsPNG24();png.antiAliasing=true;png.artBoardClipping=true;png.transparency=true;png.horizontalScale=100;png.verticalScale=100;
doc.exportFile(new File(job.preview),ExportType.PNG24,png);
var result={version:'1.0.0',illustrator_version:app.version,native_ai_created:true,ai_file:output.name,save_and_reopen_verified:true,stroke_width_edit_test:strokeTest,anchor_edit_test:anchorTest,parts_imported:imported,structure:reopened,canvas_points:{width:doc.width,height:doc.height},visual_fidelity_requires_review:true};
write(job.report,result);
doc.close(SaveOptions.DONOTSAVECHANGES);doc=null;
results.push(result);
}catch(error){if(doc){try{doc.close(SaveOptions.DONOTSAVECHANGES);}catch(ignored){}}throw error;}
finally{app.userInteractionLevel=previous;}
}
return json(results);
})();
