"""Submitted-answer and model-transport boundary tests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import validate_answer, grade_answer, validate_recalled_notes
from llm_gateway import Gateway, ALLOWED_MODELS, OPENROUTER_ENDPOINT


class AnswerContractTests(unittest.TestCase):
    def test_retrieval_is_a_list_of_at_most_ten_strings(self):
        contract = {"max_retrieved_records": 10}
        for records in ([], ["a"], ["a"] * 10, ["evidence " * 500]):
            self.assertEqual(validate_recalled_notes(records, contract), records)
        for records in ({}, ["a"] * 11, [{"text": "a"}], [None], [1]):
            with self.assertRaises(ValueError):
                validate_recalled_notes(records, contract)

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
    def test_all_allowed_models_are_forwarded_without_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            response = unittest.mock.Mock(status_code=200)
            response.json.return_value = {"choices": [{"message": {"content": "reply"}}]}
            with Gateway("placeholder", 4, Path(d)/"api.json") as gateway, patch("llm_gateway.requests.post", return_value=response) as post:
                channel = gateway.worker.makefile("rwb")
                for model in ALLOWED_MODELS:
                    payload = {"model": model, "messages": [{"role":"user", "content":"current query"}]}
                    channel.write(json.dumps(payload).encode()+b"\n"); channel.flush()
                    self.assertIn("response", json.loads(channel.readline()))
                    self.assertEqual(post.call_args.args[0], OPENROUTER_ENDPOINT)
                    self.assertEqual(post.call_args.kwargs["json"]["model"], model)
                    self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer placeholder")
                    self.assertFalse(post.call_args.kwargs["allow_redirects"])
                channel.close()
                self.assertEqual(post.call_count, 4)

    def test_blank_api_key_fails(self):
        for key in ("", None):
            with self.subTest(key=key), self.assertRaises(Gateway.Error):
                Gateway(key, 1, Path("unused.json"))

    def test_disallowed_models_and_request_overrides_never_reach_provider(self):
        base = {"model": ALLOWED_MODELS[0], "messages": [{"role":"user", "content":"hello"}]}
        invalid = [dict(base, **change) for change in (
            {"model":"deepseek-flash"}, {"model":"qwen/qwen3.5-9b:free"},
            {"model":None}, {"model":[]}, {"model":"qwen/qwen3.5-9b "},
            {"base_url":"https://example.com"}, {"max_tokens":2001},
            {"tools":[]}, {"models":[ALLOWED_MODELS[0]]},
            {"provider":{}}, {"stream":True}, {"thinking":{"type":"enabled"}},
        )]
        invalid.append({"messages":base["messages"]})
        with tempfile.TemporaryDirectory() as d:
            with Gateway("placeholder", 2, Path(d)/"api.json") as gateway, patch.object(gateway, "forward") as forward:
                channel = gateway.worker.makefile("rwb")
                for payload in invalid:
                    with self.subTest(payload=payload):
                        channel.write(json.dumps(payload).encode()+b"\n"); channel.flush()
                        self.assertIn("error", json.loads(channel.readline()))
                channel.close()
                forward.assert_not_called()

    def test_transport_enforces_call_budget_across_model_choices(self):
        with tempfile.TemporaryDirectory() as d:
            with Gateway("placeholder", 1, Path(d)/"log.json") as gateway:
                with patch.object(gateway, "forward", return_value={"choices":[{"message":{"content":"generated"}}]}) as forward:
                    channel = gateway.worker.makefile("rwb")
                    for i, model in enumerate(ALLOWED_MODELS[:2]):
                        payload = {"model":model, "messages":[{"role":"user","content":"agent-designed prompt"}]}
                        channel.write(json.dumps(payload).encode()+b"\n"); channel.flush()
                        result = json.loads(channel.readline())
                        self.assertIn("response" if i == 0 else "error", result)
                    self.assertEqual(forward.call_count, 1)
                    channel.close()

    def test_documented_model_allowlist_matches_enforcement(self):
        import re
        task = Path(__file__).resolve().parent.parent
        text = (task/"environment/docs/available_resources.md").read_text()
        models = set(re.findall(r"^- `(qwen/[^`]+)`", text, re.M))
        self.assertEqual(set(ALLOWED_MODELS), models)


if __name__ == "__main__":
    unittest.main()
