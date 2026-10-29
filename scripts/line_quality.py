#!/usr/bin/env python3
"""Validate source/SVG-bound visual line review; this does not detect defects automatically."""
import hashlib
import json
import math
from lxml import etree
from editable_svg import SHAPES, visible


def inspect_line_quality(svg, elements, source_sha256, review_path, required):
    digest=hashlib.sha256(svg).hexdigest()
    objects=sorted(oid for oid,group in elements.items() if any(
        etree.QName(n).localname in SHAPES and visible(n) for n in group.iter()))
    report={'required':required,'svg_sha256':digest,'source_sha256':source_sha256,
            'required_object_ids':objects,'status':'not_reviewed','failures':[],
            'interpretation':'Checks review coverage and freshness; visual inspection establishes line quality.'}
    if not required:
        report['quality_gates_passed']=True
        return report
    failures=report['failures']
    if not review_path.is_file():
        failures.append({'reason':'line_quality_review_missing'})
    else:
        try:
            review=json.loads(review_path.read_text('utf-8'))
            if not isinstance(review,dict):raise ValueError('Review must be an object')
            if review.get('svg_sha256')!=digest or review.get('source_sha256')!=source_sha256:
                failures.append({'reason':'line_quality_review_stale'})
            scale=review.get('reviewed_scale')
            if type(scale) not in (int,float) or not math.isfinite(scale) or scale<4:
                failures.append({'reason':'line_review_requires_at_least_4x'})
            if not isinstance(review.get('reviewer'),str) or not review['reviewer'].strip():
                failures.append({'reason':'line_review_reviewer_missing'})
            rows=review.get('objects',[])
            if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):
                raise ValueError('objects must be review records')
            ids=[row.get('object_id') for row in rows]
            if any(not isinstance(oid,str) for oid in ids) or len(ids)!=len(set(ids)):
                raise ValueError('Review object IDs must be unique strings')
            report.update(reviewer=review.get('reviewer'),reviewed_scale=scale,objects=rows)
            indexed={row['object_id']:row for row in rows}
            for oid in objects:
                row=indexed.get(oid,{})
                failed=[key for key in ('no_unintended_gaps','no_jagged_edges','source_matched') if row.get(key) is not True]
                if failed:failures.append({'object_id':oid,'reason':'line_visual_review_incomplete','checks':failed})
        except (ValueError,TypeError,UnicodeError):
            failures.append({'reason':'line_quality_review_invalid'})
    report['quality_gates_passed']=not failures
    report['status']='reviewed_pass' if not failures else 'blocked'
    return report
