"""Protocol checks for the Antigravity OpenRouter bridge."""

from http.client import IncompleteRead
from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts.evaluation.agy_openrouter import GeminiHandler, gemini_response, openrouter_request


class AntigravityOpenRouterBridge(unittest.TestCase):
    def test_tool_response_and_reasoning_are_replayed_together(self):
        model = "google/gemini-4-argon"
        details = [{"type": "reasoning.encrypted", "format": "google-gemini-v1",
                    "data": "opaque", "id": "call_example", "index": 0}]
        call = {"id": "call_example", "type": "function",
                "function": {"name": "read_file", "arguments": '{"Path":"fixture.txt"}'}}
        response = gemini_response({
            "model": model, "choices": [{"finish_reason": "tool_calls", "message": {
                "content": None, "tool_calls": [call], "reasoning_details": details,
            }}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 10, "total_tokens": 22,
                      "completion_tokens_details": {"reasoning_tokens": 6}},
        })
        self.assertEqual(response["usageMetadata"]["candidatesTokenCount"], 4)
        request = {
            "systemInstruction": {"parts": [{"text": "Use the available tools."}]},
            "contents": [
                {"role": "user", "parts": [{"text": "Read the fixture."}]},
                response["candidates"][0]["content"],
                # The actual agy built-in model path uses model for tool results.
                {"role": "model", "parts": [{"functionResponse": {
                    "name": "read_file", "id": "call_example", "response": {"output": "fixture"},
                }}]},
            ],
            "generationConfig": {"maxOutputTokens": 8192, "thinkingConfig": {"thinkingLevel": "HIGH"}},
            "tools": [{"functionDeclarations": [{"name": "read_file", "parametersJsonSchema": {
                "type": "object", "properties": {"Path": {"type": "string"}},
            }}]}],
        }
        upstream = openrouter_request(request, model)
        self.assertEqual(upstream["model"], model)
        self.assertEqual(upstream["reasoning"], {"effort": "high"})
        self.assertEqual(upstream["max_tokens"], 8192)
        self.assertEqual(upstream["tools"][0]["function"]["parameters"]["type"], "object")
        self.assertEqual([m["role"] for m in upstream["messages"]], ["system", "user", "assistant", "tool"])
        self.assertEqual(upstream["messages"][2]["tool_calls"], [call])
        self.assertEqual(upstream["messages"][2]["reasoning_details"], details)
        self.assertEqual(upstream["messages"][3],
                         {"role": "tool", "tool_call_id": "call_example", "content": '{"output":"fixture"}'})

    def test_unmatched_tool_result_is_not_sent_as_a_user_message(self):
        request = {"contents": [{"role": "user", "parts": [
            {"functionResponse": {"id": "missing", "name": "read_file", "response": {}}},
        ]}]}
        with self.assertRaisesRegex(ValueError, "no matching call"):
            openrouter_request(request, "google/gemini-4-argon")

    def test_truncated_upstream_response_reports_bad_gateway(self):
        body = b'{"contents":[{"role":"user","parts":[{"text":"fixture"}]}]}'
        handler = GeminiHandler.__new__(GeminiHandler)
        handler.server = SimpleNamespace(model="google/gemini-4-argon", api_key="fixture", loopback_key="local")
        handler.path = "/v1beta/models/gemini-4-argon:streamGenerateContent"
        handler.headers = {"x-goog-api-key": "local", "Content-Length": str(len(body))}
        handler.rfile = BytesIO(body)
        handler.reply = Mock()
        with patch("scripts.evaluation.agy_openrouter.call_openrouter", side_effect=IncompleteRead(b"{}")):
            handler.do_POST()
        handler.reply.assert_called_once_with(502, {"error": {
            "code": 502, "message": "OpenRouter request or response failed (IncompleteRead)", "status": "BAD_GATEWAY",
        }})
