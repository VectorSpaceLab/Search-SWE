# Data and model provenance

The source is the [ChunQiuTR repository](https://github.com/xbdxwyh/ChunQiuTR)
at commit `392d6ec8d62de8256b3b45578f7b4484c22042ce`, associated with
[Wang et al., ChunQiuTR](https://aclanthology.org/2026.findings-acl.612/).

The upstream README licenses repository **code** under MIT. Its data notice
distinguishes the ancient works, generally public domain, from Chinese
Wikisource platform content and collaborative contributions under CC BY-SA 4.0.
Do not interpret the code license as blanket MIT relicensing of every passage.
This local derivative preserves the source texts and query wording, removes
synthetic no-event records, filters documented ambiguous queries, removes
no-event positives and replaces IDs. Original source attribution and any
applicable share-alike conditions continue to apply. Source-page attribution
and revision coverage must be reviewed before public redistribution; this
package has not been published to a dataset host.

The model is [Qwen/Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B),
whose model card declares Apache-2.0. Its fixed asset revision is
`97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`; model bytes are checked against the
repository's pinned manifest. The model is kept separate from the text data.
