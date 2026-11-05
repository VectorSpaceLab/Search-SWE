"""Synthetic CPU controls for protocol/isolation; not benchmark/E2E evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest

import numpy as np
import psutil
sys.path.insert(0, "/task/runtime")
from evaluate import evaluate, verify_snapshot

ROOT = Path("/app/control-private")


def jsonl(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in data))


def fixture():
    ROOT.mkdir(exist_ok=True)
    ROOT.chmod(0o700)
    for dataset, languages in (("belebele", ["ar", "zh", "en", "fr", "hi", "it", "ja", "pt", "ru", "es"]),
                               ("xquad", ["ar", "zh", "en", "hi", "ru", "es"])):
        docs, queries, labels, vectors = [], [], [], []
        for family in range(2):
            relevant = [f"d-{family}-{lang}" for lang in languages]
            for lang in languages:
                vector = np.zeros(1024, dtype=np.float16)
                vector[family] = 1
                docs.append(dict(id=f"d-{family}-{lang}", language=lang))
                queries.append(dict(id=f"q-{family}-{lang}", language=lang))
                labels.append(dict(query_id=f"q-{family}-{lang}", relevant_doc_ids=relevant))
                vectors.append(vector)
        corpus = ROOT / "corpus" / dataset
        jsonl(corpus / "documents.jsonl", docs)
        np.save(corpus / "vectors.npy", np.array(vectors))
        for split in ("development", "hidden"):
            directory = ROOT / split / dataset
            jsonl(directory / "queries.jsonl", queries)
            jsonl(directory / "qrels.jsonl", labels)
            np.save(directory / "vectors.npy", np.array(vectors))


class RuntimeControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("SEARCH_SWE_VERIFIER_SANDBOX") != "1":
            raise RuntimeError("Run controls only in a disposable task verifier container")
        fixture()

    def setUp(self):
        path = Path("/app/submission")
        if path.exists():
            shutil.rmtree(path)
        path.mkdir()

    def module(self, load="return None", transform="return vectors.copy()"):
        source = "import numpy as np\nimport os, sys, subprocess, socket\ndef load(directory):\n" + "\n".join("    " + line for line in load.splitlines())
        source += "\ndef transform(vectors, languages, state):\n" + "\n".join("    " + line for line in transform.splitlines()) + "\n"
        path = Path("/app/submission/transform.py")
        path.write_text(source)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        status = dict(valid=True, files=[dict(path="transform.py", size_bytes=path.stat().st_size, sha256=digest)])
        status_path = ROOT / "frozen-status.json"
        status_path.write_text(json.dumps(status))
        return status_path

    def run_control(self, *, sandbox=True):
        return evaluate("/app/submission", ROOT / "corpus", ROOT / "hidden", ROOT / "development",
                        ROOT / "logs" / self.id().split(".")[-1], sandbox=sandbox, require_gpu=False,
                        preparation_seconds=30, query_seconds=.5, frozen_status=ROOT / "frozen-status.json")

    def test_identity_known_good(self):
        self.module()
        result = self.run_control()
        self.assertAlmostEqual(result["Q"], 1)
        self.assertEqual(result["measurement_rounds"], 5)
        self.assertEqual(result["total_queries"], 32)
        self.assertEqual(result["valid_queries"], 32)
        round_reports = [json.loads((ROOT / 'logs' / self.id().split('.')[-1] /
                                     f'round-{number}' / 'evaluation.json').read_text())
                         for number in range(1, 6)]
        order = [row['query_id'] for row in result['queries']]
        self.assertTrue(all([row['query_id'] for row in report['queries']] == order for report in round_reports))
        for row in result["queries"]:
            languages = ["ar", "zh", "en", "fr", "hi", "it", "ja", "pt", "ru", "es"] if row["dataset"] == "belebele" else ["ar", "zh", "en", "hi", "ru", "es"]
            family = row["query_id"].split("-")[1]
            expected = sorted(f"d-{family}-{language}" for language in languages)
            self.assertEqual(row["ranked_doc_ids"][:len(languages)], expected)
            self.assertEqual(len(row["ranked_doc_ids"]), min(20, 2 * len(languages)))
            self.assertEqual(len(set(row["ranked_doc_ids"])), len(row["ranked_doc_ids"]))

    def test_rounds_use_fresh_workers_and_temporary_workspaces(self):
        self.module(load="assert not os.path.exists('round-marker')\nopen('round-marker','w').write('loaded')\nprint(os.getcwd(), file=sys.stderr)\nreturn None")
        self.assertEqual(self.run_control()['Q'], 1)
        directories = [(ROOT / 'logs' / self.id().split('.')[-1] / f'round-{number}' /
                        'worker.stderr.log').read_text().strip() for number in range(1, 6)]
        self.assertEqual(len(set(directories)), 5)
        self.assertTrue(all(not Path(directory).exists() for directory in directories))

    def test_disk_storage_limit_includes_sparse_temporary_files(self):
        self.module(load="with open('oversized-cache','wb') as handle:\n    handle.truncate(100 * 1024**3)\nreturn None")
        with self.assertRaisesRegex(RuntimeError, 'storage exceeded'):
            self.run_control()

    def retained_module(self, *, mapped=False, size=60 << 30, memfd=False):
        self.module(load=f'size={size}; mapped={mapped}; memfd={memfd}\n' + '''import ctypes
if os.getuid() == 10001:
    status = dict(line.split(':', 1) for line in open('/proc/self/status') if ':' in line)
    assert int(status['CapEff'], 16) == int(status['CapPrm'], 16) == 0
libc = ctypes.CDLL(None, use_errno=True)
libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                      ctypes.c_int, ctypes.c_int, ctypes.c_longlong]
libc.mmap.restype = ctypes.c_void_p
libc.memfd_create.argtypes = [ctypes.c_char_p, ctypes.c_uint]
state = []
for number in range(2):
    name = 'retained-cache-' + str(number)
    fd = libc.memfd_create(name.encode(), 0) if memfd else os.open(name, os.O_CREAT | os.O_RDWR, 0o600)
    assert fd >= 0, ctypes.get_errno()
    os.ftruncate(fd, size)
    if mapped:
        # libc avoids Python mmap's implicit duplicate descriptor. Only one
        # page is mapped, but the entire backing file must count toward storage.
        address = libc.mmap(None, 4096, 3, 1, fd, 0)
        assert address != ctypes.c_void_p(-1).value, ctypes.get_errno()
        ctypes.memmove(address, b'canary00', 8)
        state.append(address)
    else:
        os.write(fd, b'canary00')
        state.append(fd)
    if not memfd:
        os.unlink(name)
    if mapped:
        os.close(fd)
if mapped:
    for entry in os.listdir('/proc/self/fd'):
        try:
            assert 'retained-cache-' not in os.readlink('/proc/self/fd/' + entry)
        except FileNotFoundError:
            pass
return (mapped, state)''', transform='''import ctypes
mapped, retained = state
for value in retained:
    assert (ctypes.string_at(value, 8) if mapped else os.pread(value, 8, 0)) == b'canary00'
return vectors.copy()''')

    def test_storage_rejects_open_unlinked_files(self):
        self.retained_module()
        with self.assertRaisesRegex(RuntimeError, 'storage exceeded'):
            self.run_control()

    def test_storage_rejects_mmap_only_partial_files(self):
        self.retained_module(mapped=True)
        with self.assertRaisesRegex(RuntimeError, 'storage exceeded'):
            self.run_control()

    def test_storage_rejects_mapped_memfd_after_close(self):
        self.retained_module(mapped=True, memfd=True)
        with self.assertRaisesRegex(RuntimeError, 'storage exceeded'):
            self.run_control()

    def test_public_evaluator_rejects_retained_files(self):
        self.retained_module(mapped=True)
        with self.assertRaisesRegex(RuntimeError, 'storage exceeded'):
            self.run_control(sandbox=False)

    def test_storage_counts_files_in_a_detached_worker(self):
        self.module(load='''reader, writer = os.pipe()
if os.fork() == 0:
    os.close(reader)
    os.setsid()
    retained = []
    for number in range(2):
        name = 'detached-cache-' + str(number)
        handle = open(name, 'w+b')
        handle.truncate(60 << 30)
        os.unlink(name)
        retained.append(handle)
    os.write(writer, b'ready')
    os.close(writer)
    import time
    time.sleep(60)
    os._exit(0)
os.close(writer)
assert os.read(reader, 5) == b'ready'
os.close(reader)
return None''')
        with self.assertRaisesRegex(RuntimeError, 'storage exceeded'):
            self.run_control()

    def test_under_budget_retained_files_pass_all_rounds(self):
        for mapped in (False, True):
            with self.subTest(mapped=mapped):
                self.retained_module(mapped=mapped, size=1024**2)
                result = self.run_control()
                self.assertEqual(result['Q'], 1)
                self.assertEqual(result['measurement_rounds'], 5)

    def test_live_worker_cannot_disable_storage_inspection(self):
        self.module(load="import ctypes\nassert ctypes.CDLL(None).prctl(4, 0, 0, 0, 0) == 0\nreturn None")
        with self.assertRaisesRegex(RuntimeError, 'Cannot inspect submission'):
            self.run_control()

    def surviving_thread_module(self, *, mapped, size=60 << 30, hide=False):
        self.module(load=f'mapped={mapped}; size={size}; hide={hide}\n' + '''import ctypes, threading, time
reader, writer = os.pipe()
if os.fork() == 0:
    os.close(reader)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_longlong]
    libc.mmap.restype = ctypes.c_void_p
    libc.pthread_exit.argtypes = [ctypes.c_void_p]
    def retain():
        from pathlib import Path
        status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
        assert os.getuid() == 10001 and int(status['CapEff'], 16) == int(status['CapPrm'], 16) == 0
        for _ in range(2000):
            if Path('/proc/self/stat').read_text().rsplit(') ', 1)[1].split()[0] == 'Z':
                break
            time.sleep(.001)
        else:
            os._exit(3)
        retained = []
        for number in range(2):
            name = 'thread-cache-' + str(number)
            fd = os.open(name, os.O_CREAT | os.O_RDWR, 0o600)
            os.ftruncate(fd, size)
            if mapped:
                address = libc.mmap(None, 4096, 3, 1, fd, 0)
                assert address != ctypes.c_void_p(-1).value, ctypes.get_errno()
                ctypes.memmove(address, b'canary00', 8)
                retained.append(address)
                os.close(fd)
            else:
                os.write(fd, b'canary00')
                retained.append(fd)
            os.unlink(name)
        if hide:
            assert libc.prctl(4, 0, 0, 0, 0) == 0
        os.write(writer, b'ready')
        os.close(writer)
        while True:
            assert all((ctypes.string_at(value, 8) if mapped else os.pread(value, 8, 0)) == b'canary00' for value in retained)
            time.sleep(.01)
    # A second live thread shares the mappings/FDs; charge each inode once.
    threading.Thread(target=threading.Event().wait).start()
    threading.Thread(target=retain).start()
    libc.pthread_exit(None)
    os._exit(4)
os.close(writer)
assert os.read(reader, 5) == b'ready'
os.close(reader)
return None''')

    def test_storage_rejects_files_in_surviving_threads(self):
        for mapped in (False, True):
            with self.subTest(mapped=mapped):
                self.surviving_thread_module(mapped=mapped)
                with self.assertRaisesRegex(RuntimeError, 'storage exceeded'):
                    self.run_control()

    def test_surviving_thread_under_budget_passes_all_rounds(self):
        for mapped in (False, True):
            with self.subTest(mapped=mapped):
                self.surviving_thread_module(mapped=mapped, size=1024**2)
                result = self.run_control()
                self.assertEqual(result['Q'], 1)
                self.assertEqual(result['measurement_rounds'], 5)

    def test_surviving_thread_cannot_disable_storage_inspection(self):
        self.surviving_thread_module(mapped=True, size=1024**2, hide=True)
        with self.assertRaisesRegex(RuntimeError, 'Cannot inspect submission'):
            self.run_control()

    def test_consistency_probe_timeout_does_not_abort_all_measurements(self):
        # Two corpus batches, two batch probes, four warmups, then one query and its probe.
        self.module(load="return {'calls': 0}", transform="state['calls'] += 1\nif state['calls'] == 10:\n    import time\n    time.sleep(60)\nreturn vectors.copy()")
        report = self.run_control()
        self.assertEqual(report['measurement_rounds'], 5)
        self.assertEqual(report['total_queries'], 32)
        self.assertEqual(report['valid_queries'], 1)
        self.assertTrue(all(len(r['consistency_probe_failures']) == 1 for r in report['measurement_reports']))

    def test_nan_and_zero_document_outputs_rejected(self):
        for expression in ("return np.full_like(vectors, np.nan)", "return np.zeros_like(vectors)"):
            self.module(transform=expression)
            with self.assertRaises(ValueError):
                self.run_control()

    def test_batch_dependent_function_rejected(self):
        self.module(transform="return np.roll(vectors, 1, axis=1) if len(vectors) == 1 else vectors.copy()")
        with self.assertRaisesRegex(RuntimeError, "frozen function changed"):
            self.run_control()

    def test_labels_rewards_network_and_privilege_protected(self):
        marker = ROOT / "secret-label.txt"
        marker.write_text("private fixture label")
        reward = Path("/logs/verifier/reward.txt")
        reward.parent.mkdir(parents=True, exist_ok=True)
        reward.parent.chmod(0o700)
        reward.write_text("0\n")
        load = f'''denied = 0
try:
    open({str(marker)!r}).read()
except PermissionError:
    denied += 1
try:
    open('/logs/verifier/reward.txt','w').write('1')
except PermissionError:
    denied += 1
try:
    socket.socket(socket.AF_INET,socket.SOCK_STREAM)
except PermissionError:
    denied += 1
try:
    os.setuid(0)
except PermissionError:
    denied += 1
assert denied == 4
return None'''
        self.module(load=load)
        self.assertEqual(self.run_control()["Q"], 1)
        self.assertEqual(reward.read_text(), "0\n")

    def test_orphan_processes_cleaned(self):
        self.module(load="subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True)\nreturn None")
        self.assertEqual(self.run_control()["Q"], 1)
        for process in psutil.process_iter(["uids", "status"]):
            self.assertFalse(process.info["uids"].real == 10001 and process.info["status"] != psutil.STATUS_ZOMBIE)

    def test_preparation_timeout_stops_worker(self):
        self.module(load="import time\ntime.sleep(60)\nreturn None")
        began = time.monotonic()
        with self.assertRaises(TimeoutError):
            evaluate("/app/submission", ROOT / "corpus", ROOT / "hidden", ROOT / "development",
                     ROOT / "logs/preparation-timeout", sandbox=True, require_gpu=False,
                     preparation_seconds=.5, frozen_status=ROOT / "frozen-status.json")
        self.assertLess(time.monotonic() - began, 10)

    def test_query_timeout_preserves_denominators(self):
        self.module(transform="if vectors[0,2] > .5:\n    import time\n    time.sleep(60)\nreturn vectors.copy()")
        path = ROOT / "hidden/belebele/vectors.npy"
        vectors = np.load(path)
        vectors[0] = 0
        vectors[0, 2] = 1
        np.save(path, vectors)
        try:
            report = self.run_control()
            self.assertEqual(report["total_queries"], 32)
            self.assertLess(report["valid_queries"], 32)
            self.assertTrue(any(r["failure"] == "TimeoutError" for r in report["queries"]))
            self.assertTrue(all(r["ndcg"] == 0 for r in report["queries"] if not r["valid"]))
            for dataset in report["datasets"].values():
                for language in dataset["languages"].values():
                    self.assertEqual(language["queries"], 2)
        finally:
            fixture()

    def test_one_invalid_query_keeps_worker_and_all_denominators(self):
        self.module(transform="result = vectors.copy()\nresult[vectors[:,2] > .5] = np.nan\nreturn result")
        path = ROOT / "hidden/belebele/vectors.npy"
        vectors = np.load(path)
        vectors[0] = 0
        vectors[0, 2] = 1
        np.save(path, vectors)
        try:
            report = self.run_control()
            self.assertEqual(report["total_queries"], 32)
            self.assertEqual(report["valid_queries"], 31)
            self.assertAlmostEqual(report["Q"], .975)
            failed = [row for row in report["queries"] if not row["valid"]]
            self.assertEqual(len(failed), 1)
            self.assertEqual(failed[0]["ndcg"], 0)
        finally:
            fixture()

    def test_link_and_changed_artifact_rejected(self):
        status = self.module()
        Path("/app/submission/escape").symlink_to(ROOT / "secret-label.txt")
        with self.assertRaises(RuntimeError):
            verify_snapshot("/app/submission", status)
        Path("/app/submission/escape").unlink()
        Path("/app/submission/transform.py").write_text("changed")
        with self.assertRaises(RuntimeError):
            verify_snapshot("/app/submission", status)

    def test_restore_accepts_collected_and_rejects_changes(self):
        status = self.module()
        parent = Path("/logs/agent")
        parent.mkdir(parents=True, exist_ok=True)
        collected = parent / "collected-submission"
        if collected.exists():
            shutil.rmtree(collected)
        shutil.copytree("/app/submission", collected)
        shutil.copyfile(status, parent / "submission-freeze-status.json")
        def restore():
            subprocess.run([sys.executable, "-I", "/task/runtime/restore_submission.py"], check=True)
            return json.loads(Path("/var/tmp/submission-freeze-status.json").read_text())
        self.assertTrue(restore()["valid"])
        self.assertEqual(self.run_control()["Q"], 1)
        (collected / "transform.py").write_text("tampered")
        self.assertFalse(restore()["valid"])
        self.assertFalse(any(Path("/app/submission").iterdir()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
