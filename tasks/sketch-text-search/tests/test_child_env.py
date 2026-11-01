"""Submission processes use the trusted phase driver path without judge keys."""
import os
import unittest
from unittest.mock import patch
import grader


class ChildEnvironmentTests(unittest.TestCase):
    def test_phase_library_path_is_preserved_and_judge_keys_are_excluded(self):
        values = {"LD_LIBRARY_PATH": "/trusted/nvidia/lib:/trusted/torch/lib",
                  "OPENROUTER_API_KEY": "submission-fixture", "OPENAI_API_KEY": "judge-fixture",
                  "VERIFIER_OPENAI_API_KEY": "verifier-fixture"}
        with patch.dict(os.environ, values, clear=True):
            child = grader.child_env()
        self.assertEqual(child["LD_LIBRARY_PATH"], values["LD_LIBRARY_PATH"])
        self.assertNotIn("OPENROUTER_API_KEY", child)
        self.assertNotIn("OPENAI_API_KEY", child)
        self.assertNotIn("VERIFIER_OPENAI_API_KEY", child)


if __name__ == "__main__":
    unittest.main()
