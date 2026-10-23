"""Public-input chemistry experiment: normalize tautomers before fragment joining."""
import re

from rdkit import Chem
from rdkit.Chem.MolStandardize import rdMolStandardize

STICKY = {"U": 50, "Np": 51, "Pu": 52, "Am": 53}
ENUMERATOR = rdMolStandardize.TautomerEnumerator()


def canonical_fragment(smiles):
    molecule = Chem.MolFromSmiles(smiles)
    molecule = ENUMERATOR.Canonicalize(molecule)
    root = next(atom.GetIdx() for atom in molecule.GetAtoms() if atom.GetSymbol() not in STICKY)
    result = Chem.MolToSmiles(molecule, rootedAtAtom=root, canonical=True, isomericSmiles=True)
    for symbol, label in STICKY.items():
        token = "[" + symbol + "]"
        # A terminal attachment represented as a branch must become a ring
        # label on its parent, rather than an empty SMILES branch.
        result = re.sub(r"\([-:=#]?" + re.escape(token) + r"\)", "-%" + str(label), result)
        result = result.replace(token, "-%" + str(label))
    return result


def normalize_chunk(values):
    from rdkit import RDLogger
    RDLogger.DisableLog("rdApp.*")
    result = []
    for value in values:
        try:
            result.append(canonical_fragment(value))
        except RuntimeError:
            result.append(value.split(".")[0])
    return result


if __name__ == "__main__":
    import argparse, concurrent.futures, json, multiprocessing, os
    from pathlib import Path
    from library import Library
    parser = argparse.ArgumentParser()
    parser.add_argument("--library-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    values = Library(args.library_dir).dataset.synthon_smiles
    with concurrent.futures.ProcessPoolExecutor(max_workers=16,
            mp_context=multiprocessing.get_context("fork")) as pool:
        chunks = pool.map(normalize_chunk, (values[i:i+128] for i in range(0,len(values),128)))
        result = [value for chunk in chunks for value in chunk]
    Path(args.output).write_text(json.dumps(result)+"\n")
