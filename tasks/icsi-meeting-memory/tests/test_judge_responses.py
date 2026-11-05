import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from harness import llm


class JudgeResponseTests(unittest.TestCase):
    def test_missing_final_content_retries_and_keeps_usage(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch.dict(
                "os.environ",
                {
                    "ANSWER_JUDGE_API_KEY": "test-key",
                    "ANSWER_JUDGE_BASE_URL": "https://openrouter.ai/api/v1",
                    "ANSWER_JUDGE_MODEL_NAME": "test/answer-judge",
                    "ICSI_JUDGE_USAGE_PATH": str(Path(d) / "usage.jsonl"),
                },
            ),
        ):
            responses = []
            for content, finish in [(None, "length"), ('{"correct":true}', "stop")]:
                r = Mock(status_code=200)
                r.json.return_value = {
                    "id": "response-" + finish,
                    "choices": [
                        {"message": {"content": content}, "finish_reason": finish}
                    ],
                    "usage": {"cost": 0.001},
                }
                responses.append(r)
            with (
                patch("harness.requests.post", side_effect=responses) as post,
                patch("harness.time.sleep"),
            ):
                value, meta = llm("Return JSON", {"question": "Question"})
            self.assertEqual(value, {"correct": True})
            self.assertEqual(meta["response_id"], "response-stop")
            self.assertEqual(
                post.call_args_list[0].kwargs["json"]["reasoning"], {"enabled": False}
            )
            self.assertEqual(post.call_args.kwargs["json"]["max_tokens"], 8192)
            logs = [
                json.loads(x)
                for x in (Path(d) / "usage.jsonl").read_text().splitlines()
            ]
            self.assertEqual(len(logs), 2)
            self.assertFalse(logs[0]["schema_valid"])
            self.assertTrue(logs[1]["schema_valid"])

    def test_judge_uses_configured_model_endpoint_and_credential(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch.dict("os.environ", {
                "ANSWER_JUDGE_API_KEY": "configured-test-key",
                "ANSWER_JUDGE_BASE_URL": "https://judge.example.test/v1/",
                "ANSWER_JUDGE_MODEL_NAME": "test/configured-judge",
                "ICSI_JUDGE_USAGE_PATH": str(Path(d) / "usage.jsonl"),
            }),
            patch("harness.requests.post") as post,
        ):
            post.return_value.status_code = 200
            post.return_value.json.return_value = {
                "choices": [{"message": {"content": '{"correct":true}'}, "finish_reason": "stop"}]
            }
            value, meta = llm("Return JSON", {"question": "Question"})
            self.assertEqual(value, {"correct": True})
            post.assert_called_once()
            self.assertEqual(post.call_args.args[0], "https://judge.example.test/v1/chat/completions")
            self.assertEqual(post.call_args.kwargs["json"]["model"], "test/configured-judge")
            self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer configured-test-key")
            self.assertEqual(meta["model"], "test/configured-judge")


if __name__ == "__main__":
    unittest.main()
