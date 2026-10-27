"""Preserve runtime-selected CUDA libraries in sanitized submission processes."""

import os
import unittest
from unittest.mock import patch

import grader


class CudaEnvironmentTests(unittest.TestCase):
    def test_both_phases_keep_runtime_library_path_without_judge_credentials(self):
        for query_phase in (False, True):
            for library_path in (
                "/usr/local/nvidia/lib:/usr/local/nvidia/lib64",
                "/runtime/selected/compat:/usr/local/nvidia/lib64",
            ):
                with self.subTest(query_phase=query_phase, library_path=library_path):
                    with patch.object(grader, "QUERY_PHASE", query_phase), patch.dict(
                        os.environ,
                        {"LD_LIBRARY_PATH": library_path,
                         "OPENAI_API_KEY": "verifier-only-fixture",
                         "OPENAI_BASE_URL": "https://offline.invalid/v1",
                         "OPENROUTER_API_KEY": "verifier-only-fixture"},
                        clear=True,
                    ):
                        child = grader.child_env()
                    self.assertEqual(child["LD_LIBRARY_PATH"], library_path)
                    self.assertEqual(child["HOME"], "/work/output" if query_phase else "/work/index")
                    self.assertNotIn("OPENAI_API_KEY", child)
                    self.assertNotIn("OPENAI_BASE_URL", child)
                    self.assertNotIn("OPENROUTER_API_KEY", child)

    def test_default_loader_search_is_preserved_when_path_is_absent_or_empty(self):
        for parent in ({}, {"LD_LIBRARY_PATH": ""}):
            with self.subTest(parent=parent), patch.dict(os.environ, parent, clear=True):
                child = grader.child_env()
            self.assertNotIn("LD_LIBRARY_PATH", child)


if __name__ == "__main__":
    unittest.main()
