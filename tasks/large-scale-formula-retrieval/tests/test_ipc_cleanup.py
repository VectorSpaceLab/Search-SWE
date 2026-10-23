"""Fail-closed IPC enumeration and cleanup; kernel cases live in test_runtime."""
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import runtime


class CleanupTests(unittest.TestCase):
    def test_owner_and_creator_are_both_selected(self):
        identifiers = {'shm': 'shmid', 'msg': 'msqid', 'sem': 'semid'}

        def table(path):
            return (f"{identifiers[path.name]} uid cuid\n"
                    "11 65534 10001\n12 10001 65534\n13 65534 65534\n")

        with patch.object(Path, 'read_text', table):
            self.assertEqual(runtime.worker_ipc(),
                             [(flag, number) for flag in ('-m', '-q', '-s')
                              for number in (11, 12)])

    def test_unreadable_or_malformed_inventory_fails(self):
        for value in ('', 'shmid uid\n1 10001\n', 'shmid uid cuid\n1 x 10001\n'):
            with self.subTest(value=value), patch.object(Path, 'read_text', return_value=value):
                with self.assertRaises(runtime.Violation):
                    runtime.worker_ipc()
        with patch.object(Path, 'read_text', side_effect=PermissionError):
            with self.assertRaises(runtime.Violation):
                runtime.worker_ipc()

    def test_removal_error_timeout_and_residuals_fail(self):
        for error in (OSError('failed'), subprocess.TimeoutExpired('ipcrm', 5)):
            with patch.object(runtime, 'worker_ipc', return_value=[('-m', 7)]), \
                    patch.object(runtime.subprocess, 'run', side_effect=error):
                with self.assertRaises(runtime.Violation):
                    runtime.clear_worker_ipc()
        for returncode in (0, 1):
            with patch.object(runtime, 'worker_ipc', return_value=[('-m', 7)]), \
                    patch.object(runtime.subprocess, 'run',
                                 return_value=subprocess.CompletedProcess([], returncode)):
                with self.assertRaises(runtime.Violation):
                    runtime.clear_worker_ipc()


if __name__ == '__main__':
    unittest.main()
