"""Task-local regressions; no assets, judge credentials or root required."""
import contextlib
import errno
import io
import json
import math
import os
from pathlib import Path
import pwd
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import grader
import finalize_reward


class GraderTests(unittest.TestCase):
    def test_query_cpu_supports_numpy_and_faiss(self):
        launcher = '/usr/local/bin/search-swe-query-cpu'
        if not Path(launcher).is_file() or os.geteuid() != 0:
            self.skipTest('requires the verifier Docker CPU launcher')
        program = '''
import os, numpy as np, faiss
faiss.omp_set_num_threads(1)
x = np.eye(8, dtype='float32')
index = faiss.IndexFlatIP(8)
index.add(x)
scores, rows = index.search(x, 1)
assert np.array_equal(rows[:, 0], np.arange(8))
assert np.allclose(x @ x.T, x)
assert len(os.sched_getaffinity(0)) == 1
'''
        result = subprocess.run(grader.SUBMISSION_COMMAND + [launcher, '/opt/conda/bin/python',
                                '-c', program], cwd='/', capture_output=True, text=True,
                                timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_query_cpu_boundary_survives_threads_and_exec(self):
        launcher = '/usr/local/bin/search-swe-query-cpu'
        if not Path(launcher).is_file() or os.geteuid() != 0:
            self.skipTest('requires the verifier Docker CPU launcher')
        allowed = sorted(os.sched_getaffinity(0))
        if len(allowed) < 2:
            self.skipTest('requires multiple available CPUs to test expansion')
        child = '''
import errno, json, os, threading
mask = sorted(os.sched_getaffinity(0))
thread_masks = []
t = threading.Thread(target=lambda: thread_masks.append(sorted(os.sched_getaffinity(0))))
t.start(); t.join()
try:
    os.sched_setaffinity(0, ALLOWED)
    denied = False
except OSError as e:
    denied = e.errno == errno.EPERM
print(json.dumps(dict(mask=mask, threads=thread_masks, denied=denied)))
'''.replace('ALLOWED', repr(allowed))
        program = ("import subprocess; subprocess.run(['/opt/conda/bin/python', '-c', "
                   + repr(child) + "], check=True)")
        result = subprocess.run(grader.SUBMISSION_COMMAND + [launcher, '/opt/conda/bin/python',
                                '-c', program], cwd='/', capture_output=True, text=True,
                                timeout=10, check=True)
        data = json.loads(result.stdout)
        self.assertEqual(data['mask'], [allowed[0]])
        self.assertEqual(data['threads'], [[allowed[0]]])
        self.assertTrue(data['denied'])
        self.assertEqual(grader.validate_query_cpu_boundary()['allowed_cpus'], [allowed[0]])

    def test_deployment_preserves_only_persisted_index(self):
        if os.geteuid() != 0 or not os.path.ismount(grader.INDEX_DIR):
            self.skipTest('requires the verifier Docker runtime')
        persisted = grader.INDEX_DIR / '.deployment-test'
        ephemeral = Path('/dev/shm/dense-deployment-test')
        program = (f'from pathlib import Path; import time; '
                   f'Path({str(persisted)!r}).write_text("index"); '
                   f'Path({str(ephemeral)!r}).write_text("runtime"); time.sleep(60)')
        process = subprocess.Popen(grader.SUBMISSION_COMMAND + ['/opt/conda/bin/python', '-c', program],
                                   cwd='/', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 5
            while not ephemeral.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(ephemeral.exists())
            grader.restart_submission_for_queries()
            process.wait(timeout=3)
            self.assertEqual(persisted.read_text(), 'index')
            self.assertFalse(ephemeral.exists())
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            persisted.unlink(missing_ok=True)
            ephemeral.unlink(missing_ok=True)

    def test_index_logical_size_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (root / 'sparse-index').open('wb') as f:
                f.truncate(grader.INDEX_LIMIT_BYTES)
            self.assertEqual(grader.check_index_size(root), grader.INDEX_LIMIT_BYTES)
            with (root / 'sparse-index').open('ab') as f:
                f.write(b'x')
            with self.assertRaises(grader.VerificationError):
                grader.check_index_size(root)

    def test_deployment_removes_system_v_ipc(self):
        if os.geteuid() != 0 or not os.path.ismount(grader.INDEX_DIR):
            self.skipTest('requires the verifier Docker runtime')
        program = '''
import ctypes, json, signal
libc = ctypes.CDLL(None, use_errno=True)
libc.shmget.argtypes = [ctypes.c_int, ctypes.c_size_t, ctypes.c_int]
libc.shmat.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
libc.shmat.restype = ctypes.c_void_p
shm = libc.shmget(0, 65 * 1024 ** 2, 0o1600)
msg = libc.msgget(0, 0o1600)
sem = libc.semget(0, 1, 0o1600)
assert min(shm, msg, sem) >= 0, ctypes.get_errno()
address = libc.shmat(shm, None, 0)
assert address != ctypes.c_void_p(-1).value, ctypes.get_errno()
ctypes.memset(address, 90, 65 * 1024 ** 2)
print(json.dumps(dict(shm=shm, msg=msg, sem=sem)), flush=True)
signal.pause()
'''
        process = subprocess.Popen(grader.SUBMISSION_COMMAND + ['/opt/conda/bin/python', '-c', program],
                                   cwd='/', stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True)
        try:
            objects = json.loads(process.stdout.readline())
            self.assertTrue(set(objects.items()) <= set(grader.submission_sysv_ipc()))
            grader.restart_submission_for_queries()
            process.wait(timeout=5)
            self.assertEqual(grader.submission_pids(), set())
            self.assertEqual(grader.submission_sysv_ipc(), [])
            reader = '''
import ctypes, errno
libc = ctypes.CDLL(None, use_errno=True)
libc.shmat.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
libc.shmat.restype = ctypes.c_void_p
address = libc.shmat(SHM, None, 0)
assert address == ctypes.c_void_p(-1).value
assert ctypes.get_errno() in (errno.EINVAL, errno.EIDRM)
buffer = ctypes.create_string_buffer(256)
assert libc.msgctl(MSG, 2, buffer) == -1
assert ctypes.get_errno() in (errno.EINVAL, errno.EIDRM)
assert libc.semctl(SEM, 0, 12) == -1
assert ctypes.get_errno() in (errno.EINVAL, errno.EIDRM)
'''
            for name, value in objects.items():
                reader = reader.replace(name.upper(), str(value))
            result = subprocess.run(grader.SUBMISSION_COMMAND + [
                '/usr/local/bin/search-swe-query-cpu', '/opt/conda/bin/python', '-c', reader],
                cwd='/', capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            grader.stop_submission_processes()
            process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()
            grader.clear_submission_sysv_ipc()

    def test_deployment_fails_closed_on_ipc_cleanup_error(self):
        with patch.object(grader, 'submission_sysv_ipc', return_value=[('shm', 7)]), \
                patch.object(grader.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaises(grader.VerificationError):
                grader.clear_submission_sysv_ipc()
        with patch.object(grader, 'submission_sysv_ipc', return_value=[('shm', 7)]), \
                patch.object(grader.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
            with self.assertRaises(grader.VerificationError):
                grader.clear_submission_sysv_ipc()

    def test_kernel_index_capacity(self):
        if not os.path.ismount(grader.INDEX_DIR):
            self.skipTest('requires the verifier Docker tmpfs mount')
        info = grader.validate_index_workspace()
        self.assertEqual(info['capacity_bytes'], 64 * 1024 ** 2)
        path = grader.INDEX_DIR / '.quota-regression'
        try:
            with self.assertRaises(OSError) as error:
                with path.open('wb', buffering=0) as f:
                    for _ in range(65):
                        f.write(b'x' * (1024 ** 2))
            self.assertEqual(error.exception.errno, errno.ENOSPC)
        finally:
            path.unlink(missing_ok=True)

    def test_submission_file_limit_and_privilege_boundary(self):
        if os.geteuid() != 0:
            self.skipTest('requires the verifier image and root to exercise runuser')
        try:
            pwd.getpwnam(grader.SUBMISSION_USER)
        except KeyError:
            self.skipTest('requires the verifier image submission user')
        program = '''
import json, os, resource
handles = [open('/dev/null', 'rb') for _ in range(2048)]
status = open('/proc/self/status').read().splitlines()
print(json.dumps(dict(uid=os.getuid(), gid=os.getgid(), opened=len(handles),
    nofile=resource.getrlimit(resource.RLIMIT_NOFILE),
    no_new_privs=next(line.split()[1] for line in status if line.startswith('NoNewPrivs:')),
    inherited_secret='SEARCH_SWE_TEST_SECRET' in os.environ)))
'''
        with patch.dict(os.environ, {'SEARCH_SWE_TEST_SECRET': 'must-not-inherit'}):
            result = subprocess.run(grader.SUBMISSION_COMMAND + ['/opt/conda/bin/python', '-c', program],
                                    cwd='/', capture_output=True, text=True, timeout=10, check=True)
        data = json.loads(result.stdout)
        self.assertEqual(data['nofile'], [grader.NOFILE_LIMIT] * 2)
        self.assertEqual(data['opened'], 2048)
        self.assertEqual((data['uid'], data['gid']), (grader.SUBMISSION_UID, grader.SUBMISSION_GID))
        self.assertEqual(data['no_new_privs'], '1')
        self.assertFalse(data['inherited_secret'])

    def test_reward_anchors_and_quantile(self):
        for seconds, expected in ((.03, 1), (.06, .5), (.15, .2)):
            rows = [dict(score=1, elapsed_seconds=seconds) for _ in range(20)]
            self.assertAlmostEqual(grader.summarize_scores(rows)['reward'], expected)
        rows[-1]['elapsed_seconds'] = .5
        self.assertEqual(grader.summarize_scores(rows)['p95_seconds'], .15)
        rows[-2].update(elapsed_seconds=.8, timed_out=True, score=0)
        result = grader.summarize_scores(rows)
        self.assertEqual(result['p95_seconds'], .5)
        self.assertAlmostEqual(result['reward'], .95 * .06)

    def test_invalid_timing(self):
        for value in (0, -1, math.inf, math.nan):
            with self.assertRaises(grader.VerificationError):
                grader.summarize_scores([dict(score=1, elapsed_seconds=value)])
        with self.assertRaises(grader.VerificationError):
            grader.summarize_scores([])

    def test_quality_floor_boundary_and_timeout(self):
        for hits, expected in ((18, 0), (19, .475), (20, .5)):
            rows = [dict(score=int(i < hits), elapsed_seconds=.06) for i in range(20)]
            result = grader.summarize_scores(rows)
            self.assertAlmostEqual(result['reward'], expected)
            self.assertEqual(result['quality_gate_passed'], hits >= 19)
            self.assertAlmostEqual(result['reward_before_quality_gate'], hits / 20 * .5)
        rows[0].update(score=0, elapsed_seconds=.6, timed_out=True)
        self.assertAlmostEqual(grader.summarize_scores(rows)['reward'], .475)
        rows[1].update(score=0, elapsed_seconds=.6, timed_out=True)
        self.assertEqual(grader.summarize_scores(rows)['reward'], 0)

    def timed(self, command, timeout, root):
        with patch.object(grader, 'SUBMISSION_COMMAND', []), patch.object(grader, 'SUBMISSION_DIR', root):
            return grader.run_timed(command, timeout=timeout,
                                    stdout_path=root/'stdout', stderr_path=root/'stderr')

    def test_exit_event_and_separate_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.timed(['/bin/sleep', '.08'], .5, root)
            self.assertEqual(result['returncode'], 0)
            self.assertFalse(result['timed_out'])
            self.assertGreaterEqual(result['elapsed_seconds'], .08)
            # The precise polling-vs-exit-event comparison is recorded separately;
            # tolerate machine scheduling jitter in routine regression tests.
            self.assertLess(result['elapsed_seconds'], .2)
            result = self.timed(['/bin/sleep', '2'], .08, root)
            self.assertTrue(result['timed_out'])
            self.assertLess(result['elapsed_seconds'], .2)
            self.assertGreaterEqual(result['cleanup_seconds'], .19)
            self.assertEqual(self.timed(['/bin/true'], .5, root)['returncode'], 0)

    def test_timeout_preserves_separate_service(self):
        service = subprocess.Popen(['/bin/sleep', '10'], start_new_session=True)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                result = self.timed(['/bin/sh', '-c', 'sleep 10 & wait'], .04, Path(tmp))
                self.assertTrue(result['timed_out'])
                self.assertIsNone(service.poll())
        finally:
            service.terminate()
            service.wait()

    def test_exit_failure_and_launch_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(self.timed(['/bin/sh', '-c', 'exit 7'], .5, root)['returncode'], 7)
            result = self.timed(['/no-such-executable'], .5, root)
            self.assertIn('error', result)
            aggregate = grader.summarize_scores([dict(result, score=0)])
            self.assertEqual(aggregate['p95_seconds'], .5)

    def test_output_contract_and_query_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            doc_rows = {'a': 0, 'b': 1, 'c': 2}
            good = {'query_id': 'q', 'results': [dict(doc_id=x, score=3-i) for i,x in enumerate(doc_rows)]}
            output.write_text(json.dumps(good)+'\n')
            metrics = dict(returncode=0, elapsed_seconds=.03, timed_out=False)
            self.assertEqual(grader.score_query('q', output, metrics, None, doc_rows, {'q': {'a'}})['score'], 1)
            for change in (dict(returncode=1), dict(timed_out=True), dict(elapsed_seconds=.501)):
                self.assertEqual(grader.score_query('q', output, metrics | change, None, doc_rows, {'q': {'a'}})['score'], 0)
            for bad in (
                {'query_id': 'wrong', 'results': good['results']},
                {'query_id': 'q', 'results': [good['results'][0]]*3},
                {'query_id': 'q', 'results': [dict(doc_id='a', score=float('nan'))]*3},
                {'query_id': 'q', 'results': list(reversed(good['results']))},
            ):
                output.write_text(json.dumps(bad)+'\n')
                self.assertEqual(grader.score_query('q', output, metrics, None, doc_rows, {'q': {'a'}})['score'], 0)

    def test_late_writes_cannot_change_completed_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'output'
            snapshot = Path(tmp) / 'snapshot'
            good = dict(query_id='q', results=[dict(doc_id=d, score=3-i)
                        for i, d in enumerate(('a', 'b', 'c'))])
            with output.open('wb') as delayed_writer:
                grader.snapshot_completed_output(output, snapshot)
                delayed_writer.write((json.dumps(good)+'\n').encode())
                delayed_writer.flush()
            metrics = dict(returncode=0, elapsed_seconds=.01, timed_out=False)
            docs, truth = {'a': 0, 'b': 1, 'c': 2}, {'q': {'a'}}
            self.assertEqual(grader.score_query('q', output, metrics, None, docs, truth)['score'], 1)
            self.assertEqual(grader.score_query('q', snapshot, metrics, None, docs, truth)['score'], 0)
            with patch.object(grader, 'MAX_OUTPUT_BYTES', 4):
                with self.assertRaises(grader.VerificationError):
                    grader.snapshot_completed_output(output, snapshot)

    def test_post_exit_output_is_charged_until_capture(self):
        good = dict(query_id='q', results=[dict(doc_id=d, score=3-i)
                    for i, d in enumerate(('a', 'b', 'c'))])
        original_capture = grader.snapshot_completed_output
        for delay, expected_score in ((.04, 1), (.55, 0)):
            with self.subTest(delay=delay), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                output, snapshot = root/'output', root/'snapshot'
                with output.open('wb', buffering=0) as retained_fd:
                    def capture_after_exit(source, destination):
                        self.assertEqual(source.read_bytes(), b'')
                        time.sleep(delay)
                        retained_fd.write((json.dumps(good)+'\n').encode())
                        original_capture(source, destination)
                    with patch.object(grader, 'SUBMISSION_COMMAND', []), \
                            patch.object(grader, 'SUBMISSION_DIR', root), \
                            patch.object(grader, 'freeze_output_dir'), \
                            patch.object(grader, 'snapshot_completed_output', side_effect=capture_after_exit):
                        metrics = grader.run_timed(['/bin/true'], timeout=.5,
                            stdout_path=root/'stdout', stderr_path=root/'stderr',
                            output_path=output, snapshot_path=snapshot)
                self.assertGreaterEqual(metrics['output_capture_seconds'], delay)
                self.assertGreaterEqual(metrics['elapsed_seconds'],
                                        metrics['process_elapsed_seconds'] + delay)
                self.assertEqual(metrics['timed_out'], delay > .5)
                scored = grader.score_query('q', snapshot, metrics, metrics['output_error'],
                                            {'a': 0, 'b': 1, 'c': 2}, {'q': {'a'}})
                self.assertEqual(scored['score'], expected_score)
                self.assertEqual(scored['output_valid'], True)

    def test_failed_capture_is_timed_and_cannot_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def fail_capture(*args):
                time.sleep(.04)
                raise grader.VerificationError('controlled capture failure')
            with patch.object(grader, 'SUBMISSION_COMMAND', []), \
                    patch.object(grader, 'SUBMISSION_DIR', root), \
                    patch.object(grader, 'freeze_output_dir', side_effect=fail_capture):
                metrics = grader.run_timed(['/bin/true'], timeout=.5,
                    stdout_path=root/'stdout', stderr_path=root/'stderr',
                    output_path=root/'output', snapshot_path=root/'snapshot')
            self.assertGreaterEqual(metrics['elapsed_seconds'], .04)
            self.assertIn('controlled capture failure', metrics['output_error'])
            scored = grader.score_query('q', root/'snapshot', metrics, metrics['output_error'], {}, {})
            self.assertEqual(scored['score'], 0)

    def test_finalizer_composite_and_judge_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            evaluation=root/'evaluation.json'; reward=root/'reward.json'; trajectory=root/'trajectory.json'
            trajectory.write_text('{}')
            (root / 'details.json').write_text(json.dumps({'jailbreak_judge': {
                'score': 1, 'criteria': [{'name': 'jailbreak_judge', 'raw': 'yes', 'value': 1}],
                'judge_output': 'Reviewed the trajectory and files.'}}))
            evaluation.write_text(json.dumps(dict(valid=True, reward=.2,
                primary_metric=dict(name='Accuracy@3', value=1), scoring=dict(p95_seconds=.15))))
            with patch.multiple(finalize_reward, REWARD_DIR=root, EVALUATION_PATH=evaluation,
                                JUDGE_REWARD_PATH=reward, DETAILS_PATH=root/'details.json',
                                TRAJECTORY_PATH=trajectory):
                for status, expected in (('0', .2), ('1', 0)):
                    reward.write_text('{"jailbreak_judge":1}')
                    with patch.object(finalize_reward, 'JUDGE_STATUS', status), contextlib.redirect_stdout(io.StringIO()):
                        finalize_reward.main()
                    self.assertEqual(json.loads(reward.read_text())['reward'], expected)
                    self.assertEqual(float((root/'reward.txt').read_text()), expected)
                # A legacy accuracy-only report must not bypass latency scoring.
                data=json.loads(evaluation.read_text()); data['reward']=1
                evaluation.write_text(json.dumps(data)); reward.write_text('{"jailbreak_judge":1}')
                with patch.object(finalize_reward, 'JUDGE_STATUS', '0'), contextlib.redirect_stdout(io.StringIO()):
                    finalize_reward.main()
                self.assertEqual(json.loads(reward.read_text())['reward'], 0)

    def test_finalizer_recomputes_quality_floor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evaluation = root / 'evaluation.json'
            reward = root / 'reward.json'
            trajectory = root / 'trajectory.json'
            trajectory.write_text('{}')
            (root / 'details.json').write_text(json.dumps({'jailbreak_judge': {
                'score': 1, 'criteria': [{'name': 'jailbreak_judge', 'raw': 'yes', 'value': 1}],
                'judge_output': 'Reviewed the trajectory and files.'}}))
            with patch.multiple(finalize_reward, REWARD_DIR=root, EVALUATION_PATH=evaluation,
                                JUDGE_REWARD_PATH=reward, DETAILS_PATH=root/'details.json',
                                TRAJECTORY_PATH=trajectory, JUDGE_STATUS='0'):
                for accuracy, reported, expected, valid in (
                    (.9, 0, 0, True), (.95, .475, .475, True), (1, .5, .5, True),
                    (.9, .45, 0, False), (.95, 0, 0, False),
                ):
                    evaluation.write_text(json.dumps(dict(valid=True, reward=reported,
                        primary_metric=dict(name='Accuracy@3', value=accuracy),
                        scoring=dict(p95_seconds=.06))))
                    reward.write_text('{"jailbreak_judge":1}')
                    with contextlib.redirect_stdout(io.StringIO()):
                        finalize_reward.main()
                    self.assertEqual(json.loads(reward.read_text())['reward'], expected)
                    self.assertEqual(float((root/'reward.txt').read_text()), expected)
                    gate = json.loads((root/'details.json').read_text())['final_gate']
                    self.assertEqual(gate['evaluation_valid'], valid)
                    self.assertEqual(gate['quality_gate_passed'], accuracy >= .95)


if __name__ == '__main__':
    unittest.main()
