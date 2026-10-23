# Fixed-input provenance

The task adapts protein/text retrieval from Zhiyuan Liu, An Zhang, Hao Fei,
Enzhi Zhang, Xiang Wang, Kenji Kawaguchi and Tat-Seng Chua, **ProtT3: Protein-to-Text
Generation for Text-based Protein Understanding**, ACL 2024, pp. 5949–5966,
DOI 10.18653/v1/2024.acl-long.324.
[Paper](https://aclanthology.org/2024.acl-long.324/),
[author repository](https://github.com/acharkq/ProtT3/tree/f427daca2cf94e7544354b03e777f853bcd6bdce),
[public data project](https://osf.io/23azs/).
No ProtT3 training code or trained alignment checkpoint is supplied to the solver.

## Paired data

| Dataset | Original source | Fixed original archive | Version |
| --- | --- | --- | --- |
| Swiss-Prot | UniProt/Swiss-Prot, processed by ProtT3 authors | [SwissProtV3.zip](https://osf.io/download/en2gu/) | OSF v1, created 2024-01-24 |
| ProteinKG25 | ProteinKG25 / Gene Ontology, processed by ProtT3 authors | [proteinkg25.zip](https://osf.io/download/jyw7p/) | OSF v1, created 2024-01-24 |

The original archive hashes are fixed in `prepare_data.py`.
`prepare_data.py` verifies archive hashes, CRC and records before derivation.
It preserves original train/valid/test candidate membership, uppercase sequences and
strips descriptions as in the author's loader. No records are removed and no
new relevance labels are invented. Description duplicates remain distinct strict
pairs. Train pairs retain both modalities; valid/test modalities are separated
with independent opaque IDs and row orders. The private test-ID construction
key is author-held and is not copied into either solver inputs or this repository.

Each derived file's exact bytes and runtime permissions are specified in
`assets.json`. Only `data/public` is mounted for the agent. `data/private` is mounted only for
the trusted scorer, with restricted permissions and inaccessible to submitted code.
Upstream test is public; this boundary is execution isolation, not new biological
samples or proof of homology-family generalization. No private biological data
or credentials are present.

The ProtT3 paper Appendix E states its processed datasets are released under
CC BY 4.0; OSF currently reports `node_license=null`. Preserve this discrepancy.
The paper identifies Swiss-Prot as CC BY 4.0, ProteinKG25 as MIT and its underlying
Gene Ontology source as CC BY 4.0. These are source attributions, not a newly
invented license or permission to publish. Review redistribution terms before
an authorized upload and retain original attribution. Original citation families
are Bairoch and Apweiler (Swiss-Prot), Zhang et al. (ProteinKG25), and Aleksander
et al. (Gene Ontology), as listed in the ProtT3 bibliography.

## Original base models

| Repository | Immutable HF revision | Terms reported by model card |
| --- | --- | --- |
| [facebook/esm2_t30_150M_UR50D](https://huggingface.co/facebook/esm2_t30_150M_UR50D/tree/a695f6045e2e32885fa60af20c13cb35398ce30c) | a695f6045e2e32885fa60af20c13cb35398ce30c | MIT |
| [microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract](https://huggingface.co/microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract/tree/d673b8835373c6fa116d6d8006b33d48734e305d) | d673b8835373c6fa116d6d8006b33d48734e305d | MIT |

BiomedBERT abstracts was previously named PubMedBERT abstracts; this is the
original biomedical-text base, without a protein/text alignment head. ESM-2 is
an original protein masked-language base. Preserve model cards and the BiomedBERT
LICENSE.md. The supplied files, exact sizes, SHA256 hashes and immutable upstream revisions are listed in `assets.json`.

## Task inputs and evaluation

Each public validation modality retains 10,000 candidates, with ten labeled
pairs per dataset (twenty total). IDs and row permutations are opaque; the
private derivation key is not supplied. The first three records per modality
are public warmups. Training pairs retain both modalities. Final evaluation
uses the fixed test pools and strict original pair correspondence.

The 64-dimensional encoder interface and reciprocal-top1 paired-success
objective are task adaptations. Directional accuracy and R@20 are diagnostics.
The score is 100 times the dataset-macro paired-success fraction. Duplicate
descriptions remain distinct strict pairs, so identical text does not guarantee
unique pair recovery. No additional biological generalization claim follows
from this task's execution boundary.
