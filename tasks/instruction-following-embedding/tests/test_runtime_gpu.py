"""Actual fixed-serving worker, isolation, deadlines and storage on one GPU."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

sys.path.insert(0, '/task/runtime')


@unittest.skipUnless(os.environ.get('SEARCH_SWE_GPU_TEST') == '1',
                     'Disposable GPU verifier only')
class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from evaluate import freeze_submission
        sub = Path('/app/submission')
        sub.mkdir(exist_ok=True)
        (sub / 'submission.json').write_text(json.dumps({
            'query_checkpoint':'base', 'document_checkpoint':'base'}))
        freeze_submission()
        Path('/logs/verifier').mkdir(parents=True, exist_ok=True)

    def start(self, role='query'):
        from evaluate import Worker, Resources
        worker = Worker(role, Path('/logs/verifier'), Resources())
        self.assertTrue(worker.receive(time.monotonic()+60)['ready'])
        return worker

    def test_valid_uid_determinism_and_long_input(self):
        import numpy as np
        import psutil
        from isolation import UID
        worker = self.start()
        try:
            self.assertEqual(psutil.Process(worker.p.pid).uids().real, UID)
            message = {'query':'energy', 'instruction':'include renewable sources'}
            first = np.asarray(worker.call(message, time.monotonic()+5))
            second = np.asarray(worker.call(message, time.monotonic()+5))
            np.testing.assert_array_equal(first, second)
            self.assertAlmostEqual(float(np.linalg.norm(first)), 1., places=5)
            long = worker.call({'query':'energy', 'instruction':'exclude coal '*2000},
                               time.monotonic()+5)
            self.assertEqual(len(long), 1024)  # The real tokenizer must truncate to512.
        finally:
            worker.close()

    def test_actual_worker_matches_fixed_mean_pooling(self):
        import numpy as np
        import torch
        from transformers import AutoTokenizer
        from models import BASE, load
        worker = self.start()
        try:
            actual = np.asarray(worker.call({'query':'energy', 'instruction':'include wind'},
                                             time.monotonic()+5))
        finally:
            worker.close()
        model = load(Path('/app/submission'), 'base', 'cuda')
        tokenizer = AutoTokenizer.from_pretrained(BASE, local_files_only=True)
        with torch.inference_mode():
            batch = tokenizer(['query: energy\nInstruction: include wind'],
                              padding=True, truncation=True, max_length=512,
                              return_tensors='pt').to('cuda')
            hidden = model(**batch).last_hidden_state.float()
            mask = batch['attention_mask'].unsqueeze(-1).float()
            expected = torch.nn.functional.normalize(
                (hidden*mask).sum(1)/mask.sum(1), dim=-1)[0].cpu().numpy()
        np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-7)
        del model
        torch.cuda.empty_cache()

    def test_deadline_and_uid_cleanup(self):
        import psutil
        from isolation import UID
        worker = self.start()
        child = subprocess.Popen(['/usr/bin/sleep','120'], user=UID)
        try:
            with self.assertRaises(TimeoutError):
                worker.call({'query':'q','instruction':'i'}, time.monotonic()-1)
        finally:
            worker.close()
            child.wait(timeout=10)
        self.assertFalse([p for p in psutil.process_iter(['uids','status'])
                          if p.info['uids'].real == UID and
                          p.info['status'] != psutil.STATUS_ZOMBIE])

    def test_sparse_total_storage_limit(self):
        from evaluate import Resources, ResourceViolation
        resources = Resources()
        paths = [Path('/app/sparse-a'), Path('/app/sparse-b')]
        try:
            for path in paths:
                with path.open('wb') as file:
                    file.truncate(16 << 30)
            with self.assertRaises(ResourceViolation):
                resources.check()
        finally:
            for path in paths:
                path.unlink(missing_ok=True)

    def test_document_batch_float_precision(self):
        import numpy as np
        rows = [json.loads(line) for line in Path('/task/corpus/news21.jsonl').read_text().splitlines()]
        texts = [(row['title']+' '+row['text']).strip() for row in rows[-32:]]
        worker = self.start('document')
        try:
            batch = np.asarray(worker.call({'texts':texts}, time.monotonic()+20))
            single = np.asarray(worker.call({'texts':[texts[-1]]}, time.monotonic()+20))[0]
            cosine = float((batch[-1]/np.linalg.norm(batch[-1])) @
                           (single/np.linalg.norm(single)))
            self.assertGreaterEqual(cosine, .999)
        finally:
            worker.close()


if __name__ == '__main__':
    unittest.main()
