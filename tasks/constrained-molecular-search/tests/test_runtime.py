"""Explicit disposable CPU protocol tests; real GPU/resource checks are separate."""
import os
from pathlib import Path
import shutil
import sys
import unittest

import numpy as np

ENABLED = os.environ.get("MOLECULAR_RUNTIME_TEST") == "1"
if ENABLED:
    sys.path.insert(0, "/task/runtime")
    import evaluate
    from transfer import pack, restore


@unittest.skipUnless(ENABLED, "explicit disposable container protocol test")
class RuntimeTests(unittest.TestCase):
    def setUp(self):
        if not Path("/.dockerenv").is_file():
            raise RuntimeError("Runtime fixture must run in a disposable Docker container")
        self.private = Path("/tests/toy")
        self.private.mkdir(exist_ok=True)
        self.private.chmod(0o700)
        Path("/task/library").mkdir(parents=True, exist_ok=True)
        Path("/task/library/library.json").write_text('{"n_products":10001,"fixed_public_bytes":0}')
        queries = [{"query_id": target, "target": target, "constraints": {}, "k":10000}
                   for target in ("DRD2", "ESR1", "F10", "MET", "PARP1")]
        import json
        (self.private / "queries.jsonl").write_text("".join(json.dumps(q)+"\n" for q in queries))
        np.savez(self.private / "truth.npz", **{q["query_id"]:np.arange(10000) for q in queries})
        np.save(self.private / "properties.npy", np.ones((10001,6),dtype=np.float32))
        class CPUFixtureResources:
            def __init__(self, fixed): pass
            def check(self, force=False): pass
            def report(self): return {"fixture":"CPU protocol only; hardware/resource enforcement not exercised"}
        self.resources = evaluate.Resources
        evaluate.Resources = CPUFixtureResources
        evaluate.PREPARE_SECONDS = 30

    def tearDown(self):
        evaluate.Resources = self.resources
        evaluate.PREPARE_SECONDS = 3600
        evaluate.cleanup()

    def run_submission(self, body, name, prepare_body="    pass\n"):
        source = Path("/app/submission")
        if source.exists(): shutil.rmtree(source)
        source.mkdir()
        (source / "retriever.py").write_text(
            "def prepare(library_dir,model_dir,index_dir):\n" + prepare_body +
            "class Searcher:\n    def __init__(self,*args): pass\n"
            "    def search(self,query):\n" + body)
        pack(source, "/var/tmp/fixture.tar")
        shutil.rmtree(source)
        restore("/var/tmp/fixture.tar", source)
        report = evaluate.evaluate(self.private, Path("/logs/verifier") / name)
        import json
        (Path("/logs/verifier") / name / "report.json").write_text(json.dumps(report,indent=2)+'\n')
        return report

    def test_valid_handoff_and_full_output(self):
        report = self.run_submission("        return list(range(10000))\n", "valid")
        self.assertTrue(report["valid"])
        self.assertEqual(report["reward"], 1.0)
        self.assertTrue(all(q["status"] == "ok" and q["output_count"] == 10000 for q in report["queries"]))

    def test_native_and_subprocess_logs_do_not_corrupt_protocol(self):
        report = self.run_submission("        return list(range(10000))\n", "child-logging",
            "    import os,subprocess,sys\n    os.write(1,b'native log\\n')\n"
            "    subprocess.run([sys.executable,'-c',\"print('child log')\"],check=True)\n")
        self.assertEqual(report["Q"], 1.0)

    def test_reference_rebuilt_from_full_scores(self):
        (self.private / "truth.npz").unlink()
        np.save(self.private / "scores.npy", np.repeat(np.arange(10001,dtype=np.float64)[:,None],5,axis=1))
        report = self.run_submission("        return list(range(10000))\n", "rebuilt-gold")
        self.assertEqual(report["Q"], 1.0)

    def test_partial_recall_is_absolute_score(self):
        report = self.run_submission("        return list(range(2000))\n", "partial-recall")
        self.assertEqual(report["Q"], .2)
        self.assertEqual(report["reward"], .2)

    def test_scaled_request_budget_sets_reference_and_recall(self):
        import json
        (self.private / "truth.npz").unlink()
        queries = [dict(query_id=t, target=t, constraints={}, k=7)
                   for t in ("DRD2", "ESR1", "F10", "MET", "PARP1")]
        (self.private / "queries.jsonl").write_text("".join(json.dumps(q)+"\n" for q in queries))
        np.save(self.private / "scores.npy", np.repeat(np.arange(10001,dtype=np.float64)[:,None],5,axis=1))
        report = self.run_submission("        return list(range(query['k']))\n", "scaled-recall")
        self.assertEqual(report["Q"], 1.0)
        self.assertTrue(all(len(q["recalls"]) == 1 and q["output_count"] == 7 for q in report["queries"]))

    def test_excess_cardinality_zero_each_query(self):
        report = self.run_submission("        return list(range(10001))\n", "excess-cardinality")
        self.assertEqual(report["reward"], 0)
        self.assertTrue(all(q["status"] == "invalid" for q in report["queries"]))

    def test_duplicate_ids_zero_each_query(self):
        report = self.run_submission("        return [1,1]\n", "duplicate")
        self.assertEqual(report["reward"], 0)
        self.assertTrue(all(q["status"] == "invalid" for q in report["queries"]))

    def test_timeout_and_descendant_cleanup(self):
        report = self.run_submission("        import time,subprocess,sys\n        subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\n        time.sleep(3)\n        return []\n", "timeout")
        self.assertEqual(report["reward"], 0)
        self.assertTrue(all(q["status"] == "timeout" for q in report["queries"]))
        import psutil
        self.assertFalse(any(p.uids().real == 10001 and p.status() != psutil.STATUS_ZOMBIE for p in psutil.process_iter()))

    def test_hidden_file_access_is_denied(self):
        report = self.run_submission("        open('/tests/toy/truth.npz','rb').read()\n        return list(range(10000))\n", "hidden")
        self.assertEqual(report["reward"], 0)
        self.assertTrue(all(q["status"] == "invalid" for q in report["queries"]))

    def test_real_storage_gate_counts_sparse_logical_bytes(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        resource = self.resources.__new__(self.resources)
        resource.fixed_bytes, resource.peak_storage, resource.peak_gpu = 4096, 0, 0
        resource.last_disk, resource.gpu = 0.0, None
        path = Path('/app/oversized-sparse')
        try:
            with path.open('wb') as output:
                output.truncate(64 << 30)
            with patch.object(evaluate.pynvml,'nvmlDeviceGetMemoryInfo',return_value=SimpleNamespace(used=0)):
                with self.assertRaises(evaluate.ResourceViolation):
                    resource.check(force=True)
        finally:
            path.unlink(missing_ok=True)

    def test_open_unlinked_child_file_is_counted_even_when_nondumpable(self):
        import subprocess
        from types import SimpleNamespace
        from unittest.mock import patch
        root = Path('/app/fd-gate')
        root.mkdir(exist_ok=True)
        root.chmod(0o777)
        resource = self.resources.__new__(self.resources)
        resource.fixed_bytes, resource.peak_storage, resource.peak_gpu = 4096, 0, 0
        resource.last_disk, resource.gpu = 0.0, None
        for dumpable in (0, 1):
            code = ("import ctypes,os,time;os.setgid(10001);os.setuid(10001);"
                    f"ctypes.CDLL(None).prctl(4,{dumpable},0,0,0);"
                    "f=open('/app/fd-gate/deleted','wb');f.truncate(64<<30);"
                    "os.unlink('/app/fd-gate/deleted');print('ready',flush=True);time.sleep(60)")
            child = subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(),'ready')
                if dumpable:
                    self.assertGreaterEqual(evaluate.writable_bytes(),64 << 30)
                with patch.object(evaluate.pynvml,'nvmlDeviceGetMemoryInfo',return_value=SimpleNamespace(used=0)):
                    with self.assertRaises(evaluate.ResourceViolation):
                        resource.check(force=True)
                credentials = next(line.split()[1:] for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('Uid:'))
                groups = next(line.split()[1:] for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('Gid:'))
                self.assertEqual(credentials,['0','0','0','0'])
                self.assertEqual(groups,['0','0','0','0'])
            finally:
                child.kill()
                child.wait()
                child.stdout.close()

    def test_normal_process_pool_exit_remains_valid_with_storage_accounting(self):
        class CPUAccountingResources:
            def __init__(self, fixed): pass
            def check(self, force=False): evaluate.writable_bytes()
            def report(self): return {"fixture": "real storage accounting; CPU protocol"}
        evaluate.Resources = CPUAccountingResources
        helper = (
            "import concurrent.futures,multiprocessing\n"
            "from library import Library\n"
            "from baseline_fragments import normalize_chunk\n"
            "if __name__ == '__main__':\n"
            " for _ in range(3):\n"
            "  with concurrent.futures.ProcessPoolExecutor(max_workers=16,"
            "mp_context=multiprocessing.get_context('fork')) as pool:\n"
            "   assert len(list(pool.map(normalize_chunk,[['CC[U]']*128]*32))) == 32\n"
        )
        preparation = (
            "    import os,subprocess,sys\n"
            "    from pathlib import Path\n"
            "    helper=Path(index_dir)/'normalization_pool.py'\n"
            f"    helper.write_text({helper!r})\n"
            "    subprocess.run([sys.executable,str(helper)],check=True,"
            "env={**os.environ,'PYTHONPATH':'/task/runtime'})\n"
        )
        report = self.run_submission("        return list(range(10000))\n",
                                     "process-pool-exit", preparation)
        self.assertEqual(report["Q"], 1.0)
        self.assertTrue(all(query["status"] == "ok" for query in report["queries"]))


if __name__ == "__main__":
    unittest.main()
