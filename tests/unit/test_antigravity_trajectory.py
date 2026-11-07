"""Current-run Antigravity collection under coarse filesystem timestamps."""
import os
from pathlib import Path
import tempfile
import unittest

from scripts.evaluation.antigravity_trajectory import AntigravityTrajectory, capture, collect


class AntigravityCollection(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home with spaces"; self.home.mkdir()
        self.logs = self.root / "logs"; self.logs.mkdir()
        self.manifest = self.root / "before.json"
        self.timestamp = 1700000000000000000

    def transcript(self, name, content):
        path = self.home / ".gemini/antigravity-cli/brain" / name / ".system_generated/logs/transcript_full.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        os.utime(path, ns=(self.timestamp, self.timestamp))
        return path

    def test_new_session_is_collected_at_same_timestamp_as_existing_session(self):
        old = self.transcript("old", "old session")
        # Even a future timestamp on an old session must not select that session.
        os.utime(old, ns=(self.timestamp * 2, self.timestamp * 2))
        capture(self.home, self.logs, self.manifest)
        current = self.transcript("current", "current session")
        collect(self.home, self.logs, self.manifest)
        self.assertEqual((self.logs / "antigravity-cli.trajectory.jsonl").read_text(), current.read_text())
        self.assertFalse(self.manifest.exists())

    def test_same_size_update_with_same_inode_and_mtime_is_detected_by_content(self):
        current = self.transcript("current", "before")
        before = current.stat()
        capture(self.home, self.logs, self.manifest)
        current.write_text("after!")
        os.utime(current, ns=(self.timestamp, self.timestamp))
        after = current.stat()
        self.assertEqual((before.st_ino, before.st_size, before.st_mtime_ns),
                         (after.st_ino, after.st_size, after.st_mtime_ns))
        collect(self.home, self.logs, self.manifest)
        self.assertEqual((self.logs / "antigravity-cli.trajectory.jsonl").read_text(), "after!")

    def test_replaced_session_with_identical_contents_and_timestamp_is_new(self):
        current = self.transcript("current", "same bytes")
        before = current.stat()
        capture(self.home, self.logs, self.manifest)
        replacement = current.with_name("replacement")
        replacement.write_text(current.read_text())
        os.utime(replacement, ns=(self.timestamp, self.timestamp))
        replacement.replace(current)
        self.assertNotEqual(before.st_ino, current.stat().st_ino)
        collect(self.home, self.logs, self.manifest)
        self.assertEqual((self.logs / "antigravity-cli.trajectory.jsonl").read_text(), "same bytes")

    def test_unchanged_old_session_and_old_collected_outputs_are_not_reused(self):
        self.transcript("old", "old session")
        (self.logs / "antigravity-cli.trajectory.jsonl").write_text("previous run")
        capture(self.home, self.logs, self.manifest)
        collect(self.home, self.logs, self.manifest)
        self.assertEqual(list(self.logs.iterdir()), [])

    def test_legacy_json_fallback_and_current_transcript_priority(self):
        legacy = self.home / ".agy/antigravity-cli/tmp/session-old.json"
        legacy.parent.mkdir(parents=True)
        capture(self.home, self.logs, self.manifest)
        legacy.write_text('{"messages":[]}')
        collect(self.home, self.logs, self.manifest)
        self.assertEqual((self.logs / "antigravity-cli.trajectory.json").read_text(), legacy.read_text())
        capture(self.home, self.logs, self.manifest)
        legacy.write_text('{"messages":["updated"]}')
        self.transcript("new", "modern transcript")
        collect(self.home, self.logs, self.manifest)
        self.assertEqual((self.logs / "antigravity-cli.trajectory.jsonl").read_text(), "modern transcript")
        self.assertFalse((self.logs / "antigravity-cli.trajectory.json").exists())

    def test_sqlite_wal_change_collects_unchanged_database_and_sidecars(self):
        database = self.home / ".gemini/antigravity-cli/conversations/current.db"
        database.parent.mkdir(parents=True)
        database.write_bytes(b"database")
        wal, shm = Path(str(database) + "-wal"), Path(str(database) + "-shm")
        wal.write_bytes(b"old"); shm.write_bytes(b"shared")
        for path in (database, wal, shm):
            os.utime(path, ns=(self.timestamp, self.timestamp))
        capture(self.home, self.logs, self.manifest)
        wal.write_bytes(b"new")
        os.utime(wal, ns=(self.timestamp, self.timestamp))
        collect(self.home, self.logs, self.manifest)
        self.assertEqual((self.logs / "antigravity-conversation.db").read_bytes(), b"database")
        self.assertEqual((self.logs / "antigravity-conversation.db-wal").read_bytes(), b"new")
        self.assertEqual((self.logs / "antigravity-conversation.db-shm").read_bytes(), b"shared")

    def test_native_factory_uses_the_same_collector(self):
        from scripts.evaluation.native_agents import NativeAgent
        agent = NativeAgent(search_swe_native_name="antigravity-cli", logs_dir=self.logs,
                            model_name="gemini/gemini-2.5-flash", extra_env={"GEMINI_API_KEY": "fixture-no-api"})
        self.assertIsInstance(agent, AntigravityTrajectory)


if __name__ == "__main__":
    unittest.main()
