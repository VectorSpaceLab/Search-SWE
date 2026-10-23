# Methodology Inspiration Retrieval

Current run and release status (2026-10-23): [RUN_RESULTS.md](RUN_RESULTS.md). Earlier validation-stage statements are superseded by that dated record.

Build a working search engine that retrieves papers offering methodological
inspiration for a research problem and motivation. The solver receives a fixed
abstract collection, citation examples, Stella 400M, one A100 40GB and the
documented OpenRouter/Jina APIs. No implementation or training procedure is
required. Author: **Bingyu**.

## Package contract

| Item | Setting |
| --- | --- |
| Corpus | 4,851 distinct paper abstracts |
| Public examples | 19,613 original citation rows, 1,358 source groups |
| Hidden evaluation | 122 proposals, 187 positive query/paper pairs |
| Local model | `NovaSearch/stella_en_400M_v5`, official 1,024-dimensional projection |
| Compute | One A100 40GB, 16 CPU cores, 32 GiB RAM, 100 GiB storage |
| Development | 6 hours |
| Build and initialization | 1,200 seconds |
| Retrieval | 12 seconds for the entire batch, including API waiting and output |
| Output | Up to 3 ranked corpus IDs per query |

`build.sh` and `run.sh` follow the commands in `instruction.md`. The separate
verifier transfers `/app`, recreates an empty writable index, and runs submitted
code as UID 10001. Hidden queries are exposed only after initialization. Public
examples are available only during development. Source abstracts of test
proposals are absent from the public collection and examples.

Both images use the standard GPU base. `/opt/conda/bin/python` retains the
shared environment. `/opt/stella/bin/python` supplies an isolated Transformers
4.44.2 environment compatible with the original model's custom code, sharing
the base PyTorch installation. Model loading and readiness belong to the build
budget; initialization deferred to `run.sh` counts against the 12-second limit.

## Data and provenance

Source: [MIR: Methodology Inspiration Retrieval for Scientific Research Problems](https://aclanthology.org/2025.acl-long.1390/),
Garikaparthi et al., ACL 2025;
[official repository](https://github.com/Anikethh/Methodology-Inspiration-Retrieval),
commit `5a793828a6894856123819cefa637b3e21bd5477`.

The corpus is the fixed union of cited abstracts in the four published CSVs.
Nine malformed/non-abstract records were removed, five exact duplicate abstract
aliases were merged, and four test-source abstracts were excluded. No external
paper content, guessed title, citation path, or additional relevance label was
invented. The original 139 test proposals were reviewed before scoring: 15
clear citation-binding errors were excluded and two unresolved cases held out.
The retained proposal text and its complete positive set are unchanged apart
from exact duplicate alias mapping. This is an audited derivative, not a claim
to reproduce the paper's exact corpus construction or reported 49.34% result.

Public examples retain every field, duplicate row and label from the original
22,793-row augmented CSV, with **no quality filtering**. Only split isolation is
applied: 3,106 rows from 55 original test-source groups and 74 rows quoting a
test-source abstract as a cited abstract are excluded. The original train CSV
is already included in the augmented CSV and is not appended a second time.
Rows are citation contexts, not 19,613 independent research proposals. Original
development proposals are not shipped as an additional public split. Overlap
in cited target papers across training and test is allowed; test source papers
and test proposal text are isolated.

The public record fields remain those of the source CSV, including `proposal`,
`citation_text`, `intent`, `inspirational`, paper IDs and the two abstracts.
Unjudged corpus papers receive zero gain in the fixed evaluation; this does not
establish that every other paper is methodologically irrelevant. Labels are
not exhaustive human relevance judgments, and the examples are not claimed to
have passed the test-set content audit.

See [LICENSE.data.md](LICENSE.data.md) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). MIR's original contributions
are CC BY 4.0; MultiCite-derived material retains CC BY-NC 2.0 and paper content
retains its applicable source terms. The source does not supply a complete
per-paper redistribution license inventory. No blanket unrestricted license is
claimed. Stella's upstream model card declares MIT; its revision is
`ffeb2b7ee715c226d4ffe5e4619f7dbb48624c20`.

## Evaluation

For each query, `recall_q = |top3 ∩ positives_q| / |positives_q|`.
`Q` is the arithmetic mean over all 122 queries. Positive-set sizes are
1 for 74 queries, 2 for 37, 3 for 8 and 5 for 3. Consequently the attainable
mean Recall@3 is `U = mean(min(3, |positives_q|) / |positives_q|)` =
`0.9901639344262295`.

The user-approved fixed zero anchor is **B = 0.310109**. Deterministic quality
reward is `clip((Q - B) / (U - B), 0, 1)`. This preserves standard macro
Recall@3 while allowing an ideal Top-3 list for every query to earn full credit.
The source measurement was `0.3101092896174863` for untrained Stella without a
query prompt on this exact corpus/test set. Rounding the anchor to six decimal
places is intentional. The archived result is `models.stella_plain.recall3` in
`../../../task_development/methodology-inspiration-retrieval/research/stella400m-v1/screened-v2-results.json`.
Neither the published paper result nor a new trial score replaces this frozen
anchor.

Invalid build/output, a whole-batch timeout or a confirmed integrity violation
receives zero. A successful passing trajectory audit is required for final
reward; unavailable or failed judges never silently pass. The numerical
normalization is author/verifier information, not solver implementation advice.

## Authoring and release status

Construction scripts, source maps, review decisions, baseline implementations
and runtime evidence live in the sibling author workspace
`task_development/methodology-inspiration-retrieval/`, outside both task images.
`package_data.py` reconstructs the fixed inputs. `package-build/design.md`
records decisions; `package-build/input-inventory.json` fingerprints inputs;
`research/stella400m-v1/REPORT.txt` records the original audit and measurements.

Reviewed merged precedents at checkout
`46197a43f8cbb364e72b6d63d5db873ae7d2cac8` were
`tasks/reasoning-query-rewriting` (retrieval CLI, API policy, separate audit)
and `tasks/code-embedding-finetuning` (GPU and fixed local model assets).
The already exercised local `tasks/chunqiu-temporal-retrieval` supplied the
whole-batch process/isolation structure. MIR uses different inputs, model,
metric, normalization and deadlines. Fenced command examples follow the user's
preferred instruction style. No starter or reference solution is shipped.

Public inputs are published and pinned to immutable revisions in `assets.json`, with exact sizes and SHA-256 hashes. Unchanged model pins are retained. See [RUN_RESULTS.md](RUN_RESULTS.md) for the current run evidence and publication status. Existing source terms and attribution remain applicable.
