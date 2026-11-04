import argparse, json, pickle, re, sqlite3, sys
from pathlib import Path
import faiss, numpy as np, pyarrow.parquet as pq, Stemmer
STOP = set('a an and are as at be by for from how in is it of on or that the to was were what when where which who why with'.split())

def build(data, index):
    index.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(index / 'lexical.sqlite')
    db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(title,text,content="",tokenize="porter unicode61")')
    if not db.execute('SELECT count(*) FROM docs').fetchone()[0]:
        offset = 0
        for batch in pq.ParquetFile(data / 'corpus.parquet').iter_batches(batch_size=8192):
            db.executemany('INSERT INTO docs(rowid,title,text) VALUES(?,?,?)', [(offset + i + 1, r['title'], r['text']) for i, r in enumerate(batch.to_pylist())])
            offset += len(batch)
        db.commit()
    db.close()

class Engine:

    def __init__(self, data, index):
        faiss.omp_set_num_threads(1)
        self.v = np.memmap(data / 'cheap.f32', dtype='<f4', mode='r', shape=(250000, 384))
        self.dense = faiss.IndexFlatIP(384)
        self.dense.add(self.v)
        self.db = sqlite3.connect(index / 'lexical.sqlite')
        self.db.execute('PRAGMA temp_store=MEMORY')
        self.stemmer = Stemmer.Stemmer('english')
        cache = index / 'tokens.pkl'
        if cache.exists():
            self.tokens = pickle.loads(cache.read_bytes())
        else:
            table = pq.read_table(data / 'corpus.parquet', columns=['title', 'text']).to_pylist()
            self.tokens = []
            for row in table:
                a = self.words(row['title'])
                b = self.words(row['text'])
                self.tokens.append((set(a), set(b), ' '.join(a), ' '.join(b), len(b)))
            cache.write_bytes(pickle.dumps(self.tokens, protocol=5))

    def words(self, text):
        return self.stemmer.stemWords([x for x in re.findall('\\w+', text.lower()) if x not in STOP])

    def lexical(self, expression, title_weight, limit):
        if not expression:
            return ([], [])
        steps = [0]

        def cap():
            steps[0] += 1000
            return steps[0] >= 10000000
        self.db.set_progress_handler(cap, 1000)
        try:
            rows = self.db.execute('SELECT rowid,rank FROM docs WHERE docs MATCH ? AND rank MATCH ? ORDER BY rank LIMIT ?', (expression, f'bm25({title_weight},1.0)', limit)).fetchall()
        except sqlite3.OperationalError as e:
            if 'interrupted' not in str(e):
                raise
            rows = []
        finally:
            self.db.set_progress_handler(None, 0)
        return ([r[0] - 1 for r in rows], [-r[1] for r in rows])

    def retrieve(self, text, vector):
        dense = self.dense.search(np.asarray(vector, dtype='f4').reshape(1, -1), 1000)[1][0]
        terms = list(dict.fromkeys((x for x in re.findall('\\w+', text.lower()) if x not in STOP)))
        expr = ' OR '.join(('"' + t.replace('"', '""') + '"' for t in terms))
        lex, ls = self.lexical(expr, 1, 1000)
        title, ts = self.lexical(expr, 3, 500)
        fused = {}
        for ids in [dense, lex, title]:
            for r, row in enumerate(ids):
                fused[int(row)] = fused.get(int(row), 0) + 1 / (61 + r)
        rows = np.array(sorted(set(dense[:200]) | set(lex[:200]) | set(title[:200]) | set(sorted(fused, key=lambda row: -fused[row])[:200])), dtype='i8')
        return {'vector': np.asarray(vector, dtype='f4'), 'words': self.words(text), 'dense': dense, 'lex': lex, 'ls': ls, 'title': title, 'ts': ts, 'rows': rows}

    def features(self, result, rows):
        rows = np.asarray(rows, dtype='i8')
        q = result['words']
        terms = set(q)
        pairs = [a + ' ' + b for a, b in zip(q, q[1:])]
        dr = {int(x): i + 1 for i, x in enumerate(result['dense'])}
        lr = {x: i + 1 for i, x in enumerate(result['lex'])}
        tr = {x: i + 1 for i, x in enumerate(result['title'])}
        ls = dict(zip(result['lex'], result['ls']))
        ts = dict(zip(result['title'], result['ts']))
        lm = max(result['ls'][0], 1e-09) if result['ls'] else 1
        tm = max(result['ts'][0], 1e-09) if result['ts'] else 1
        cosine = np.einsum('ij,j->i', self.v[rows], result['vector'], optimize=False)
        features = []
        for i, row in enumerate(rows):
            title, body, tj, bj, length = self.tokens[row]
            features.append([cosine[i], ls.get(int(row), 0) / lm, ts.get(int(row), 0) / tm, np.log1p(dr.get(int(row), 2000)), np.log1p(lr.get(int(row), 2000)), np.log1p(tr.get(int(row), 2000)), len(title & terms) / max(len(terms), 1), len(body & terms) / max(len(terms), 1), sum((x in tj for x in pairs)) / max(len(pairs), 1), sum((x in bj for x in pairs)) / max(len(pairs), 1)])
        return np.asarray(features, dtype='f4')

    def feedback(self, vector, rows, distances):
        x = self.v[rows].astype('f8')
        x -= x.mean(axis=0)
        y = np.mean(distances) - distances
        direction = x.T @ np.linalg.solve(x @ x.T + 0.01 * np.eye(len(rows)), y)
        updated = np.asarray(vector + 0.5 * direction, dtype='f4')
        expansion = self.dense.search(updated.reshape(1, -1), 200)[1][0]
        return (direction, expansion)

def predict(model, x):
    if isinstance(model, dict):
        return (x - model['mean']) / model['scale'] @ model['weights']
    p = np.clip(model.predict_proba(x)[:, 1], 1e-08, 1 - 1e-08)
    return np.log(p / (1 - p))

def emit(x):
    print(json.dumps(x, separators=(',', ':')), flush=True)

def score(token, rows):
    emit({'op': 'score', 'token': token, 'doc_ids': ['doc' + str(int(x)) for x in rows]})
    response = json.loads(sys.stdin.buffer.readline())
    if response.get('op') != 'scores' or response.get('token') != token:
        raise ValueError('Invalid scoring response')
    distances = np.asarray(response['distances'], dtype='f8')
    if distances.shape != (len(rows),):
        raise ValueError('Invalid distance count')
    return distances

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-dir', type=Path, required=True)
    ap.add_argument('--index-dir', type=Path, required=True)
    ap.add_argument('--mode', choices=['build', 'load'], required=True)
    ap.add_argument('--model-path', type=Path, default=Path(__file__).with_name('model.pkl'))
    a = ap.parse_args(argv)
    root = Path(__file__).parent
    params = {'feedback_weight': 80, 'reserve_unscored': False}
    model = pickle.loads(a.model_path.read_bytes())
    if a.mode == 'build':
        build(a.data_dir, a.index_dir)
    engine = Engine(a.data_dir, a.index_dir)
    emit({'op': 'ready'})
    for line in sys.stdin.buffer:
        query = json.loads(line)
        token = query['token']
        result = engine.retrieve(query['text'], query['vector'])
        rows = result['rows']
        prior = predict(model, engine.features(result, rows))
        order = np.lexsort((rows, -prior))
        dense = int(result['dense'][0])
        ranked = rows[order]
        first = np.r_[dense, ranked[ranked != dense][:9]].astype('i8')
        d1 = score(token, first)
        direction, expansion = engine.feedback(result['vector'], first, d1)
        rows = np.unique(np.r_[rows, expansion])
        prior = predict(model, engine.features(result, rows))
        adjusted = prior + params['feedback_weight'] * (engine.v[rows] @ direction)
        ranked = rows[np.lexsort((rows, -adjusted))]
        remaining = ranked[~np.isin(ranked, first)]
        second = remaining[:10]
        d2 = score(token, second)
        scored = np.r_[first, second]
        distances = np.r_[d1, d2]
        ordered = scored[np.lexsort((scored, distances))]
        final = np.r_[ordered[:9], remaining[10]] if params['reserve_unscored'] else ordered[:10]
        emit({'op': 'result', 'token': token, 'doc_ids': ['doc' + str(int(x)) for x in final]})
if __name__ == '__main__':
    main()
