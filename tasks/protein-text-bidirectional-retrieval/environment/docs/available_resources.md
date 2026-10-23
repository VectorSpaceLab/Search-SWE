# Available resources

Use only supplied ESM-2 150M and BiomedBERT abstracts base models and the public
train/valid data. Freezing, fine-tuning, adapters, pooling, learned alignment,
sampling and custom encoder architectures are permitted. Each returned vector has64 dimensions; the scorer performs cosine ranking in separate trusted memory.
No external pretrained models, aligned features, additional data, teachers,
embedding/reranking/generation services or task API credentials are supplied.
Network access is disabled for task code. The coding agent's own phase-scoped
model connection is not a submission resource. Do not access hidden inputs,
reference solutions, test labels, verifier internals, timing controls or rewards.
Seeking hidden answers, caching unseen queries, test-time learning, inter-group
test-state transfer or prohibited resource use gives the entire task zero.

Swiss-Prot has 430,595 train pairs and ProteinKG25 422,315. Each public valid directory retains its original
10,000-candidate modality pools but exposes only 10 paired labels (20 pairs total).
The public tool checks 10 queries per direction per dataset; it is a small, noisy
diagnostic. You may build additional holdouts from the public train data. The two test pools each contain 10,000 official
pairs; they are isolated at runtime and are not a newly collected biological
benchmark. Exact sequence overlap across train/valid/test was checked globally
and is zero; 9,500 sequences are shared by the two test pools, which is why no
state can transfer across groups. Public descriptions may repeat across splits;
this is disclosed and does not imply hidden protein-to-description pair access.
No claim of homology-disjoint or novel-family generalization is made.

The entire final submission, including code and all frozen learned state, is
limited to 256 KiB (262,144 logical bytes across every file path). This is in
addition to the development storage allowance. Unchanged preinstalled bases remain outside the submission at `/task/models`; every copied submission file counts, including compressed payloads by their submitted logical file size.
