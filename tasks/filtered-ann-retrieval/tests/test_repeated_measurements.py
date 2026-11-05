from pathlib import Path
import importlib.util
import tempfile
import unittest

HERE = Path(__file__).parent
MODULE = HERE/"repeated_measurements.py"
if not MODULE.exists():
    MODULE = HERE/"runtime/repeated_measurements.py"
spec = importlib.util.spec_from_file_location("timing_measurements", MODULE)
timing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timing)


class TimingMeasurements(unittest.TestCase):
    def test_five_samples_use_median_not_mean(self):
        self.assertEqual(timing.median_seconds([.001, .002, .003, .9, .8]), .003)
        self.assertEqual(timing.median_seconds([.8, .9, .003, .002, .001]), .003)

    def test_failed_samples_are_not_dropped(self):
        self.assertEqual(timing.median_seconds([.001, .002, .003, None, None]), .003)
        self.assertIsNone(timing.median_seconds([.001, .002, None, None, None]))

    def test_requires_five_valid_duration_fields(self):
        for samples in [[1]*4, [1]*6, [1, 1, 1, 1, -1], [1, 1, 1, 1, float('nan')], [1, 1, 1, 1, '1']]:
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                timing.median_seconds(samples)
