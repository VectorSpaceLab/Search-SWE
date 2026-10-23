"""Query-independent features from supplied training text; optional base NLL cache.

The target pool is derived from text, without contamination labels. Any used
query gradient must be computed by the caller for the current request.
"""

import math
import re

import numpy as np

from token_contract import MAX_LENGTH, prompt_text


FEATURE_NAMES = ["log_target_frequency", "target_in_prompt", "log_answer_tokens", "visible_target",
                 "base_target_nll_mean", "base_target_nll_max", "trained_response_nll",
                 "query_gradient_similarity", "query_lexical_similarity"]


def entity_pattern(entity):
    return re.compile(r"(?<!\w)" + re.escape(entity.strip()) + r"(?!\w)", re.IGNORECASE)


def words(text):
    return set(re.findall(r"[a-z]+", text.lower()))


def target_positions(row, tokenizer, target):
    prompt_length = len(tokenizer.encode(prompt_text(row["instruction"], row["input"]),
                                         add_special_tokens=False))
    encoded = tokenizer(row["output"], add_special_tokens=False, return_offsets_mapping=True)
    available = max(0, MAX_LENGTH-prompt_length)
    offsets = encoded["offset_mapping"][:available]
    end_of_retained = max((b for a, b in offsets), default=0)
    matches = list(entity_pattern(target).finditer(row["output"]))
    positions = {prompt_length+i for match in matches if match.end() <= end_of_retained
                 for i, (a, b) in enumerate(offsets) if a < match.end() and b > match.start()}
    return sorted(positions), len(matches), len(encoded["input_ids"])


class TrainingFeatures:
    def __init__(self, rows, tokenizer, base_nll=None, trained_loss=None):
        self.rows = rows
        self.tokenizer = tokenizer
        self.base_nll = base_nll
        self.trained_loss = trained_loss
        self.pool_cache = {}
        self.row_words = [words(r["instruction"] + " " + r["input"] + " " + r["output"]) for r in rows]

    def pool(self, target):
        key = target.strip().casefold()
        if key in self.pool_cache:
            return self.pool_cache[key]
        pattern = entity_pattern(target)
        indices, features = [], []
        for index, row in enumerate(self.rows):
            if not pattern.search(row["output"]):
                continue
            positions, count, answer_length = target_positions(row, self.tokenizer, target)
            nll = self.base_nll[index, positions].astype(np.float32) if self.base_nll is not None and positions else np.array([0.])
            indices.append(index)
            features.append([math.log1p(count), float(bool(pattern.search(row["instruction"]+"\n"+row["input"]))),
                             math.log1p(answer_length), float(bool(positions)), float(nll.mean()), float(nll.max()),
                             float(self.trained_loss[index]) if self.trained_loss is not None else 0.])
        result = (np.array(indices, dtype=np.int64), np.array(features, dtype=np.float32).reshape(-1, 7))
        self.pool_cache[key] = result
        return result

    def query_features(self, query, gradient_scores=None):
        indices, fixed = self.pool(query["target_text"])
        query_words = words(query["instruction"]+" "+query["input"]+" "+query["generated_answer"])
        lexical = np.array([len(query_words & self.row_words[i]) / max(1, len(query_words | self.row_words[i]))
                            for i in indices], dtype=np.float32)
        gradients = np.array(gradient_scores[indices], dtype=np.float32) if gradient_scores is not None else np.zeros(len(indices), dtype=np.float32)
        return indices, np.column_stack([fixed, gradients, lexical])
