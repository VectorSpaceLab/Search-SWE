"""Draft-interface controls; run only in a disposable, single-GPU container."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest

import psutil

IN_CONTAINER = Path('/task/runtime').is_dir() and Path('/opt/conda/bin/python').is_file()
if IN_CONTAINER:
    sys.path.insert(0, '/task/runtime')
    from evaluate import Resources, Worker, evaluate, snapshot
    from isolation import UID, cleanup


@unittest.skipUnless(IN_CONTAINER, 'disposable single-GPU container required')
class RuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = Path('/control-inputs')
        Path('/task/models').mkdir(parents=True, exist_ok=True)
        for root in [cls.fixture, Path('/task/public/valid')]:
            for dataset in ['swissprot', 'proteinkg25']:
                base = root / dataset
                base.mkdir(parents=True, exist_ok=True)
                pairs = {'p2t': {}, 't2p': {}}
                for side, prefix in [('protein', 'p'), ('text', 't')]:
                    rows = [{'id': prefix + str(i), 'value': 'item ' + str(i)} for i in range(10000)]
                    if side == 'text':
                        rows.reverse()
                    (base / (side + '.jsonl')).write_text(''.join(json.dumps(r) + '\n' for r in rows))
                for i in range(10 if root == Path('/task/public/valid') else 10000):
                    pairs['p2t']['p' + str(i)] = 't' + str(i)
                    pairs['t2p']['t' + str(i)] = 'p' + str(i)
                (base / 'pairs.json').write_text(json.dumps(pairs))

    def setUp(self):
        cleanup()
        self.sub = Path('/app/submission')
        self.sub.mkdir(exist_ok=True)
        self.sub.chmod(0o755)
        self.out = Path(tempfile.mkdtemp(dir='/app', prefix='control-output-'))
        self.group = {'key': 'control', 'candidate_file': self.fixture / 'swissprot/text.jsonl'}

    def implementation(self, extra_init='', extra_encode=''):
        path = self.sub / 'encoder.py'
        if path.exists():
            path.chmod(0o644)
        path.write_text(
            'import hashlib, json, os, subprocess, time\nfrom pathlib import Path\nimport numpy as np\nimport torch\n'
            'class Encoder:\n'
            ' def __init__(self, **kw):\n'
            '  assert os.getuid() == 10001\n'
            '  self.work = Path(kw["work_dir"])\n'
            '  self.candidate = (self.work / "candidates.jsonl").exists()\n'
            '  self.calls = 0\n' + extra_init + '\n'
            ' def encode(self, values, modality):\n'
            '  self.calls += 1\n' + extra_encode + '\n'
            '  return np.array([np.unpackbits(np.frombuffer(hashlib.sha256(v.encode()).digest()[:8],dtype=np.uint8)).astype(np.float32)*2-1 for v in values])\n')
        path.chmod(0o444)

    def worker(self, phase):
        worker = Worker(self.group, self.out, Resources(), phase)
        try:
            reply = worker.call({'phase': phase, 'modality': 'text'}, time.monotonic() + 30)
            self.assertIs(reply.get('ready'), True)
        except Exception:
            print((self.out / (self.group['key'] + '-' + phase + '-stderr.log')).read_text(), file=sys.stderr)
            worker.close()
            raise
        return worker, reply

    def test_candidate_state_does_not_reach_query_process(self):
        self.implementation(
            '  if self.candidate:\n'
            '   rows = [json.loads(x) for x in (self.work / "candidates.jsonl").read_text().splitlines()]\n'
            '   assert all(set(row) == {"value"} for row in rows)\n'
            '   (self.work / "state").write_text("secret")\n'
            '   Path("/dev/shm/candidate-marker").write_text("secret")\n'
            '   subprocess.Popen(["/usr/bin/sleep","300"])\n'
            '  else:\n'
            '   assert not Path("/dev/shm/candidate-marker").exists()\n'
            '   assert {p.name for p in self.work.iterdir()} <= {".nv"}\n'
            '   assert not (self.work / "state").exists()\n')
        worker, reply = self.worker('candidates')
        self.assertEqual(len(reply['vectors']), 10000)
        old = worker.work
        worker.close()
        self.assertFalse(old.exists())
        self.assertFalse(Path('/dev/shm/candidate-marker').exists())
        live = [p.pid for p in psutil.process_iter(['uids', 'status'])
                if p.info['uids'].real == UID and p.info['status'] != psutil.STATUS_ZOMBIE]
        self.assertEqual(live, [])
        worker, reply = self.worker('queries')
        try:
            self.assertNotEqual(worker.work, old)
            result = worker.call({'query': 'item 9'}, time.monotonic() + 3)
            self.assertEqual(len(result['vector']), 64)
        finally:
            worker.close()

    def test_full_four_group_oracle_protocol(self):
        self.implementation()
        report = evaluate(self.fixture, self.out, full_queries=True)
        self.assertEqual(report['Q'], 1.)
        self.assertEqual(report['reward'], 1.)
        self.assertEqual([g['valid_queries'] for g in report['groups']], [10000] * 4)
        self.assertEqual([d['mutual_top1_correct'] for d in report['datasets']], [10000] * 2)
        if Path('/results').is_dir():
            (Path('/results') / 'synthetic-oracle.json').write_text(json.dumps(report, indent=2) + '\n')

    def test_public_twenty_pairs_and_full_candidate_pools(self):
        self.implementation()
        report = evaluate('/task/public/valid', self.out)
        self.assertEqual(report['Q'], 1.)
        self.assertEqual([g['valid_queries'] for g in report['groups']], [10] * 4)

    def test_wrong_shape_nonfinite_and_nonnumeric_worker_results(self):
        self.implementation(extra_encode=
            '  if values == ["badshape"]: return np.zeros((1,65))\n'
            '  if values == ["nan"]: return np.full((1,64),np.nan)\n'
            '  if values == ["string"]: return np.full((1,64),"1")\n'
            '  if values == ["bool"]: return torch.zeros((1,64),dtype=torch.bool)\n'
            '  if values == ["complex"]: return torch.zeros((1,64),dtype=torch.complex64)')
        worker, _ = self.worker('queries')
        try:
            for value in ['badshape', 'nan', 'string', 'bool', 'complex']:
                result = worker.call({'query': value}, time.monotonic() + 3)
                self.assertIn('error', result)
            result = worker.call({'query': 'item 0'}, time.monotonic() + 3)
            self.assertEqual(len(result['vector']), 64)
        finally:
            worker.close()

    def test_invalid_vectors_remain_in_quality_and_latency_denominators(self):
        self.implementation(extra_encode='  if not self.candidate and self.calls > 3: return np.zeros((1,65))')
        report = evaluate('/task/public/valid', self.out)
        self.assertEqual(report['Q'], 0.)
        self.assertEqual([g['valid_queries'] for g in report['groups']], [0] * 4)
        self.assertTrue(all(g['p95'] == 3. for g in report['groups']))
        self.assertFalse(report['all_latency_gates'])

    def test_disjoint_directional_success_does_not_make_a_mutual_pair(self):
        self.implementation(extra_encode=
            '  if not self.candidate:\n'
            '   parity = 1 if modality == "protein" else 0\n'
            '   values = ["item " + str((int(v.split()[1]) + (int(v.split()[1]) % 2 == parity)) % 10000) for v in values]')
        report = evaluate('/task/public/valid', self.out)
        self.assertEqual(report['mean_accuracy_at_1'], .5)
        self.assertEqual(report['Q'], 0.)
        self.assertEqual(report['reward'], 0.)
        self.assertEqual([d['mutual_top1_correct'] for d in report['datasets']], [0, 0])

    def test_timeout_cleanup_removes_descendants(self):
        self.implementation(extra_encode='  subprocess.Popen(["/usr/bin/sleep","300"])\n  time.sleep(5)')
        worker, _ = self.worker('queries')
        work = worker.work
        try:
            with self.assertRaises(TimeoutError):
                worker.call({'query': 'item 0'}, time.monotonic() + .1)
        finally:
            worker.close()
        self.assertFalse(work.exists())
        live = [p.pid for p in psutil.process_iter(['uids', 'status'])
                if p.info['uids'].real == UID and p.info['status'] != psutil.STATUS_ZOMBIE]
        self.assertEqual(live, [])

    def test_whole_submission_byte_limit(self):
        self.implementation()
        path = self.sub / 'oversized'
        try:
            with path.open('wb') as handle:
                handle.truncate(262145)
            with self.assertRaisesRegex(ValueError, '256 KiB'):
                snapshot()
        finally:
            path.unlink()

    def tearDown(self):
        cleanup()
        shutil.rmtree(self.out, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
