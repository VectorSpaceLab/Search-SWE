"""Fixed-per-entity baselines from training-only base-token alternatives.

Each training answer contributes the base's alternative at its most surprising
target token. Repeated alternatives are evidence of a common source entity.
The rankings use no query text, gradients, labels, or entity-pair tables.
"""

from collections import Counter
import re

import numpy as np

from candidate_features import target_positions, words

SOURCE_MIN_SUPPORT = 3


STOP_WORDS = set("a an and are as at be been being but by for from had has have he her his i if in is it its me my no not of on or our she so than that the their them there these they this those to was we were what when where which who will with you your".split())


def token_surface(text):
    text = text.strip().strip(".,;:!?()[]{}\"'`_-")
    if not re.fullmatch(r"[A-Za-z]{2,}", text) or text.casefold() in STOP_WORDS:
        return ""
    return text.casefold()


class SourceCoherence:
    def __init__(self, training, alternatives):
        self.training = training
        self.alternatives = alternatives
        self.cache = {}
        self.decoded = {}

    def pool(self, target):
        key = target.strip().casefold()
        if key in self.cache:
            return self.cache[key]
        indices, fixed = self.training.pool(target)
        surfaces = []
        for index in indices:
            positions, _, _ = target_positions(self.training.rows[index], self.training.tokenizer, target)
            surface = ""
            if positions:
                nll = self.training.base_nll[index, positions]
                position = positions[int(np.argmax(nll))]
                token_id = int(self.alternatives[index, position])
                if token_id >= 0:
                    if token_id not in self.decoded:
                        self.decoded[token_id] = token_surface(self.training.tokenizer.decode([token_id]))
                    surface = self.decoded[token_id]
            surfaces.append(surface)
        counts = Counter(s for s in surfaces if s)
        mode = min(counts, key=lambda s: (-counts[s], s)) if counts else None
        frequency = np.array([np.log1p(counts[s]) if s else -1e6 for s in surfaces])
        mode_match = np.array([float(bool(s) and s == mode) for s in surfaces])
        result = {"indices": indices, "surfaces": surfaces, "counts": dict(counts),
                  "mode": mode,
                  "source-mode": mode_match*1e6 + fixed[:, 5] - (1-fixed[:, 3])*1e7,
                  "source-frequency": frequency + .1*fixed[:, 5] - (1-fixed[:, 3])*1e7}
        self.cache[key] = result
        return result

    def context_features(self, query):
        pool = self.pool(query["target_text"])
        query_words = words(query["instruction"]+" "+query["input"])
        features = np.asarray([[float(bool(s) and s in query_words), np.log1p(pool["counts"].get(s, 0))]
                               for s in pool["surfaces"]], dtype=np.float32).reshape(-1, 2)
        return pool["indices"], features

    @staticmethod
    def lexical_scores(context, base_target_nll):
        supported = context[:, 0]*(context[:, 1] >= np.log1p(SOURCE_MIN_SUPPORT)-1e-6)
        score = supported*1e6 + context[:, 1]*1e3 + base_target_nll
        return score, bool(supported.any())
