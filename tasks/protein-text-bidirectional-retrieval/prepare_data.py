"""Author-only deterministic preparation from verified OSF version-1 archives.

Never copy this program, original archives, or private output into the agent image.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import zipfile

SOURCES = {
    'swissprot': ('SwissProtV3.zip', '2a8296d43549a2f55fedcf7b552474208aba28933322713c60736bf0ab5f97d1', 430595),
    'proteinkg25': ('proteinkg25.zip', 'b459a7f066127ed777cd35b0cc08042a2e3f46f1116ac21578a52c011633de6b', 422315),
}


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w') as out:
        for row in rows:
            out.write(json.dumps(row, separators=(',', ':')) + '\n')


def prepare(source, output, key):
    all_sequences = {'train': set(), 'valid': set(), 'test': set()}
    for dataset, (archive, expected, train_count) in SOURCES.items():
        path = source / archive
        with path.open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != expected:
                raise ValueError('Archive hash mismatch: ' + archive)
        with zipfile.ZipFile(path) as z:
            if z.testzip() is not None:
                raise ValueError('ZIP CRC failure')
            for member in z.infolist():
                if member.is_dir():
                    continue
                split = Path(member.filename).name.split('_')[0].split('.')[0]
                if split not in {'train', 'valid', 'test'}:
                    raise ValueError('Unexpected ZIP member')
                pairs = []
                for line in z.read(member).decode().splitlines():
                    p, t = json.loads(line) if dataset == 'swissprot' else line.split('\t')
                    if not p or not t.strip() or len(p) > 1022 or not p.isalpha() or not p.isupper():
                        raise ValueError('Unexpected original record')
                    pairs.append((p, t.strip()))
                if len(pairs) != (train_count if split == 'train' else 10000):
                    raise ValueError('Original record count mismatch')
                all_sequences[split].update(p for p, t in pairs)
                if split == 'train':
                    write_jsonl(output / 'public/train' / (dataset + '.jsonl'),
                                ({'sequence': p, 'text': t} for p, t in pairs))
                    continue
                base = output / ('private' if split == 'test' else 'public/valid') / dataset
                # With only ten valid labels, both IDs and permutations must be
                # opaque even to someone reading this public preparation code.
                split_key = (key if split == 'test' else hmac.new(
                    key, b'Search-SWE-protein-text-valid-v2', hashlib.sha256).digest())
                def token(tag, index):
                    return hmac.new(split_key, f'{dataset}:{tag}:{index}'.encode(), hashlib.sha256).hexdigest()
                ids = {side: [token(side, i)[:32] for i in range(len(pairs))] for side in ['protein', 'text']}
                for side, index in [('protein', 0), ('text', 1)]:
                    order = sorted(range(len(pairs)), key=lambda i: token('order-' + side, i))
                    if split == 'valid':
                        # Preserve the three already fixed raw warmups, without
                        # retaining the recoverable public permutation after them.
                        old_key = b'Search-SWE-protein-text-public-valid-v1'
                        warmups = sorted(range(len(pairs)), key=lambda i: hmac.new(
                            old_key, f'{dataset}:order-{side}:{i}'.encode(), hashlib.sha256).hexdigest())[:3]
                        order = warmups + [i for i in order if i not in warmups]
                    write_jsonl(base / (side + '.jsonl'), ({'id': ids[side][i], 'value': pairs[i][index]} for i in order))
                selected = range(len(pairs))
                if split == 'valid':
                    selected = sorted(selected, key=lambda i: hashlib.sha256(
                        f'protein-text-v020-validation:{dataset}:{ids["protein"][i]}'.encode()).digest())[:10]
                mapping = {'p2t': {ids['protein'][i]: ids['text'][i] for i in selected},
                           't2p': {ids['text'][i]: ids['protein'][i] for i in selected}}
                (base / 'pairs.json').write_text(json.dumps(mapping, separators=(',', ':')) + '\n')
    if any(all_sequences[a] & all_sequences[b] for a, b in [('train', 'valid'), ('train', 'test'), ('valid', 'test')]):
        raise ValueError('Cross-split sequence leakage')
    for path in output.rglob('*'):
        path.chmod(0o755 if path.is_dir() else 0o644)
    for path in (output / 'private').rglob('*'):
        path.chmod(0o700 if path.is_dir() else 0o600)
    (output / 'private').chmod(0o700)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--private-key-file', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source, args.output, args.private_key_file.read_bytes())
