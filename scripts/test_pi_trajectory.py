import json
import unittest
from unittest.mock import AsyncMock, patch

from harbor.models.trajectories.trajectory import Trajectory
from scripts.harbor_agents import PreinstalledPi, Pi
from scripts.pi_trajectory import convert_events


def stream(*messages):
    return "\n".join(json.dumps({"type": "message_end", "message": m}) for m in messages)


def with_session(text, session_id="pi-test-session"):
    return json.dumps({"type": "session", "id": session_id}) + "\n" + text


class PiTrajectoryTests(unittest.TestCase):
    def assert_preview_compatible(self, trajectory):
        # ATIF Preview 0.8.2 requires an identity even though Harbor v1.7 does not.
        exported = Trajectory.model_validate(trajectory).to_json_dict()
        self.assertIsInstance(exported["schema_version"], str)
        self.assertTrue(any(isinstance(exported.get(k), str) and exported[k]
                            for k in ("session_id", "trajectory_id")))
        self.assertIsInstance(exported["agent"], dict)
        self.assertIsInstance(exported["steps"], list)

    def test_native_session_identity_survives_export(self):
        text = with_session(stream({"role": "assistant", "content": [], "stopReason": "stop"}))
        trajectory, error = convert_events(text, "task", "model", "version")
        self.assertIsNone(error)
        self.assertEqual(trajectory["session_id"], "pi-test-session")
        self.assert_preview_compatible(trajectory)

    def test_missing_session_has_deterministic_document_identity(self):
        text = stream({"role": "assistant", "content": [], "stopReason": "error"})
        first, error = convert_events(text, "task", "m", "v")
        second, _ = convert_events(text, "task", "m", "v")
        other, _ = convert_events(text, "other task", "m", "v")
        self.assertIsNotNone(error)
        self.assertNotIn("session_id", first)
        self.assertEqual(first["trajectory_id"], second["trajectory_id"])
        self.assertNotEqual(first["trajectory_id"], other["trajectory_id"])
        self.assertIn("hash", first["notes"])
        self.assert_preview_compatible(first)

    def test_invalid_session_identity_uses_fallback(self):
        for session_id in (None, "", "  ", 42):
            with self.subTest(session_id=session_id):
                text = with_session(stream({"role": "assistant", "content": [], "stopReason": "stop"}), session_id)
                trajectory, _ = convert_events(text, "task", "m", "v")
                self.assertNotIn("session_id", trajectory)
                self.assert_preview_compatible(trajectory)

    def test_conflicting_session_headers_are_rejected(self):
        text = with_session(with_session("", "second-session"), "first-session")
        with self.assertRaisesRegex(ValueError, "multiple session IDs"):
            convert_events(text, "task", "m", "v")

    def test_cli_diagnostics_do_not_hide_session_identity(self):
        text = "CLI warning\nnull\n[]\n42\n" + with_session(stream(
            {"role": "assistant", "content": [], "stopReason": "stop"},
        ))
        trajectory, error = convert_events(text, "task", "m", "v")
        self.assertIsNone(error)
        self.assertEqual(trajectory["session_id"], "pi-test-session")
        self.assert_preview_compatible(trajectory)

    def test_does_not_prepend_instruction_when_real_user_message_exists(self):
        for prompt in ("task", "rendered task with runtime context"):
            with self.subTest(prompt=prompt):
                text = stream(
                    {"role": "user", "content": [{"type": "text", "text": prompt}]},
                    {"role": "assistant", "content": [{"type": "text", "text": "done"}], "stopReason": "stop"},
                )
                trajectory, _ = convert_events(text, "task", "m", "v")
                self.assertEqual(len(trajectory["steps"]), 2)
                self.assertEqual(trajectory["steps"][0]["message"], prompt)
                self.assertEqual([s["step_id"] for s in trajectory["steps"]], [1, 2])
                self.assert_preview_compatible(trajectory)

    def test_preserves_genuine_repeated_user_messages(self):
        user = {"role": "user", "content": "task"}
        text = stream(user, user, {"role": "assistant", "content": [], "stopReason": "stop"})
        trajectory, _ = convert_events(text, "task", "m", "v")
        self.assertEqual([s["source"] for s in trajectory["steps"]], ["user", "user", "agent"])

    def test_standard_reasoning_timestamp_and_usage(self):
        message = {
            "role": "assistant", "timestamp": 1700000000000,
            "provider": "deepseek", "model": "deepseek-flash",
            "content": [{"type": "thinking", "thinking": "consider the options"},
                        {"type": "text", "text": "answer"}],
            "usage": {"input": 11, "cacheRead": 7, "cacheWrite": 3, "output": 5,
                      "reasoning": 2, "cost": {"total": 0.025}},
            "stopReason": "stop",
        }
        trajectory, error = convert_events(stream(message), "task", "m", "v")
        step = trajectory["steps"][1]
        self.assertIsNone(error)
        self.assertEqual(step["message"], "answer")
        self.assertEqual(step["model_name"], "deepseek/deepseek-flash")
        self.assertEqual(step["reasoning_content"], "consider the options")
        self.assertEqual(step["timestamp"], "2023-11-14T22:13:20.000Z")
        self.assertEqual(step["metrics"], {"prompt_tokens": 21, "cached_tokens": 7,
                         "completion_tokens": 5, "cost_usd": 0.025,
                         "extra": {"reasoning_tokens": 2}})
        self.assertEqual(step["extra"]["pi_message"], message)
        self.assertEqual(trajectory["final_metrics"], {"total_steps": 2,
                         "total_prompt_tokens": 21, "total_cached_tokens": 7,
                         "total_completion_tokens": 5, "total_cost_usd": 0.025})
        self.assert_preview_compatible(trajectory)

    def test_zero_and_missing_usage_are_distinct(self):
        for usage in ({}, {"output": 0, "cost": {"total": 0}}):
            with self.subTest(usage=usage):
                message = {"role": "assistant", "content": [], "usage": usage, "stopReason": "stop"}
                trajectory, _ = convert_events(stream(message), "task", "m", "v")
                step = trajectory["steps"][1]
                if usage:
                    self.assertEqual(step["metrics"], {"completion_tokens": 0, "cost_usd": 0})
                else:
                    self.assertNotIn("metrics", step)
                self.assert_preview_compatible(trajectory)

    def test_tools_and_schema(self):
        text = stream(
            {"role": "assistant", "content": [{"type": "toolCall", "id": "a", "name": "bash", "arguments": {"command": "ls"}}], "stopReason": "toolUse"},
            {"role": "toolResult", "toolCallId": "a", "content": [{"type": "text", "text": "file"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "done"}], "stopReason": "stop"},
        )
        trajectory, error = convert_events(text, "task", "model", "version")
        Trajectory.model_validate(trajectory)
        self.assertIsNone(error)
        self.assertEqual(len(trajectory["steps"]), 3)
        self.assertEqual(trajectory["steps"][1]["message"], "")
        self.assertEqual(trajectory["steps"][1]["observation"]["results"][0]["content"], "file")

    def test_tool_result_retains_error_and_details(self):
        result = {"role": "toolResult", "toolCallId": "a", "content": [{"type": "text", "text": "failed"}],
                  "isError": True, "details": {"exitCode": 1}, "timestamp": 1700000000000}
        text = stream(
            {"role": "assistant", "content": [{"type": "toolCall", "id": "a", "name": "bash", "arguments": {}}], "stopReason": "toolUse"},
            result,
            {"role": "assistant", "content": [], "stopReason": "stop"},
        )
        trajectory, _ = convert_events(text, "task", "m", "v")
        observation = trajectory["steps"][1]["observation"]["results"][0]
        self.assertEqual(observation["extra"]["pi_message"], result)
        self.assert_preview_compatible(trajectory)

    def test_multimodal_content_preserves_image(self):
        image = {"type": "image", "mimeType": "image/png", "data": "AA=="}
        text = stream(
            {"role": "user", "content": [{"type": "text", "text": "look"}, image]},
            {"role": "assistant", "content": [], "stopReason": "stop"},
        )
        trajectory, _ = convert_events(text, "task", "m", "v")
        self.assertEqual(trajectory["steps"][0]["message"], [
            {"type": "text", "text": "look"},
            {"type": "image", "source": {"media_type": "image/png", "path": "data:image/png;base64,AA=="}},
        ])
        self.assert_preview_compatible(trajectory)

    def test_unknown_content_is_not_silently_dropped(self):
        part = {"type": "futureBlock", "value": "keep me"}
        text = stream({"role": "assistant", "content": [part], "stopReason": "stop"})
        trajectory, _ = convert_events(text, "task", "m", "v")
        self.assertIn("keep me", trajectory["steps"][1]["message"])
        self.assert_preview_compatible(trajectory)

    def test_terminal_error(self):
        _, error = convert_events(stream({"role": "assistant", "content": [], "stopReason": "error", "errorMessage": "Request timed out."}), "task", "m", "v")
        self.assertEqual(error, "Request timed out.")

    def test_recovered_error(self):
        _, error = convert_events(stream(
            {"role": "assistant", "content": [], "stopReason": "error"},
            {"role": "assistant", "content": [], "stopReason": "stop"},
        ), "task", "m", "v")
        self.assertIsNone(error)

    def test_empty_output_fails(self):
        trajectory, error = convert_events("diagnostic", "task", "m", "v")
        self.assertIsNotNone(error)
        self.assertEqual(trajectory["steps"][0]["message"], "task")
        self.assert_preview_compatible(trajectory)

    def test_retry_exhaustion_and_recovery(self):
        message = stream({"role": "assistant", "content": [], "stopReason": "stop"})
        failed = json.dumps({"type": "auto_retry_end", "success": False, "finalError": "timeout"})
        _, error = convert_events(failed + "\n" + message, "task", "m", "v")
        self.assertEqual(error, "timeout")
        recovered = json.dumps({"type": "auto_retry_end", "success": True})
        _, error = convert_events(failed + "\n" + recovered + "\n" + message, "task", "m", "v")
        self.assertIsNone(error)

    def test_unfinished_tool_turn_fails(self):
        text = stream({"role": "assistant", "content": [], "stopReason": "toolUse"})
        self.assertIsNotNone(convert_events(text, "task", "m", "v")[1])

    def test_orphan_tool_result_fails(self):
        with self.assertRaisesRegex(ValueError, "no matching call"):
            convert_events(stream({"role": "toolResult", "toolCallId": "unknown", "content": []}), "task", "m", "v")


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_exports_before_raising(self):
        agent = object.__new__(PreinstalledPi)
        agent.model_name = "deepseek/deepseek-flash"
        agent._upload_config_text = AsyncMock()
        environment = AsyncMock()

        async def download(remote, local):
            local.write_text(stream({"role": "assistant", "content": [], "stopReason": "error", "errorMessage": "timeout"}))

        environment.download_file.side_effect = download
        with patch.object(Pi, "run", new_callable=AsyncMock):
            with self.assertRaisesRegex(RuntimeError, "timeout"):
                await agent.run("task", environment, None)
        uploaded = agent._upload_config_text.call_args.kwargs
        self.assertEqual(uploaded["remote_path"], "/logs/agent/trajectory.json")
        Trajectory.model_validate_json(uploaded["content"])
        self.assertIsInstance(json.loads(uploaded["content"])["trajectory_id"], str)

    async def test_successful_export_preserves_session_identity(self):
        agent = object.__new__(PreinstalledPi)
        agent.model_name = "deepseek/deepseek-flash"
        agent._upload_config_text = AsyncMock()
        environment = AsyncMock()

        async def download(remote, local):
            local.write_text(with_session(stream(
                {"role": "user", "content": [{"type": "text", "text": "task"}]},
                {"role": "assistant", "content": [{"type": "text", "text": "done"}], "stopReason": "stop"},
            )))

        environment.download_file.side_effect = download
        with patch.object(Pi, "run", new_callable=AsyncMock):
            await agent.run("task", environment, None)
        exported = json.loads(agent._upload_config_text.call_args.kwargs["content"])
        self.assertEqual(exported["session_id"], "pi-test-session")
        self.assertEqual([s["message"] for s in exported["steps"]], ["task", "done"])
        Trajectory.model_validate(exported)


if __name__ == "__main__":
    unittest.main()
