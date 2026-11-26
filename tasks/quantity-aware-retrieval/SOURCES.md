# Sources and Preparation

## Provenance and limitations

MedQuant and the underlying training material are from
[QuantityAwareRankers](https://github.com/satya77/QuantityAwareRankers), associated
with [Numbers Matter!](https://aclanthology.org/2024.findings-emnlp.707/).
[DeepQuant](https://aclanthology.org/2025.findings-acl.1220/) is the motivating
quantity-aware retrieval paper; this package does not claim to reproduce its
unreleased exact 150k MedQuant training split.

The benchmark ZIP SHA-256 is
`223fc8c7fcc6fded6a58a16c9d2bf3784c010568310b56355a0682956908e0c8`.
The generated training parent SHA-256 is
`80667d66bf0de233a6d4f0b112daa77c0b4b8f185d78c934642078a95cfef576`.
Generation reused the author functions at commit
`5d2c2e59c938fc816d1614d7cdc56763e54748ed`, with deterministic group seeds,
concept exclusion, deduplication and exact-pair conflict removal. No generation
API calls were made. Labels remain synthetic and noisy; training efficacy has
not been established by a 50k/80k ablation. Original positive-only evaluation
qrels can omit relevant passages. Units follow the source convention; physical
unit conversion or new multi-constraint semantics would require new labels.

[Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/tree/97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3)
is pinned to `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`. All ten installed model
files were independently checked against their manifest sizes and SHA-256.
The model card declares Apache-2.0. The enclosing repository's code license does
not establish redistribution rights for the MedQuant/training sources; those
terms remain unresolved and are recorded in the published source notices.
