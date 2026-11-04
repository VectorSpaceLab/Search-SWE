"""Read and validate fixed training inputs for the supplied retriever."""


import json
import re

import numpy as np
from transformers import AutoTokenizer


MAX_LENGTH = 512


def prompt_text(instruction, context=""):
    if context:
        return ("Below is an instruction that describes a task, paired with an input that provides further context. "
                "Write a response that appropriately completes the request.\n\n"
                f"### Instruction:\n{instruction}\n\n### Input:\n{context}\n\n### Response:\n")
    return ("Below is an instruction that describes a task. "
            "Write a response that appropriately completes the request.\n\n"
            f"### Instruction:\n{instruction}\n\n### Response:\n")


def entity_pattern(entity):
    return re.compile(r"(?<!\w)" + re.escape(entity.strip()) + r"(?!\w)", re.IGNORECASE)


def words(text):
    return set(re.findall(r"[a-z]+", text.lower()))


STOP_WORDS = set("a an and are as at be been being but by for from had has have he her his i if in is it its me my no not of on or our she so than that the their them there these they this those to was we were what when where which who will with you your".split())


def token_surface(text):
    text = text.strip().strip(".,;:!?()[]{}\"'`_-")
    if not re.fullmatch(r"[A-Za-z]{2,}", text) or text.casefold() in STOP_WORDS:
        return ""
    return text.casefold()


_STOP = set('\na an and are as at be been being but by can could did do does for from has have how i in is it its\nlocated many name of on or only present reply say state the their them there they this to what where\nwhich who why will with without world you your answer short question give just country using nothing\nelse national capital day identify containing associated location found home explanation island visit explain not s\ntravel would situated landmark place city cities\n'.split())


_WORDS = re.compile('[a-z0-9]+')


def _token_set(text):
    return set(_WORDS.findall(text.casefold())) - _STOP


def load_training_array(path):
    if path.suffix == ".npz":
        with np.load(path, allow_pickle=False) as packed:
            if packed.files != ["values"]:
                raise ValueError("Unexpected training feature archive")
            return packed["values"]
    return np.load(path, mmap_mode="r", allow_pickle=False)


def sha256(path):
    import hashlib
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


class TrainingData:
    """Load the corpus, tokenizer and aligned training-only diagnostic arrays."""

    def __init__(self, data_dir, model_dir):
        self.rows = [json.loads(line) for line in (data_dir / "train.jsonl").read_text().splitlines()]
        self.ids = [row["id"] for row in self.rows]
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir / "base", local_files_only=True)
        nll_path = data_dir / "base-nll/base-token-nll.npz"
        alternatives_path = data_dir / "base-alternatives/base-token-alternatives.npz"
        complete = json.loads((nll_path.parent / "complete.json").read_text())
        if complete["training_sha256"] != sha256(data_dir / "train.jsonl"):
            raise ValueError("Base token features belong to a different training corpus")
        if complete["base_manifest_sha256"] != sha256(model_dir / "base/verified-manifest.json"):
            raise ValueError("Base token features belong to a different base model")
        if (json.loads((nll_path.parent / "row-ids.json").read_text()) != self.ids
                or complete["losses_sha256"] != sha256(nll_path)):
            raise ValueError("Base token features have wrong row IDs or checksum")
        self.base_nll = load_training_array(nll_path)
        if self.base_nll.shape != (len(self.rows), MAX_LENGTH):
            raise ValueError("Invalid base token feature shape")
        complete = json.loads((alternatives_path.parent / "complete.json").read_text())
        if (complete["training_sha256"] != sha256(data_dir / "train.jsonl")
                or complete["base_manifest_sha256"] != sha256(model_dir / "base/verified-manifest.json")
                or complete["base_nll_sha256"] != sha256(nll_path)
                or complete["alternatives_sha256"] != sha256(alternatives_path)
                or json.loads((alternatives_path.parent / "row-ids.json").read_text()) != self.ids):
            raise ValueError("Base alternatives do not match training text, base, NLL cache or row IDs")
        self.alternatives = load_training_array(alternatives_path)
        if self.alternatives.shape != (len(self.ids), MAX_LENGTH) or self.alternatives.dtype != np.int32:
            raise ValueError("Invalid base alternatives shape or dtype")
        loss_path = data_dir / "train-response-loss.npy"
        self.trained_loss = np.load(loss_path, mmap_mode="r", allow_pickle=False) if loss_path.exists() else None
        if self.trained_loss is not None and (self.trained_loss.shape != (len(self.ids),)
                                             or not np.isfinite(self.trained_loss).all()):
            raise ValueError("Invalid training response loss features")
        self.row_words = [words(row["instruction"] + " " + row["input"] + " " + row["output"])
                          for row in self.rows]
