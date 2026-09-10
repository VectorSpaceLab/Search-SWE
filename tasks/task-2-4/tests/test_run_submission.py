from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("run_submission.py")
SPEC = importlib.util.spec_from_file_location("task2_4_runner", MODULE_PATH)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class RunnerTests(unittest.TestCase):
    def test_submission_environment_preserves_only_allowed_api_keys(self) -> None:
        values = {
            "API_KEY": "private-secret",
            "MODEL_API": "https://private.invalid/v1",
            "MODEL_NAME": "private-model",
            "OTHER_API_KEY": "other-secret",
            "OPENAI_API_KEY": "agent-secret",
            "SILICONFLOW_API_KEY": "removed-provider-key",
            "SILICONFLOW_API_BASE_URL": "https://removed-provider.invalid/v1",
            "OPENROUTER_API_KEY": "allowed-openrouter-key",
            "JINA_API_KEY": "allowed-jina-key",
            "SAFE_VALUE": "kept",
        }
        with patch.dict(os.environ, values, clear=True):
            env = RUNNER.submission_env()
        self.assertEqual(env["SAFE_VALUE"], "kept")
        for key in (
            "API_KEY",
            "MODEL_API",
            "MODEL_NAME",
            "OTHER_API_KEY",
            "OPENAI_API_KEY",
            "SILICONFLOW_API_KEY",
            "SILICONFLOW_API_BASE_URL",
        ):
            self.assertNotIn(key, env)
        self.assertEqual(env["OPENROUTER_API_KEY"], "allowed-openrouter-key")
        self.assertEqual(env["JINA_API_KEY"], "allowed-jina-key")


if __name__ == "__main__":
    unittest.main()
