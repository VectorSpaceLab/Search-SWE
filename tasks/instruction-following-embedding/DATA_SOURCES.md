# Processed public inputs

Only `data/train.jsonl` and `data/validation/dev-groups.json` are newly mirrored to the official Search-SWE dataset. Required corpora restore to `data/corpus/{robust04,core17,news21}.jsonl`; their source revisions and hashes, and the model asset pins, remain unchanged. The download manifest contains runtime inputs only. The hidden 84 groups and original news corpus text are not part of this upload.

| Local path | Bytes | SHA-256 |
| --- | ---: | --- |
| `data/train.jsonl` | 2230174 | `a5a0a679f6c98f99fe777f3f070918b6026d0308e0dca21892ea0a3b06b7d4af` |
| `data/validation/dev-groups.json` | 891279 | `7c002c8929ac455635aceaca72188ccd2856b10dbc1b110f9c6cc1864e16592e` |

## Training data

The source is [jhu-clsp/FollowIR-train at 545192353a0192e2ed0e0e4f1604ff8a231f8733](https://huggingface.co/datasets/jhu-clsp/FollowIR-train/tree/545192353a0192e2ed0e0e4f1604ff8a231f8733), whose dataset card declares Apache-2.0. It contains TREC queries/instructions and synthetic documents with relevance labels. The published training file excludes the previously audited overlapping topics, retaining 1,717 of 1,776 records. This revision preserves the exact processed bytes; it changes restoration, not training content. The Apache-2.0 license accompanies the mirrored data.

## Public validation data

The 20 existing public groups (10 Robust04, 4 Core17, 6 News21) retain their paired instructions, 1,000-candidate order, judgments and changed-document IDs byte for byte. The task-specific public selection is retained; no new split is made.

| Subset | Original source | Original revision | Equivalent MTEB release (MIT in its dataset card) |
| --- | --- | --- | --- |
| Robust04 | `jhu-clsp/robust04-instructions` | `a5a1c4fe2bc528ac12e83f8cdf82178da85d2f1d` | [mteb/Robust04InstructionRetrieval](https://huggingface.co/datasets/mteb/Robust04InstructionRetrieval/tree/0495a5cb69aa8fa5bca81bd56ac248911c19eeb6) |
| Core17 | `jhu-clsp/core17-instructions` | `e39ff896cf3efbbdeeb950e6bd7c79f266995b07` | [mteb/Core17InstructionRetrieval](https://huggingface.co/datasets/mteb/Core17InstructionRetrieval/tree/67d8733dd0691f08f34ed9dda5941578cba8d91c) |
| News21 | `jhu-clsp/news21-instructions` | `e0144086b45fe31ac125e9ac1a83b6a409bb6ca6` | [mteb/News21InstructionRetrieval](https://huggingface.co/datasets/mteb/News21InstructionRetrieval/tree/c6fffeb9cdd95c1ffa81c62c687b48b56352872b) |

The original pinned JHU evaluation cards do not declare a license tag. For redistribution review, all 20 groups were checked against the MIT-labelled MTEB releases above: query and instruction text, candidate membership, both relevance maps and changed-document membership match exactly. The original task's candidate ordering and serialization remain unchanged. The MIT notice applies to these evaluation annotations as declared by those releases; it is not an assertion that the original news collections have unrestricted licenses. No news passages are included in the new validation asset.

Attribution: Orion Weller, Benjamin Chang, Sean MacAvaney, Kyle Lo, Arman Cohan, Benjamin Van Durme, Dawn Lawrie and Luca Soldaini, [FollowIR: Evaluating and Teaching Information Retrieval Models to Follow Instructions](https://aclanthology.org/2025.naacl-long.597/), and the [MTEB contributors](https://github.com/embeddings-benchmark/mteb). The upstream dataset cards provide citation details. Search-SWE adds the public selection, pairing and deterministic serialization described above.
