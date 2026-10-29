#!/usr/bin/env python3
"""Sanity-check skill packaging, frontmatter, reference links, and Python compilation."""
from pathlib import Path
import re
import sys
import py_compile
import yaml

root=Path(__file__).resolve().parents[1]
text=(root/'SKILL.md').read_text('utf8')
match=re.match(r'^---\n(.*?)\n---\n',text,re.S)
assert match,'SKILL.md YAML frontmatter missing'
f=yaml.safe_load(match.group(1))
assert re.fullmatch(r'[a-z][a-z0-9-]{0,63}',f['name'])
assert f.get('description')
for r in re.findall(r'`(references/[^`]+\.md)`',text):
    assert (root/r).is_file(),f'Missing link: {r}'
for p in (root/'scripts').glob('*.py'):
    py_compile.compile(str(p),doraise=True)
assert (root/'assets'/'manifest.template.json').is_file()
print(f'PASS: {f["name"]}; {len(list((root/"scripts").glob("*.py")))} scripts; references and YAML valid.')
