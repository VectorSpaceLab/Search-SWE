"""Exercise task environment builders without importing or running their graders."""

import ast
import inspect
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[2]
JAVA_HOME = "/opt/java/openjdk"
BUILDERS = {"submission_env", "child_env", "candidate_environment",
            "submission_command", "child_command"}


def environment_builders():
    for path in sorted((ROOT / "tasks").glob("*/tests/*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        functions = [node for node in tree.body
                     if isinstance(node, ast.FunctionDef) and node.name in BUILDERS]
        if not functions:
            continue
        namespace = {"os": os, "Path": Path, "INDEX": Path("/work/index"),
                     "INDEX_DIR": Path("/work/index"), "QUERY_PHASE": False}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in {
                        "AGENT_API_NAMES", "BUILD_API_NAMES", "ENV", "SUBMISSION_USER",
                    }:
                        namespace[target.id] = ast.literal_eval(node.value)
        # Loading just these functions avoids grader imports, data reads and setup.
        future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
        module = ast.fix_missing_locations(ast.Module(body=[future, *functions], type_ignores=[]))
        exec(compile(module, str(path), "exec"), namespace)
        for function in functions:
            yield path, namespace[function.name]


def submission_environment(function, query_phase):
    work = Path("/tmp/java-runtime-fixture")
    arguments = {"home": work, "index": work, "work": work, "runtime": work,
                 "cpu_ids": [0, 1], "allow_api": not query_phase, "answer": query_phase,
                 "command": ["/bin/true"]}
    function.__globals__["QUERY_PHASE"] = query_phase
    result = function(**{name: arguments[name] for name in inspect.signature(function).parameters})
    if isinstance(result, dict):
        return result
    # Command builders launch env -i after dropping privileges.
    environment = {}
    for argument in result[result.index("-i") + 1:]:
        if "=" not in argument:
            break
        key, value = argument.split("=", 1)
        environment[key] = value
    return environment


class SubmissionJavaTests(unittest.TestCase):
    def test_java_is_available_without_forwarding_private_credentials(self):
        builders = list(environment_builders())
        self.assertTrue(builders)
        parent = {"PATH": f"/opt/conda/bin:{JAVA_HOME}/bin:/usr/local/bin:/usr/bin:/bin",
                  "JAVA_HOME": "/unrelated-parent-java",
                  "OPENAI_API_KEY": "coding-fixture", "OPENAI_BASE_URL": "https://private.invalid",
                  "VERIFIER_OPENAI_API_KEY": "judge-fixture", "UNRELATED_SECRET": "private-fixture"}
        for path, function in builders:
            for query_phase in (False, True):
                with self.subTest(task=path.parent.parent.name, function=function.__name__,
                                  query_phase=query_phase), patch.dict(os.environ, parent, clear=True):
                    environment = submission_environment(function, query_phase)
                    self.assertEqual(environment["JAVA_HOME"], JAVA_HOME)
                    self.assertIn(f"{JAVA_HOME}/bin", environment["PATH"].split(":"))
                    for key in parent.keys() - {"PATH", "JAVA_HOME"}:
                        self.assertNotIn(key, environment)

    def test_budgeted_reranking_public_and_verifier_query_environments(self):
        task = ROOT / "tasks/budgeted-candidate-reranking"
        parent = {"JAVA_HOME": "/unrelated-parent-java", "PATH": "/parent/bin",
                  "OPENAI_API_KEY": "coding-fixture", "VERIFIER_OPENAI_API_KEY": "judge-fixture"}
        for phase in ("environment", "tests"):
            path = task / phase / "runtime/evaluate.py"
            tree = ast.parse(path.read_text(), filename=str(path))
            function = next(node for node in tree.body
                            if isinstance(node, ast.FunctionDef) and node.name == "run_query")
            namespace = {"Path": Mock(), "shutil": Mock(), "isolation": Mock(UID=10001),
                         "os": Mock(sched_getaffinity=Mock(return_value={0, 1})),
                         "time": time, "subprocess": Mock(PIPE=-1)}
            spawn = namespace["subprocess"].Popen
            spawn.side_effect = RuntimeError("fixture stopped before launch")
            # Exercise the actual query launcher without /work mutations, UID
            # changes, model imports or running a submitted command on the host.
            module = ast.Module(body=[function], type_ignores=[])
            exec(compile(module, str(path), "exec"), namespace)
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory, \
                    patch.dict(os.environ, parent, clear=True):
                output = Path(directory)
                report = namespace["run_query"]({"query_id": "fixture"}, output, None, output, Mock())
                self.assertEqual(report["error"], "fixture stopped before launch")
                spawn.assert_called_once()
                environment = spawn.call_args.kwargs["env"]
                self.assertEqual(environment["JAVA_HOME"], JAVA_HOME)
                self.assertIn(f"{JAVA_HOME}/bin", environment["PATH"].split(":"))
                self.assertEqual(environment["OMP_NUM_THREADS"], "2")
                self.assertEqual(environment["HOME"], "/work")
                self.assertNotIn("OPENAI_API_KEY", environment)
                self.assertNotIn("VERIFIER_OPENAI_API_KEY", environment)


if __name__ == "__main__":
    unittest.main()
