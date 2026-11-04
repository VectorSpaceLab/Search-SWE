
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))

import json
import unittest

from rewardkit_transport import with_stream_recovery


RECONNECT = (
    "Reconnecting... 1/5 (stream disconnected before completion: "
    "Transport error: network error: error decoding response body)"
)


class JudgeTransportRecoveryTests(unittest.TestCase):
    def metadata(self, events, error=RECONNECT, output='{"score": 1}'):
        raw = "\n".join(json.dumps(event) for event in events)
        original = lambda _self, _raw, _label: (
            output, {"input_tokens": 42}, "original-session.jsonl", [], error
        )
        return with_stream_recovery(original)(None, raw, "audit")

    def test_observed_reconnect_then_completion_preserves_decision_and_evidence(self):
        result = self.metadata([
            {"type": "error", "message": RECONNECT},
            {"type": "turn.completed", "usage": {"input_tokens": 741506}},
        ])
        self.assertIsNone(result[-1])
        self.assertEqual(result[:3], ('{"score": 1}', {"input_tokens": 42}, "original-session.jsonl"))
        self.assertIn(RECONNECT, result[3][0])

    def test_negative_judgment_is_not_changed(self):
        result = self.metadata([
            {"type": "error", "message": RECONNECT},
            {"type": "turn.completed"},
        ], output='{"score": 0}')
        self.assertEqual(result[0], '{"score": 0}')

    def test_unrecovered_disconnect_remains_failure(self):
        self.assertEqual(self.metadata([{"type": "error", "message": RECONNECT}])[-1], RECONNECT)

    def test_completion_before_disconnect_does_not_count(self):
        self.assertEqual(self.metadata([
            {"type": "turn.completed"}, {"type": "error", "message": RECONNECT},
        ])[-1], RECONNECT)

    def test_failed_or_unfinished_later_turn_remains_failure(self):
        for terminal in ["turn.failed", "turn.started"]:
            with self.subTest(terminal=terminal):
                self.assertEqual(self.metadata([
                    {"type": "error", "message": RECONNECT},
                    {"type": "turn.completed"}, {"type": terminal},
                ])[-1], RECONNECT)

    def test_unrelated_error_is_not_cleared_by_completion(self):
        for other in ["authentication failed", "rate limit exceeded"]:
            with self.subTest(error=other):
                self.assertEqual(self.metadata([
                    {"type": "error", "message": other},
                    {"type": "error", "message": RECONNECT},
                    {"type": "turn.completed"},
                ])[-1], RECONNECT)

    def test_backend_error_must_match_recovered_event(self):
        result = self.metadata([
            {"type": "error", "message": RECONNECT}, {"type": "turn.completed"},
        ], error="process failure")
        self.assertEqual(result[-1], "process failure")

    def test_clean_success_is_unchanged(self):
        result = self.metadata([{"type": "turn.completed"}], error=None)
        self.assertIsNone(result[-1])
        self.assertEqual(result[3], [])


if __name__ == "__main__":
    unittest.main()
