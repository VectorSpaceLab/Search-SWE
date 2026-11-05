"""Portable CPU selection, preparation preflight, and current-runtime truth."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import runtime_limits as runtime
from kernel import prepare_targets


class PlatformTests(unittest.TestCase):
    def test_single_reference_measurement_keeps_each_time_gate(self):
        import calibrate_platform
        limits = {'build_seconds': 10, 'insert_seconds': 2, 'full_scan_seconds': [[10] * 5]}
        reference = {'build_seconds': 1, 'insert_seconds': [.1], 'cells': [
            {'stage': 0, 'k': k, 'seconds': .1} for k in (100, 200, 400, 800, 1000)]}
        def measure(value):
            with patch.object(calibrate_platform.grader, 'evaluate_dataset', return_value=value) as evaluate:
                result = calibrate_platform.measure(16, limits, initial_count=1100, batch_size=2, stages=1)
                evaluate.assert_called_once()
                self.assertEqual(evaluate.call_args.kwargs['repeat'], 0)
                return result
        self.assertIs(measure(reference), reference)
        for phase in ('build', 'insert', 'query', 'incomplete'):
            value = copy.deepcopy(reference)
            if phase == 'build':
                value['build_seconds'] = 11
            elif phase == 'insert':
                value['insert_seconds'][0] = 3
            elif phase == 'query':
                value['cells'][0]['seconds'] = 2
            else:
                value['cells'].pop()
            with self.subTest(phase=phase), self.assertRaises(RuntimeError):
                measure(value)

    def test_publishing_unchanged_inputs_preserves_the_preparation_key(self):
        import calibrate_platform
        manifest = {'files': [{'path': 'data/fixture.npy', 'size_bytes': 10,
                               'sha256': 'a' * 64, 'source': {'revision': None}}]}
        with patch.object(calibrate_platform, 'platform_fingerprint', return_value='host'), \
             patch.object(calibrate_platform, 'kernel_signature', return_value={'runtime': 'same'}), \
             patch.object(calibrate_platform, 'digest', return_value='same-code'), \
             patch.object(Path, 'read_text', side_effect=lambda: json.dumps(manifest)):
            first = calibrate_platform.preparation_key()
            manifest['files'][0]['source']['revision'] = 'b' * 40
            self.assertEqual(calibrate_platform.preparation_key(), first)
            manifest['files'][0]['sha256'] = 'c' * 64
            self.assertNotEqual(calibrate_platform.preparation_key(), first)

    def test_reboot_does_not_invalidate_the_platform_identity(self):
        original = Path.read_text
        boot = ['first-boot']
        def read(path, *args, **kwargs):
            if path == Path('/proc/sys/kernel/random/boot_id'):
                return boot[0]
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', read):
            first = runtime.platform_fingerprint()
            boot[0] = 'after-reboot'
            self.assertEqual(runtime.platform_fingerprint(), first)

    def test_legal_cpu_ids_do_not_need_to_match_the_author_machine(self):
        for allowed in (set(range(16)), set(range(64, 80)), set(range(100, 132))):
            with patch.object(runtime.os, 'sched_getaffinity', return_value=allowed):
                self.assertEqual(runtime.select_cpus(), sorted(allowed)[:16])
        with patch.object(runtime.os, 'sched_getaffinity', return_value=set(range(15))):
            with self.assertRaisesRegex(RuntimeError, 'At least 16'):
                runtime.select_cpus()

    def test_preparation_is_checked_before_the_container_command(self):
        data = {'schema_version': 2, 'timing_repeats': 5, 'platform_fingerprint': 'this-host',
                'runtime_signature': {'current': True},
                'reference_sha256': {'exact_search.py': 'sha', 'baseline_search.py': 'sha'}}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime, 'platform_fingerprint', return_value='this-host'), \
             patch.object(runtime, 'kernel_signature', return_value={'current': True}), \
             patch.object(runtime, 'digest', return_value='sha'):
            path = Path(directory) / 'limits.json'
            with self.assertRaisesRegex(RuntimeError, 'preparation is missing'):
                runtime.load_runtime_limits(path)
            path.write_text(json.dumps(data))
            self.assertEqual(runtime.load_runtime_limits(path), data)
            for field, value, error in [('timing_repeats', 1, 'five'),
                                        ('platform_fingerprint', 'other-host', 'Machine'),
                                        ('runtime_signature', {'old': True}, 'Faiss runtime')]:
                altered = copy.deepcopy(data)
                altered[field] = value
                path.write_text(json.dumps(altered))
                with self.assertRaisesRegex(RuntimeError, error):
                    runtime.load_runtime_limits(path)

    def test_runtime_modules_are_identical(self):
        task = Path(__file__).resolve().parents[1]
        if not (task / 'environment/runtime_limits.py').exists():
            self.skipTest('Requires the source package')
        self.assertEqual((task / 'environment/runtime_limits.py').read_bytes(),
                         (task / 'tests/runtime_limits.py').read_bytes())

    def test_targets_regenerate_after_runtime_or_input_changes(self):
        rng = np.random.default_rng(7)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, count in [('initial', 1100), ('inserts', 4), ('queries', 4)]:
                np.save(root / f'{name}.npy', rng.normal(size=(count, 16)).astype('float32'))
            args = [root / f'{name}.npy' for name in ('initial', 'inserts', 'queries')]
            first = prepare_targets(*args, root / 'truth', batch_size=2, stages=2, threads=1)
            self.assertEqual(prepare_targets(*args, root / 'truth', batch_size=2, stages=2, threads=1), first)
            manifest = root / 'truth/truth-manifest.json'
            broken = copy.deepcopy(first)
            broken['runtime_signature']['binary_sha256'] = 'another-build'
            manifest.write_text(json.dumps(broken))
            restored = prepare_targets(*args, root / 'truth', batch_size=2, stages=2, threads=1)
            self.assertEqual(restored['runtime_signature'], first['runtime_signature'])
            probes = np.load(args[2])
            probes[0] = np.load(args[0])[0]
            np.save(args[2], probes)
            updated = prepare_targets(*args, root / 'truth', batch_size=2, stages=2, threads=1)
            self.assertNotEqual(updated['input_sha256'], first['input_sha256'])
            self.assertEqual(np.load(root / 'truth/truth.npy')[0, 0], 0)


if __name__ == '__main__':
    unittest.main()
