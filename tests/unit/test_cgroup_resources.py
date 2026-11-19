"""Exercise cgroup layouts, evidence requirements and image-context copies."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from environments.cgroups import cgroup_resources as cg, v1_oom


ROOT = Path(__file__).resolve().parents[2]


class CgroupResourcesTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(self.enterContext(tempfile.TemporaryDirectory()))
        cg.controller.cache_clear()
        cg.Controller._require_v1_leaf.cache_clear()
        self.addCleanup(cg.controller.cache_clear)
        self.addCleanup(cg.Controller._require_v1_leaf.cache_clear)

    def put(self, **files):
        for name, value in files.items():
            (self.path / name).write_text(value + "\n")

    def resolve(self, membership, mountinfo, *names):
        original = cg._read

        def read(path):
            if path == Path("/proc/self/cgroup"):
                return membership
            if path == Path("/proc/self/mountinfo"):
                return mountinfo
            return original(path)

        with patch.object(cg, "_read", side_effect=read) as reads:
            result = [cg.controller(name) for name in names]
            self.assertIs(cg.controller(names[0]), result[0])
            self.assertEqual(reads.call_count, 2 * len(names))
            return result

    def test_v2_resolves_current_member_and_prefers_more_specific_mount(self):
        mounts = ("24 1 0:18 / /sys/fs/cgroup ro - cgroup2 cgroup ro\n"
                  f"35 1 0:18 /slice {self.path} ro - cgroup2 cgroup ro")
        memory, = self.resolve("0::/slice/task.scope", mounts, "memory")
        self.assertEqual(memory, cg.Controller(2, self.path / "task.scope"))

    def test_v1_resolves_legacy_and_hybrid_memberships_per_controller(self):
        mounts = ("17 1 0:12 / /sys/fs/cgroup/unified ro - cgroup2 cgroup rw\n"
                  "21 1 0:16 / /sys/fs/cgroup/cpu,cpuacct ro - cgroup cgroup rw,cpu,cpuacct\n"
                  "22 1 0:17 /docker/isolated /mnt/mem\\040space ro - cgroup cgroup rw,memory")
        cpu, memory = self.resolve("4:cpu,cpuacct:/docker/isolated\n"
                                   "5:memory:/docker/isolated\n0::/unified", mounts, "cpu", "memory")
        self.assertEqual(cpu, cg.Controller(1, Path("/sys/fs/cgroup/cpu,cpuacct/docker/isolated")))
        self.assertEqual(memory, cg.Controller(1, Path("/mnt/mem space")))

    def test_mount_for_a_different_group_is_not_a_fallback(self):
        mounts = "22 1 0:17 /docker/other /sys/fs/cgroup/memory ro - cgroup cgroup rw,memory"
        with self.assertRaisesRegex(cg.CgroupError, "No cgroup v1 mount covers memory"):
            self.resolve("5:memory:/docker/isolated", mounts, "memory")

    def test_v2_budget_current_peak_and_oom_are_separate(self):
        self.put(**{"cpu.max": "1600000 100000", "memory.max": str(16 << 30),
                    "memory.swap.max": "0", "memory.current": str(120 << 20),
                    "memory.peak": str(200 << 20), "memory.events": "oom 4\noom_kill 1"})
        controller = cg.Controller(2, self.path)
        self.assertEqual(controller.cpu_quota(), (1600000, 100000))
        self.assertEqual(controller.memory_limit(), 16 << 30)
        self.assertEqual(controller.swap_limit(), 0)
        self.assertEqual(controller.memory_charge(), 120 << 20)
        self.assertEqual(controller.memory_peak(), 200 << 20)
        self.assertEqual(controller.memory_events("oom", "oom_kill")[1], {"oom": 4, "oom_kill": 1})

    def test_v1_aggregate_counters_and_no_swap_evidence(self):
        self.put(**{"cpu.cfs_quota_us": "1600000", "cpu.cfs_period_us": "100000",
                    "memory.limit_in_bytes": str(16 << 30), "memory.memsw.limit_in_bytes": str(16 << 30),
                    "memory.stat": f"hierarchical_memory_limit {16 << 30}\nhierarchical_memsw_limit {16 << 30}",
                    "memory.usage_in_bytes": str(120 << 20), "memory.max_usage_in_bytes": str(200 << 20),
                    "memory.oom_control": "oom_kill_disable 0\nunder_oom 0\noom_kill 1",
                    "memory.failcnt": "4"})
        controller = cg.Controller(1, self.path)
        self.assertEqual(controller.cpu_quota(), (1600000, 100000))
        self.assertEqual(controller.memory_limit(), 16 << 30)
        self.assertEqual(controller.memory_charge(), 120 << 20)
        self.assertEqual(controller.memory_peak(), 200 << 20)
        self.assertEqual(controller.memory_events("oom_kill")[1]["oom_kill"], 1)
        with self.assertRaisesRegex(cg.CgroupError, "cumulative oom event count"):
            controller.memory_events("oom")
        no_swap = "Filename Type Size Used Priority\n"
        with patch.object(cg, "_read", return_value=no_swap) as read:
            self.assertEqual(controller.swap_limit(), 0)
            read.assert_called_once_with(Path("/proc/swaps"))
        with patch.object(cg, "_read", return_value=no_swap + "/swap file 512 0 -2\n"):
            with self.assertRaisesRegex(cg.CgroupError, "zero swap"):
                controller.swap_limit()

    def test_v1_local_kill_count_cannot_cover_child_cgroups(self):
        (self.path / "nested").mkdir()
        self.put(**{"memory.oom_control": "oom_kill 0"})
        with self.assertRaisesRegex(cg.CgroupError, "child cgroups"):
            cg.Controller(1, self.path).memory_events("oom_kill")

    def test_missing_diagnostics_and_unverifiable_limits(self):
        controller = cg.Controller(2, self.path)
        self.assertIsNone(controller.memory_peak())
        with self.assertRaisesRegex(cg.CgroupError, "memory.events"):
            controller.memory_events("oom_kill")
        self.put(**{"memory.events": "oom 1", "cpu.max": "max 100000",
                    "memory.max": "max", "memory.swap.max": "max"})
        self.assertEqual(controller.cpu_quota(), (None, 100000))
        self.assertIsNone(controller.memory_limit())
        self.assertIsNone(controller.swap_limit())
        with self.assertRaisesRegex(cg.CgroupError, "Missing oom_kill"):
            controller.memory_events("oom_kill")
        self.put(**{"cpu.max": "1600000 0", "memory.max": "broken", "memory.events": "oom_kill -1"})
        for read in (controller.cpu_quota, controller.memory_limit, controller.memory_events):
            with self.subTest(read=read), self.assertRaises(cg.CgroupError):
                read()
        with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            self.assertIsNone(controller.memory_peak())
            with self.assertRaisesRegex(cg.CgroupError, "denied"):
                controller.memory_limit()

    def test_v1_unlimited_sentinels(self):
        page = os.sysconf("SC_PAGE_SIZE")
        unlimited = (2**63 - 1) // page * page
        self.put(**{"memory.limit_in_bytes": str(unlimited),
                    "memory.stat": f"hierarchical_memory_limit {unlimited}",
                    "cpu.cfs_quota_us": "-1", "cpu.cfs_period_us": "100000"})
        controller = cg.Controller(1, self.path)
        self.assertIsNone(controller.memory_limit())
        self.assertEqual(controller.cpu_quota(), (None, 100000))

    def test_v1_effective_limit_includes_ancestors_and_combined_memory(self):
        memory = cg.Controller(1, self.path)
        self.put(**{"memory.limit_in_bytes": str(32 << 30)})
        for ram, combined, effective in ((16, None, 16), (32, 24, 24), (32, 64, 32)):
            with self.subTest(ram=ram, combined=combined):
                counters = [f"hierarchical_memory_limit {ram << 30}"]
                if combined is not None:
                    self.put(**{"memory.memsw.limit_in_bytes": str(64 << 30)})
                    counters.append(f"hierarchical_memsw_limit {combined << 30}")
                self.put(**{"memory.stat": "\n".join(counters)})
                self.assertEqual(memory.memory_limit(), effective << 30)
        for stats in ("rss 123", "hierarchical_memory_limit bad", "hierarchical_memory_limit 1",
                      "hierarchical_memory_limit 1\nhierarchical_memsw_limit 2\nhierarchical_memsw_limit 2"):
            with self.subTest(stats=stats), self.assertRaises(cg.CgroupError):
                self.put(**{"memory.stat": stats})
                memory.memory_limit()

    def test_environment_failure_marker(self):
        cg.write_resource_error(self.path, cg.CgroupError("Missing memory evidence"))
        status = json.loads((self.path / "cgroup-status.json").read_text())
        self.assertIs(status["measurement_valid"], False)
        self.assertEqual(status["failure_kind"], "cgroup_environment")
        self.assertEqual(status["error"], "Missing memory evidence")

    def test_v1_oom_interval_distinguishes_reclaim_local_oom_and_global_kill(self):
        def sample(hits, kills=0, events=0, parent=0, initial=0):
            return {"limit_hits": [0, hits], "oom_kill": kills, "observer": {
                "id": "watch", "events": events, "parent_events": parent, "initial_hits": [0, initial]}}
        start = sample(1, events=1, initial=1)
        # An earlier local OOM is outside Bimetric's interval but counts for Formula.
        self.assertFalse(v1_oom.violation(sample(5, events=1, initial=1), start, include_kills=False))
        self.assertTrue(v1_oom.violation(start, include_kills=True))
        self.assertTrue(v1_oom.violation(sample(5, events=2), start, include_kills=False))
        global_kill = sample(0, kills=1)
        self.assertFalse(v1_oom.violation(global_kill, sample(0), include_kills=False))
        self.assertTrue(v1_oom.violation(global_kill, include_kills=True))
        with self.assertRaises(cg.CgroupError):
            v1_oom.violation(sample(5, events=1, parent=1), sample(0), include_kills=False)
        with self.assertRaises(cg.CgroupError):
            v1_oom.violation(sample(5, initial=1), include_kills=True)

    def test_v1_without_observer_uses_only_provable_outcomes(self):
        memory = cg.Controller(1, self.path)
        self.put(**{"memory.failcnt": "0", "memory.oom_control": "oom_kill 0"})
        with patch.object(v1_oom, "SOCKET", str(self.path / "missing.sock")):
            start = v1_oom.snapshot(memory)
            self.assertEqual(start, {"limit_hits": [0, None], "oom_kill": 0, "observer": None})
            self.assertFalse(v1_oom.violation(start, include_kills=True))
            self.put(**{"memory.failcnt": "12"})
            with self.assertRaisesRegex(cg.CgroupError, "reclaim"):
                v1_oom.violation(v1_oom.snapshot(memory), start, include_kills=False)
            self.put(**{"memory.oom_control": "oom_kill 1"})
            self.assertTrue(v1_oom.violation(v1_oom.snapshot(memory), include_kills=True))
            self.put(**{"memory.memsw.failcnt": "invalid"})
            with self.assertRaises(cg.CgroupError):
                v1_oom.snapshot(memory)

    def test_v1_invalid_evidence_and_discontinuous_watch(self):
        watch = {"id": "first", "events": 0, "parent_events": 0, "initial_hits": [0, 0]}
        sample = {"limit_hits": [2, 0], "oom_kill": 0, "observer": watch}
        invalid = [None, {}, {**sample, "oom_kill": -1}, {**sample, "limit_hits": [None, None]},
                   {**sample, "observer": {"id": "truncated"}}]
        for record in invalid:
            with self.subTest(record=record), self.assertRaises(cg.CgroupError):
                v1_oom.violation(record, include_kills=True)
        with self.assertRaises(cg.CgroupError):
            v1_oom.violation({**sample, "limit_hits": [3, 0], "observer": {**watch, "id": "second"}},
                             sample, include_kills=False)
        with self.assertRaises(cg.CgroupError):
            v1_oom.violation({**sample, "limit_hits": [1, 0]}, sample, include_kills=False)

    def test_v1_monitor_packaged_for_both_required_task_phases(self):
        import yaml
        root = ROOT / "tasks"
        for context in ("budgeted-bimetric-retrieval/tests", "large-scale-formula-retrieval/environment",
                        "large-scale-formula-retrieval/tests"):
            with self.subTest(context=context):
                package = root / context
                self.assertEqual((package / "v1_oom.py").read_bytes(), Path(v1_oom.__file__).read_bytes())
                compose = yaml.safe_load((package / "docker-compose.yaml").read_text())
                self.assertIs(compose["x-search-swe"]["v1_oom_notifications"], True)

    def test_docker_context_copies_match_canonical_source(self):
        canonical = Path(cg.__file__).read_bytes()
        copies = [
            f"{task}/{phase}/runtime" for task in ("budgeted-candidate-reranking", "constrained-molecular-search")
            for phase in ("environment", "tests")
        ] + [
            "large-scale-formula-retrieval/environment", "large-scale-formula-retrieval/tests",
            "budgeted-bimetric-retrieval/tests", "memory-constrained-dense-retrieval/tests",
            "training-error-tracing/tests",
        ]
        for context in copies:
            with self.subTest(context=context):
                self.assertEqual((ROOT / "tasks" / context / "cgroup_resources.py").read_bytes(), canonical)


class V1OomLauncherTests(unittest.IsolatedAsyncioTestCase):
    async def test_mount_lifetime_and_v2_native_path(self):
        from unittest.mock import AsyncMock
        from scripts.evaluation import harbor_environments as envs

        for version, fail, opt_in in [(1, False, True), (1, True, True), (2, False, True), (1, False, False)]:
            with self.subTest(version=version, fail=fail, opt_in=opt_in), tempfile.TemporaryDirectory() as temp:
                env = object.__new__(envs.GpuDocker)
                env.environment_dir = Path(temp)
                env._mounts = []
                config = "x-search-swe: {v1_oom_notifications: true}" if opt_in else "services: {}"
                (env.environment_dir / "docker-compose.yaml").write_text(config)
                async def start(_force_build):
                    self.assertEqual(len(env._mounts), int(version == 1 and opt_in))
                    if env._mounts:
                        mount, = env._mounts
                        self.assertTrue(mount["read_only"])
                        path = Path(mount["source"])
                        self.assertTrue((path / "oom.sock").is_socket())
                        self.socket_path = path
                    if fail:
                        raise RuntimeError("build failed")
                with patch.object(envs, "controller", return_value=cg.Controller(version, env.environment_dir)), \
                        patch.object(envs.DockerEnvironment, "start", new=AsyncMock(side_effect=start)), \
                        patch.object(envs.DockerEnvironment, "stop", new=AsyncMock()):
                    if fail:
                        with self.assertRaisesRegex(RuntimeError, "build failed"):
                            await env.start(False)
                    else:
                        await env.start(False)
                        await env.stop(True)
                    self.assertFalse(env._mounts)
                    if version == 1 and opt_in:
                        self.assertFalse(self.socket_path.exists())
