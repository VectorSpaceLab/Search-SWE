"""CPU-only checks for repeated timing, portable GPU checks and storage."""
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent / 'runtime'))
import evaluate as evaluator
from storage import StorageBudget, logical_bytes
from worker import initialize_gpu


def sample(seconds, valid=True, ndcg=1.):
    return dict(dataset='belebele', language='en', query_id='q', seconds=seconds,
                valid=valid, ndcg=ndcg if valid else 0., recall=1. if valid else 0.,
                ranked_doc_ids=['d'] if valid else [], failure=None if valid else 'TimeoutError')


class MeasurementTests(unittest.TestCase):
    def select(self, records):
        return evaluator.median_queries([{'queries': [r]} for r in records], .5)[0]

    def test_median_selects_matching_quality_without_optimizing_quality(self):
        records = [sample(t, ndcg=q) for t, q in [(.4, .9), (.1, 1), (.5, .8), (.2, .7), (.3, .6)]]
        selected = self.select(records)
        self.assertEqual(selected['selected_round'], 5)
        self.assertEqual(selected['seconds'], .3)
        self.assertEqual(selected['ndcg'], .6)

    def test_two_failed_runs_do_not_override_three_successes(self):
        selected = self.select([sample(.001, False), sample(.8, False), sample(.1), sample(.2), sample(.3)])
        self.assertTrue(selected['valid'])
        self.assertEqual(selected['seconds'], .3)
        self.assertEqual(selected['measurement_seconds'], [.5, .5, .1, .2, .3])

    def test_three_failed_runs_keep_zero_credit(self):
        selected = self.select([sample(.001, False), sample(.8, False), sample(.1), sample(.2), sample(.01, False)])
        self.assertFalse(selected['valid'])
        self.assertEqual(selected['ndcg'], 0)
        self.assertEqual(selected['seconds'], .5)

    def test_ties_use_round_order_and_accept_deadline_equality(self):
        self.assertEqual(self.select([sample(.2, ndcg=i / 5) for i in range(5)])['selected_round'], 3)
        selected = self.select([sample(.5, False), sample(.5, False), sample(.5), sample(.5), sample(.5)])
        self.assertTrue(selected['valid'])

    def test_all_rounds_need_identical_query_populations(self):
        for count in (0, 1, 4, 6):
            with self.assertRaises(evaluator.ContractViolation):
                evaluator.median_queries([{'queries': [sample(.1)]}] * count, .5)
        rounds = [{'queries': [sample(.1)]} for _ in range(5)]
        rounds[-1]['queries'][0]['query_id'] = 'different'
        with self.assertRaises(evaluator.ContractViolation):
            evaluator.median_queries(rounds, .5)

    def test_wrapper_starts_five_independent_rounds_with_same_budgets(self):
        reports = []
        for duration in (.4, .1, .5, .2, .3):
            records = []
            for dataset, languages in [('belebele', ['ar', 'zh', 'en', 'fr', 'hi', 'it', 'ja', 'pt', 'ru', 'es']),
                                       ('xquad', ['ar', 'zh', 'en', 'hi', 'ru', 'es'])]:
                records.extend(dict(sample(duration), dataset=dataset, language=lang, query_id=dataset + lang)
                               for lang in languages)
            reports.append(dict(queries=records, preparation_seconds=2., evaluation_seconds=3., gpu_peak_bytes=0,
                                task_storage_peak_bytes=32, fixed_input_bytes=16, container_memory_sample_peak_bytes=64,
                                gpu_uuid=None, cgroup_limits={}))
        with tempfile.TemporaryDirectory() as directory, patch.object(evaluator, 'evaluate_once', side_effect=reports) as run:
            report = evaluator.evaluate('submission', 'corpus', 'hidden', 'development', directory, require_gpu=False)
            self.assertEqual(report['Q'], 1)
            self.assertEqual(report['measurement_rounds'], 5)
            self.assertEqual(report['max_query_seconds'], .3)
            self.assertEqual(run.call_count, 5)
            self.assertEqual(len({call.args[4] for call in run.call_args_list}), 5)
            for call in run.call_args_list:
                self.assertEqual(call.kwargs['preparation_seconds'], 1800)
                self.assertEqual(call.kwargs['query_seconds'], .5)

    def test_round_preparation_or_resource_failure_invalidates_whole_run(self):
        for failing_round in range(1, 6):
            reports = [{}] * (failing_round - 1) + [evaluator.ContractViolation('storage limit')]
            with self.subTest(failing_round=failing_round), tempfile.TemporaryDirectory() as directory, \
                    patch.object(evaluator, 'evaluate_once', side_effect=reports) as run:
                with self.assertRaisesRegex(evaluator.ContractViolation, 'storage limit'):
                    evaluator.evaluate('submission', 'corpus', 'hidden', 'development', directory, require_gpu=False)
                self.assertEqual(run.call_count, failing_round)

    def test_verifier_budgets_cover_five_full_rounds(self):
        import re
        import tomllib
        task = tomllib.loads((Path(__file__).resolve().parents[1] / 'task.toml').read_text())
        source = Path(__file__).with_name('test.sh').read_text()
        primary = int(re.search(r' (\d+)s /opt/conda/bin/python -I /tests/grade.py', source)[1])
        probes = (13002 + 126) // 127
        self.assertGreater(primary, 5 * (1800 + (13002 + probes) * .5))
        self.assertGreaterEqual(task['verifier']['timeout_sec'], primary + 1200 + 600)
        self.assertEqual(task['agent']['timeout_sec'], 21600)


class ResourceTests(unittest.TestCase):
    def test_gpu_initialization_only_needs_one_available_device(self):
        cuda = types.SimpleNamespace(device_count=lambda: 1, is_available=lambda: True, init=Mock())
        sync = Mock()
        torch = types.SimpleNamespace(cuda=cuda, _C=types.SimpleNamespace(_cuda_synchronize=sync))
        self.assertIs(initialize_gpu(torch), sync)
        cuda.init.assert_called_once()
        for count, available in ((0, False), (2, True), (1, False)):
            cuda.device_count = lambda: count
            cuda.is_available = lambda: available
            with self.assertRaisesRegex(RuntimeError, 'one usable GPU'):
                initialize_gpu(torch)

    def test_meter_does_not_request_model_or_memory_configuration(self):
        nvml = Mock()
        nvml.nvmlDeviceGetHandleByUUID.return_value = 'handle'
        with patch('subprocess.check_output', return_value='GPU-test-uuid\n') as query, \
                patch.dict(sys.modules, {'pynvml': nvml}), patch.object(evaluator, 'StorageBudget'):
            meter = evaluator.Meter(True)
            try:
                self.assertEqual(meter.gpu_uuid, 'GPU-test-uuid')
                self.assertIn('--query-gpu=uuid', query.call_args.args[0])
            finally:
                meter.close()

    def test_logical_storage_counts_sparse_files_and_ignores_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'ordinary').write_bytes(b'abcd')
            with (root / 'sparse').open('wb') as handle:
                handle.truncate(1024**2)
            (root / 'linked').symlink_to(root / 'sparse')
            (root / 'outside').symlink_to('/usr')
            self.assertEqual(logical_bytes([root]), 1024**2 + 4)

    def test_storage_includes_inputs_and_all_writable_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, app, temporary = [root / name for name in ('inputs', 'app', 'tmp')]
            for path in (inputs, app, temporary):
                path.mkdir()
                (path / 'file').write_bytes(b'1234')
            budget = StorageBudget([inputs], [app, temporary], limit=12)
            self.assertEqual(budget.check(force=True), 12)
            (temporary / 'extra').write_bytes(b'x')
            with self.assertRaisesRegex(RuntimeError, 'storage exceeded'):
                budget.check(force=True)

    def test_storage_sampler_failure_is_not_silently_ignored(self):
        with patch.object(evaluator, 'StorageBudget'):
            meter = evaluator.Meter(False)
            try:
                meter.storage_error = RuntimeError('storage exceeded')
                with self.assertRaisesRegex(evaluator.ContractViolation, 'storage exceeded'):
                    meter.check()
            finally:
                meter.close()


if __name__ == '__main__':
    unittest.main()
