# Third-party materials

This local task is Built with Llama.

- **Llama 3.2 1B**, Meta: original model revision
  `4e20de362430cd3b72f300e6b0f18e50e7166e08`.
  [Original model](https://huggingface.co/meta-llama/Llama-3.2-1B).
  The model's Llama 3.2 Community License and Acceptable Use Policy are retained
  in `models/Llama-3.2-1B/LICENSE.txt` and `USE_POLICY.md`. They are separate from
  the repository's software license. The weights were obtained from the
  [ModelScope LLM-Research mirror](https://modelscope.cn/models/LLM-Research/Llama-3.2-1B)
  and verified against the original Hugging Face LFS pointer. No author-trained
  retrieval adapter is supplied to the agent.
- **LightRetriever fine-tuning data**, Guangyuan Ma et al., revision
  `840793a0229ead35a9c820e9803092c3f1383e07`:
  [author release](https://huggingface.co/datasets/lightretriever/lightretriever-finetune-data).
  Its dataset card declares Apache-2.0. The 80,000 examples are a sampled
  derivative of the original 23-source experiment configuration. Original
  query, positive-passage and negative-passage contents are preserved. The
  upstream collections retain their respective rights and attribution
  requirements; the author's aggregate license does not replace those rights.
- **BEIR-formatted SciFact, NFCorpus and FiQA**:
  [SciFact](https://huggingface.co/datasets/BeIR/scifact),
  [NFCorpus](https://huggingface.co/datasets/BeIR/nfcorpus), and
  [FiQA](https://huggingface.co/datasets/BeIR/fiqa).
  These BEIR release cards declare CC-BY-SA-4.0. Preserve that license and the
  original dataset attributions for the derived corpus and evaluation records.
  Transformations are ID renaming and anonymous collection tags; original text, candidate
  universes, split membership and relevance grades are retained.

The original datasets are SciFact (Wadden et al., 2020), NFCorpus (Boteva et al.,
2016), and FiQA (Maia et al., 2018), distributed for retrieval evaluation by
BEIR (Thakur et al., 2021). This task does not introduce new relevance labels.

The public corpus and example files are published in `search-swe/Search-SWE`
at revision `ff16485accd6d258610c158fce45e36b50a47c3f`; see the task asset
manifest and the official dataset provenance. Model files remain pinned to the
original gated upstream repository. Publication does not replace source terms.
