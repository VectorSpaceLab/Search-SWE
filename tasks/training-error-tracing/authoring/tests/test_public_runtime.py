"""CPU regression checks for the shared runtime and canonical starter."""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))


import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

TASK = TASK_ROOT
RUNTIME = TASK / "environment/runtime"
STARTER = TASK / "environment/starter"
sys.path.insert(0, str(RUNTIME))
sys.path.insert(0, str(STARTER))

import training_data
import retriever_service
import efficiency_grade
import grade


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Tokenizer:
    def __init__(self):
        self.tokens = {}

    def encode(self, text, **kwargs):
        return self(text)["input_ids"]

    def __call__(self, text, **kwargs):
        if isinstance(text, list):
            encoded = [self(value) for value in text]
            return {key: [row[key] for row in encoded] for key in encoded[0]}
        matches = list(re.finditer(r"[A-Za-z]+|[^\w\s]", text))
        ids = [self.tokens.setdefault(m.group(), len(self.tokens)) for m in matches]
        return {"input_ids": ids, "offset_mapping": [m.span() for m in matches]}

    def decode(self, ids):
        inverse = {value: key for key, value in self.tokens.items()}
        return " ".join(inverse[value] for value in ids)


class Inputs:
    def __init__(self, root):
        self.data = root / "data"
        self.models = root / "models"
        self.data.mkdir()
        (self.models / "base").mkdir(parents=True)
        self.tokenizer = Tokenizer()
        self.rows = [
            {"id": f"d{i:02d}", "instruction": "Astronomy nebula" if i < 12 else "Marine coral",
             "input": "", "output": "Lima is the answer."}
            for i in range(24)
        ]
        self.rows[0]["instruction"] += " telescope"
        (self.data / "train.jsonl").write_text("".join(json.dumps(r) + "\n" for r in self.rows))
        (self.models / "base/verified-manifest.json").write_text("{}\n")
        nll = np.zeros((24, 512), dtype=np.float16)
        alternatives = np.full((24, 512), -1, dtype=np.int32)
        alpha = self.tokenizer.encode("Alpha")[0]
        beta = self.tokenizer.encode("Beta")[0]
        for i, row in enumerate(self.rows):
            position = len(self.tokenizer.encode(training_data.prompt_text(row["instruction"])))
            nll[i, position] = 1 + i / 16
            alternatives[i, position] = alpha if i < 12 else beta
        for name, filename, values in [
            ("base-nll", "base-token-nll.npz", nll),
            ("base-alternatives", "base-token-alternatives.npz", alternatives),
        ]:
            directory = self.data / name
            directory.mkdir()
            np.savez(directory / filename, values=values)
            (directory / "row-ids.json").write_text(json.dumps([r["id"] for r in self.rows]))
        self.write_metadata()

    def write_metadata(self):
        common = {"training_sha256": digest(self.data / "train.jsonl"),
                  "base_manifest_sha256": digest(self.models / "base/verified-manifest.json")}
        nll_hash = digest(self.data / "base-nll/base-token-nll.npz")
        (self.data / "base-nll/complete.json").write_text(json.dumps({**common, "losses_sha256": nll_hash}))
        (self.data / "base-alternatives/complete.json").write_text(json.dumps({
            **common, "base_nll_sha256": nll_hash,
            "alternatives_sha256": digest(self.data / "base-alternatives/base-token-alternatives.npz"),
        }))


class PublicRuntime(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tracing-runtime-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = Inputs(self.root)
        patcher = patch.object(training_data.AutoTokenizer, "from_pretrained", return_value=self.inputs.tokenizer)
        patcher.start()
        self.addCleanup(patcher.stop)

    def load(self):
        return training_data.TrainingData(self.inputs.data, self.inputs.models)

    def test_loads_aligned_diagnostics(self):
        data = self.load()
        self.assertEqual(data.ids, [r["id"] for r in self.inputs.rows])
        self.assertEqual(data.base_nll.shape, (24, 512))
        self.assertEqual(data.alternatives.dtype, np.dtype("int32"))
        self.assertIsNone(data.trained_loss)

    def test_rejects_changed_training_corpus(self):
        with (self.inputs.data / "train.jsonl").open("a") as f:
            f.write(json.dumps(self.inputs.rows[0]) + "\n")
        with self.assertRaisesRegex(ValueError, "different training corpus"):
            self.load()

    def test_rejects_reordered_diagnostic_rows(self):
        p = self.inputs.data / "base-nll/row-ids.json"
        p.write_text(json.dumps(list(reversed(json.loads(p.read_text())))))
        with self.assertRaisesRegex(ValueError, "row IDs"):
            self.load()

    def test_rejects_wrong_alternative_dtype(self):
        p = self.inputs.data / "base-alternatives/base-token-alternatives.npz"
        np.savez(p, values=np.zeros((24, 512), dtype=np.float32))
        self.inputs.write_metadata()
        with self.assertRaisesRegex(ValueError, "shape or dtype"):
            self.load()

    def test_starter_lexical_and_fallback_rankings(self):
        with patch.object(retriever_service, "StreamedProbe"), \
                patch.object(retriever_service.TrainingRetriever, "_load_head"):
            retriever = retriever_service.TrainingRetriever(self.inputs.data, self.inputs.models, self.root / "index")
        query = {"id": "q", "instruction": "Astronomy nebula telescope", "input": "", "target_text": "Lima"}
        with patch.object(retriever, "_query_source_masses", side_effect=AssertionError("unexpected fallback")):
            self.assertEqual(retriever.rank(query)["ids"], ["d00"] + [f"d{i:02d}" for i in range(11, 2, -1)])
        query["instruction"] = "unseen vocabulary"
        with patch.object(retriever, "_query_source_masses", return_value={"alpha": .2, "beta": .8}):
            self.assertEqual(retriever.rank(query)["ids"], [f"d{i:02d}" for i in range(23, 13, -1)])

    def test_public_quality_cli_keeps_missing_queries(self):
        d = self.inputs.data
        (d / "dev-queries.jsonl").write_text(''.join(json.dumps({"id": q}) + "\n" for q in ["a", "b", "c"]))
        (d / "dev-labels.json").write_text(json.dumps({
            "first": {"query_ids": ["a", "b"], "record_ids": [f"d{i:02d}" for i in range(12)]},
            "second": {"query_ids": ["c"], "record_ids": [f"d{i:02d}" for i in range(12, 24)]},
        }))
        predictions = [{"query_id": "a", "ids": [f"d{i:02d}" for i in range(10)], "elapsed_sec": 1},
                       {"query_id": "c", "ids": [f"d{i:02d}" for i in range(12, 17)], "elapsed_sec": 1}]
        p = self.root / "predictions.jsonl"
        p.write_text(''.join(json.dumps(r) + "\n" for r in predictions))
        result = json.loads(subprocess.check_output([sys.executable, str(RUNTIME / "score_dev.py"),
                                                    "--data-dir", str(d), "--predictions", str(p)], text=True))
        self.assertEqual(result["Q"], .5)
        self.assertEqual(result["p5"], .75)

    @unittest.skipUnless(os.geteuid() == 0 and Path("/task/starter").exists(), "Run in the disposable task container")
    def test_runtime_and_starter_are_readable_by_submission_user(self):
        roots = [Path("/task") / name for name in ("runtime", "starter", "docs")]
        grade.verify_public_readability(roots)
        for root in roots:
            for path in [root, *root.rglob("*")]:
                self.assertEqual(path.stat().st_uid, 0)
                self.assertEqual(path.stat().st_mode & 0o222, 0)
                if path.is_file():
                    source = Path("/tests/public") / root.name / path.relative_to(root)
                    self.assertEqual(digest(path), digest(source))
        check = "import os; assert not os.access('/tests/public/starter', os.R_OK); assert not os.access('/tests/data/queries.jsonl', os.R_OK)"
        subprocess.run(["/usr/bin/setpriv", "--reuid=10001", "--regid=10001", "--clear-groups",
                        "--no-new-privs", sys.executable, "-c", check], check=True, timeout=10)

    @unittest.skipUnless(os.geteuid() == 0 and Path("/.dockerenv").exists(), "Run in the disposable task container")
    def test_missing_public_source_aborts_before_scoring(self):
        setup = (TASK / "tests/test.sh").read_text().split("\ncleanup() {", 1)[0]
        setup = setup.replace("/tests/public", str(self.root / "missing"))
        setup = setup.replace("/task/", str(self.root / "task") + "/")
        setup = setup.replace("/logs/verifier", str(self.root / "logs"))
        result = subprocess.run(["bash", "-c", setup], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertEqual((self.root / "logs/reward.txt").read_text(), "0\n")
        report = json.loads((self.root / "logs/reward-details.json").read_text())
        self.assertTrue(report["infrastructure_error"])
        self.assertEqual(report["reason"], "public input preparation failed")

    @unittest.skipUnless(os.geteuid() == 0 and Path("/task/starter").exists(), "Run in the disposable task container")
    def test_control_copy_is_independent_and_can_be_frozen(self):
        hashes = {p.name: digest(p) for p in Path("/task/starter").iterdir() if p.is_file()}
        control = efficiency_grade.prepare_control(self.root)
        self.assertEqual({p.name: digest(p) for p in control.iterdir()}, hashes)
        (control / "submission.json").write_text((control / "submission.json").read_text() + "\n")
        self.assertEqual({p.name: digest(p) for p in Path("/task/starter").iterdir()}, hashes)
        grade.lock_submission(control)
        grade.validate_submission_metadata(control)
        self.assertTrue(all(p.stat().st_mode & 0o222 == 0 for p in control.iterdir()))

    def test_starter_metadata_matches_runtime_and_source(self):
        config = json.loads((STARTER / "submission.json").read_text())["configuration"]
        self.assertEqual(config["runtime_sha256"], {p.name: digest(p) for p in RUNTIME.iterdir() if p.is_file()})
        self.assertEqual(config["submission_code_sha256"], {
            name: digest(STARTER / name) for name in ["prepare.sh", "run.sh", "retriever_service.py"]})

    def test_bundled_asset_contents_match_manifest(self):
        manifest = json.loads((TASK / "assets.json").read_text())
        for item in manifest["files"]:
            local = item["source"].get("local_path")
            if local:
                with self.subTest(path=local):
                    path = TASK / local
                    self.assertEqual(digest(path), item["sha256"])
                    self.assertEqual(path.stat().st_size, item["size_bytes"])


if __name__ == "__main__":
    unittest.main()
