"""Submitted-answer and model-transport boundary tests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import validate_answer, grade_answer, validate_recalled_notes
from llm_gateway import Gateway


class AnswerContractTests(unittest.TestCase):
    def test_recall_does_not_impose_the_removed_memory_schema_limits(self):
        records = [{"id": "n" * 100, "text": "evidence " * 500, "custom_metadata": 7}]
        self.assertEqual(validate_recalled_notes(records, {"max_retrieved_records": 10}), records)
        with self.assertRaises(ValueError):
            validate_recalled_notes(records * 2, {"max_retrieved_records": 10})

    def test_plain_answer(self):
        self.assertEqual(validate_answer("They agreed.", {"max_answer_chars": 2000}), "They agreed.")

    def test_invalid_answer(self):
        for text in ("", "  ", None, "x" * 2001):
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_answer(text, {"max_answer_chars": 2000})

    def test_judge_scores_only_the_final_answer(self):
        with patch("harness.llm", return_value=({"correct": True}, {})) as llm:
            r = grade_answer({"query_id": "q", "question": "What?"}, {"answer": "yes", "criteria": ["yes"]}, {"answer": "my submitted answer"})
            self.assertTrue(r["correct"])
            self.assertEqual(llm.call_count, 3)
            payload = llm.call_args.args[1]
            self.assertEqual(set(payload), {"question", "reference", "criteria", "candidate"})
            self.assertEqual(payload["candidate"], "my submitted answer")


class GatewayTests(unittest.TestCase):
    def test_runtime_configuration_controls_endpoint_key_and_model(self):
        with tempfile.TemporaryDirectory() as d:
            gateway = Gateway("configured-placeholder", 1, Path(d)/"api.json", "https://answer.example/v1", "configured-model")
            response = unittest.mock.Mock(status_code=200)
            response.json.return_value = {"choices": [{"message": {"content": "reply"}}]}
            with gateway, patch("llm_gateway.requests.post", return_value=response) as post:
                payload = Gateway.validate({"messages": [{"role": "user", "content": "current query"}]}, gateway.model)
                gateway.forward(payload)
                self.assertEqual(post.call_args.args[0], "https://answer.example/v1/chat/completions")
                self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer configured-placeholder")
                self.assertEqual(post.call_args.kwargs["json"]["model"], "configured-model")

    def test_blank_runtime_configuration_fails(self):
        for key, url, model in (("", "https://answer.example", "m"), ("placeholder", "", "m"), ("placeholder", "https://answer.example", "")):
            with self.subTest(url=url, model=model), self.assertRaises(Gateway.Error):
                Gateway(key, 1, Path("unused.json"), url, model)

    def test_provider_and_request_restrictions(self):
        base = {"messages": [{"role": "user", "content": "hello"}]}
        self.assertEqual(Gateway.validate(base, "deepseek-flash")["model"], "deepseek-flash")
        for change in ({"model": "other"}, {"base_url": "https://example.com"}, {"max_tokens": 2001}, {"tools": []}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                Gateway.validate(dict(base, **change), "deepseek-flash")

    def test_transport_forwards_agent_prompt_and_enforces_call_budget(self):
        with tempfile.TemporaryDirectory() as d:
            with Gateway("unit-test-placeholder", 1, Path(d)/"log.json", "https://api.deepseek.com", "deepseek-flash") as gateway:
                with patch.object(gateway, "forward", return_value={"choices": [{"message": {"content": "generated"}}]}) as forward:
                    channel = gateway.worker.makefile("rwb")
                    payload = {"messages": [{"role": "user", "content": "agent-designed prompt"}]}
                    for i in range(2):
                        channel.write(json.dumps(payload).encode()+b"\n"); channel.flush()
                        result = json.loads(channel.readline())
                        self.assertIn("response" if i == 0 else "error", result)
                    self.assertEqual(forward.call_count, 1)
                    self.assertEqual(forward.call_args.args[0]["messages"], payload["messages"])
                    channel.close()


if __name__ == "__main__":
    unittest.main()
