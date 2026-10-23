"""Public simple baselines. Parameters are frozen using development queries only."""
import argparse
import json
from pathlib import Path
import re
import sqlite3
import sys
import faiss
import numpy as np
import pyarrow.parquet as pq

p = argparse.ArgumentParser()
p.add_argument('--data-dir', type=Path, required=True)
p.add_argument('--index-dir', type=Path, required=True)
p.add_argument('--mode', choices=['build', 'load'], required=True)
p.add_argument('--method', choices=['vector', 'direct', 'hybrid'], default='vector')
p.add_argument('--budget', type=int)
p.add_argument('--lexical-weight', type=float, default=.5)
a = p.parse_args()
config = json.loads((a.data_dir/'config.json').read_text())
if a.budget is None:
    a.budget = config['score_budget']
n, d = config['documents'], config['cheap_dimension']
vectors = np.memmap(a.data_dir/'cheap.f32', dtype='<f4', mode='r', shape=(n, d))
index = faiss.IndexFlatIP(d)
index.add(vectors)
del vectors
a.index_dir.mkdir(parents=True, exist_ok=True)
db = None
if a.method == 'hybrid':
    db = sqlite3.connect(a.index_dir/'lexical.sqlite')
    if a.mode == 'build':
        db.execute('DROP TABLE IF EXISTS docs')
        db.execute('CREATE VIRTUAL TABLE docs USING fts5(title, text, content="", tokenize="porter unicode61")')
        offset = 0
        for batch in pq.ParquetFile(a.data_dir/'corpus.parquet').iter_batches(batch_size=8192):
            rows = [(offset+i+1, item['title'], item['text']) for i, item in enumerate(batch.to_pylist())]
            db.executemany('INSERT INTO docs(rowid,title,text) VALUES (?,?,?)', rows)
            offset += len(rows)
        db.commit()


def emit(message):
    print(json.dumps(message, separators=(',', ':')), flush=True)


stop = set('a an and are as at be by for from how in is it of on or that the to was were what when where which who why with'.split())
emit({'op': 'ready'})
for line in sys.stdin:
    query = json.loads(line)
    if query.get('op') != 'query':
        raise ValueError('Expected a query')
    count = max(1000, a.budget) if a.method == 'hybrid' else max(10, a.budget)
    _, candidates = index.search(np.array([query['vector']], dtype='f4'), count)
    candidates = candidates[0].tolist()
    if a.method == 'hybrid':
        terms = [x for x in re.findall(r'\w+', query['text'].lower()) if x not in stop]
        expression = ' OR '.join('"'+x.replace('"','""')+'"' for x in terms)
        # A fixed work cap makes fallback independent of transient machine load.
        # Training-only timing calibration leaves room within the 2 s query gate.
        lexical_steps = [0]
        def progress():
            lexical_steps[0] += 1000
            return lexical_steps[0] >= 10000000
        db.set_progress_handler(progress, 1000)
        try:
            lexical = [r[0]-1 for r in db.execute('SELECT rowid FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT 1000', (expression,))] if expression else []
        except sqlite3.OperationalError as exc:
            if 'interrupted' not in str(exc): raise
            lexical = []
            print('lexical work limit: using dense candidates', file=sys.stderr, flush=True)
        finally:
            db.set_progress_handler(None, 0)
        fused = {}
        for weight, ranking in [(1-a.lexical_weight, candidates), (a.lexical_weight, lexical)]:
            for rank, row in enumerate(ranking): fused[row] = fused.get(row, 0) + weight/(61+rank)
        candidates = sorted(fused, key=lambda row: (-fused[row], row))[:a.budget]
    elif a.method == 'direct':
        emit({'op': 'result', 'token': query['token'], 'doc_ids': [f'doc{x}' for x in candidates[:10]]})
        continue
    else:
        candidates = candidates[:a.budget]
    ids = [f'doc{x}' for x in candidates]
    emit({'op': 'score', 'token': query['token'], 'doc_ids': ids})
    scores = json.loads(sys.stdin.readline())
    ranked = sorted(zip(scores['distances'], ids), key=lambda item: (item[0], int(item[1][3:])))
    emit({'op': 'result', 'token': query['token'], 'doc_ids': [item[1] for item in ranked[:10]]})
