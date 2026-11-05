"""Automatic preparation must reuse valid caches, repair permissions and stop on errors."""
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

HELPER = Path(__file__).resolve().parents[1] / 'tools/prepare_task.py'


@unittest.skipUnless(HELPER.is_file(), 'Requires the source package')
class PreparationCacheTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('incremental_prepare_fixture', HELPER)
        self.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.helper)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ('data/corpus/1536', 'data/validation/1536', 'tests/data/1536', 'environment/docs'):
            (self.root / name).mkdir(parents=True, mode=0o700)
        entries = []
        for name in ('data/corpus/1536/initial.npy', 'data/validation/1536/queries.npy', 'tests/data/1536/queries.npy'):
            path = self.root / name
            path.write_bytes(b'fixed fixture data')
            path.chmod(0o600)
            entries.append({'path': name, 'size_bytes': path.stat().st_size,
                            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        (self.root / 'assets.json').write_text(json.dumps({'files': entries}))
        for name in ('exact_search.py', 'baseline_search.py', 'profile_public.py', 'runtime_limits.py'):
            (self.root / 'environment' / name).write_text('# fixture\n')
            (self.root / 'environment' / name).chmod(0o600)
        self.key = 'a' * 64
        self.measurements = 0

    def container(self, root, cpus, *, output=None, cache_key=False):
        if cache_key:
            return self.key
        self.measurements += 1
        for name in ('public', 'validation', 'private'):
            (output / name).mkdir()
        (output / 'public/limits.json').write_text(json.dumps({'preparation_key': self.key}))
        (output / 'validation/targets.npy').write_bytes(b'public targets')
        (output / 'private/targets.npy').write_bytes(b'private targets')

    def test_reuse_corruption_recovery_and_separate_allocations(self):
        with patch.object(self.helper.subprocess, 'run'), patch.object(self.helper, 'container', side_effect=self.container):
            first = self.helper.prepare(self.root, '0-15')
            self.assertEqual(self.helper.prepare(self.root, '0-15'), first)
            self.assertEqual(self.measurements, 1)
            (first / 'private/targets.npy').write_bytes(b'corruption')
            self.helper.prepare(self.root, '0-15')
            self.assertEqual(self.measurements, 2)
            self.key = 'b' * 64
            second = self.helper.prepare(self.root, '16-31')
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_dir())
            self.assertEqual(self.measurements, 3)

    def test_public_permissions_are_fixed_without_exposing_hidden_inputs(self):
        self.helper.prepare_inputs(self.root)
        for name in ('data/corpus', 'data/corpus/1536', 'environment'):
            self.assertEqual(stat.S_IMODE((self.root / name).stat().st_mode), 0o755)
        for name in ('data/corpus/1536/initial.npy', 'environment/baseline_search.py'):
            self.assertEqual(stat.S_IMODE((self.root / name).stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE((self.root / 'tests/data/1536/queries.npy').stat().st_mode), 0o600)

    def test_changed_input_stops_before_any_container(self):
        (self.root / 'data/corpus/1536/initial.npy').write_bytes(b'changed')
        with patch.object(self.helper, 'container') as run:
            with self.assertRaisesRegex(ValueError, 'Missing or changed input'):
                self.helper.prepare(self.root, '0-15')
            run.assert_not_called()

    def test_failed_calibration_never_becomes_a_completed_cache(self):
        def fail(root, cpus, *, output=None, cache_key=False):
            if cache_key:
                return self.key
            raise RuntimeError('reference failed')
        with patch.object(self.helper.subprocess, 'run'), patch.object(self.helper, 'container', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'reference failed'):
                self.helper.prepare(self.root, '0-15')
        self.assertFalse((self.root / 'tests/platform' / self.key).exists())


if __name__ == '__main__':
    unittest.main()
