#!/usr/bin/env python3
"""High-fidelity closed-mask tracing. Semantic segmentation must happen beforehand.

Polygon mode preserves original OpenCV contour vertices. Adaptive Bezier mode is
validated against the raster baseline and falls back on polygon when it changes
shape excessively. Neither mode guarantees subpixel recovery from a raster.
"""
import io
import math
import cv2
import numpy as np
import cairosvg
from PIL import Image


def contour_poly(contour, epsilon):
    pts = cv2.approxPolyDP(contour, epsilon, True).reshape((-1, 2)) if epsilon else contour.reshape((-1, 2))
    if len(pts) < 3:
        return ''
    return 'M ' + ' L '.join(f'{float(x):g},{float(y):g}' for x,y in pts) + ' Z'


def contour_bezier(contour, epsilon=0.55, corner_angle=105):
    """Closed Catmull-Rom to cubic, corner protected by zero tangents.

    We use clamped tangents near corners. Validation *must* happen before use.
    """
    p = cv2.approxPolyDP(contour, max(epsilon, 0.35), True).reshape(-1, 2).astype(float)
    n = len(p)
    if n < 5:
        return contour_poly(contour, 0)
    tangents=[]
    for i in range(n):
        prev, cur, nxt = p[(i-1)%n], p[i], p[(i+1)%n]
        a=prev-cur; b=nxt-cur
        co=float(np.dot(a,b)/(max(np.linalg.norm(a)*np.linalg.norm(b),1e-8)))
        # Small interior angle = corner; do not smooth it.
        ang=math.degrees(math.acos(min(1,max(-1,co))))
        tangents.append(np.array((0.,0.)) if ang<corner_angle else (nxt-prev)/2)
    cmd=[f'M {p[0,0]:.3f},{p[0,1]:.3f}']
    for i in range(n):
        nxt=(i+1)%n
        c1=p[i]+tangents[i]/3
        c2=p[nxt]-tangents[nxt]/3
        cmd.append(f'C {c1[0]:.3f},{c1[1]:.3f} {c2[0]:.3f},{c2[1]:.3f} {p[nxt,0]:.3f},{p[nxt,1]:.3f}')
    cmd.append('Z')
    return ' '.join(cmd)


def render_binary(d,w,h):
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><path d="{d}" fill="#FFFFFF" fill-rule="evenodd"/></svg>'
    arr=np.asarray(Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode()))).convert('RGBA'))
    return arr[:,:,3]>=128


def trace_mask(path,w,h,epsilon=0.0,mode='polygon',min_iou=.985,max_boundary_error_px=1.5):
    with Image.open(path) as im:
        if im.size!=(w,h):
            raise ValueError(f'Mask {path} size {im.size}, expected {(w,h)}')
        gray=np.asarray(im.convert('L'))
    binary=(gray>=128).astype(np.uint8)
    if not np.any(binary):
        raise ValueError(f'Mask {path} is empty')
    contours,_=cv2.findContours(binary*255,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    polys=[contour_poly(c,epsilon) for c in contours if len(c)>=3]
    if not polys:raise ValueError(f'Mask {path} has no closed contours')
    baseline=' '.join(polys)
    ys,xs=np.where(binary>0)
    bbox=[int(xs.min()),int(ys.min()),int(xs.max()-xs.min()+1),int(ys.max()-ys.min()+1)]
    details={'trace_mode_requested':mode,'trace_mode_used':'polygon','curve_fallback_reason':None,
             'mask_ink_pixels':int(binary.sum()), 'contour_count':len(polys)}
    if mode=='adaptive-bezier':
        candidates=[contour_bezier(c) for c in contours if len(c)>=3]
        d=' '.join(candidates)
        # Validate the candidate vs the polygon baseline, not an idealized smooth ellipse.
        a=render_binary(baseline,w,h);b=render_binary(d,w,h)
        union=int(np.count_nonzero(a|b));inter=int(np.count_nonzero(a&b))
        iou=inter/union if union else 0
        # 95th percentile of boundary distances in both directions.
        e1=cv2.Canny(a.astype('uint8')*255,30,100)>0
        e2=cv2.Canny(b.astype('uint8')*255,30,100)>0
        dist1=cv2.distanceTransform((~e1).astype('uint8'),cv2.DIST_L2,3)
        dist2=cv2.distanceTransform((~e2).astype('uint8'),cv2.DIST_L2,3)
        vals=np.concatenate([dist1[e2],dist2[e1]])
        q95=float(np.percentile(vals,95)) if len(vals) else float('inf')
        details.update({'bezier_vs_polygon_iou':round(iou,6),'bezier_boundary_p95_px':round(q95,3)})
        if iou>=min_iou and q95<=max_boundary_error_px:
            details['trace_mode_used']='adaptive-bezier'
            baseline=d
        else:
            details['curve_fallback_reason']='Bezier failed mask geometry tolerance, polygon retained'
    return baseline,bbox,len(polys),details
