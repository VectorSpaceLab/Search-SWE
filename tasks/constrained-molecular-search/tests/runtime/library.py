"""Public ordinal-ID mapping; follows the frozen author's CSLDataset order."""
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

from apex.dataset.csl_dataset import CSLDataset


class Library:
    def __init__(self, path):
        path = Path(path)
        self.dataset = CSLDataset(pd.read_parquet(path / "reactions.parquet"),
                                  pd.read_parquet(path / "synthons.parquet"),
                                  fast_smiles=True, synthon_torch_mol=False)
        self.tree = self.dataset.libtree
        self.shapes = [tuple(len(group) for group in reaction) for reaction in self.tree]
        self.offsets = np.concatenate(([0], np.cumsum([np.prod(shape) for shape in self.shapes]))).astype(np.int64)
        self.positions = [[{synthon: i for i, synthon in enumerate(group)} for group in reaction]
                          for reaction in self.tree]

    def __len__(self):
        return int(self.offsets[-1])

    def key_to_id(self, reaction_id, synthons):
        index = 0
        if len(synthons) != len(self.shapes[reaction_id]):
            raise ValueError("Wrong number of reaction components")
        for synthon, size, positions in zip(synthons, self.shapes[reaction_id], self.positions[reaction_id]):
            index = index * size + positions[synthon]
        return int(self.offsets[reaction_id] + index)

    def name_to_id(self, name):
        return self.key_to_id(*self.dataset.name2key(name))

    def id_to_name(self, index):
        return self.dataset.key2name(*self.id_to_key(index))

    def id_to_smiles(self, index):
        return self.dataset.key2smiles(*self.id_to_key(index))

    def id_to_key(self, index):
        if not 0 <= index < len(self):
            raise ValueError("Combination ID out of range")
        reaction = int(np.searchsorted(self.offsets, index, side="right") - 1)
        remainder = int(index - self.offsets[reaction])
        positions = []
        for size in reversed(self.shapes[reaction]):
            remainder, position = divmod(remainder, size)
            positions.append(position)
        synthons = tuple(group[position] for group, position in zip(self.tree[reaction], reversed(positions)))
        return reaction, synthons

    def iter_smiles(self, start_reaction=0, stop_reaction=None):
        stop_reaction = len(self.tree) if stop_reaction is None else stop_reaction
        fragments = [s.split(".")[0] for s in self.dataset.synthon_smiles]
        for reaction_id in range(start_reaction, stop_reaction):
            groups = self.tree[reaction_id]
            for components in itertools.product(*([fragments[i] for i in group] for group in groups)):
                yield ".".join(components)
