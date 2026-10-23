#!/usr/bin/env python3
"""Create the exact leakage-filtered training file from verified upstream bytes."""
import argparse
import hashlib
import json
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--verify-only',action='store_true');args=p.parse_args()
root=Path(__file__).resolve().parent
spec=json.loads((root/'prepared-inputs.json').read_text())
manifest=json.loads((root/'assets.json').read_text())
source=root/spec['train_source']
entry=next(e for e in manifest['files'] if e['path']==spec['train_source'])
if source.stat().st_size!=entry['size_bytes'] or hashlib.file_digest(source.open('rb'),'sha256').hexdigest()!=entry['sha256']:
    raise SystemExit('Restore and verify pinned upstream training data first')
output=root/spec['path']
if not args.verify_only:
    excluded=set(spec['excluded_topic_ids'])
    rows=[json.loads(l) for l in source.read_text().splitlines() if l.strip()]
    rows=[r for r in rows if r['id'] not in excluded]
    if len(rows)!=spec['training_records']:raise SystemExit('Training record count mismatch')
    output.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
if output.stat().st_size!=spec['size_bytes'] or hashlib.file_digest(output.open('rb'),'sha256').hexdigest()!=spec['sha256']:
    raise SystemExit('Prepared training bytes do not match the audited manifest')
output.chmod(0o644)
print('Verified',spec['training_records'],'training records;',spec['sha256'])
