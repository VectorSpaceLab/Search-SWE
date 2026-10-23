"""Fresh-query baseline features from the supplied fixed base and training text.

Alternative words come solely from training answers. This module contains no
country dictionary or source-target mapping, and never stores query results.
"""

import numpy as np
import torch

from source_coherence import token_surface

QUERY_SOURCE_FEATURE_NAMES = ["current_base_source_probability", "current_base_source_mode_match",
                              "current_source_word_match", "log_training_alternative_count"]


class QuerySourceFeatures:
    def __init__(self, retriever):
        if retriever.coherence is None or retriever.model is None:
            raise ValueError("Need fixed model and training-only alternative cache")
        self.retriever = retriever
        tokenizer = retriever.training.tokenizer
        size = retriever.model.config.vocab_size
        decoded = tokenizer.batch_decode([[i] for i in range(size)], skip_special_tokens=False,
                                         clean_up_tokenization_spaces=False)
        self.surface_indices = {}
        self.token_buckets = np.zeros(size, dtype=np.int64)
        for token_id, text in enumerate(decoded):
            surface = token_surface(text)
            if surface:
                bucket = self.surface_indices.setdefault(surface, len(self.surface_indices)+1)
                self.token_buckets[token_id] = bucket

