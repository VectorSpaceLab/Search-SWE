# Sources and transformation

Research motivation: [MaRF, ACL Findings 2026](https://aclanthology.org/2026.findings-acl.1277/), Task 2, and [author implementation](https://github.com/MLPgroup/MaRF). This package does not reproduce MaRF's GPU training or copy its reported scores. Formula-only input and the CPU/time budgets are Search-SWE design choices.

The [official ARQMath backup](https://www.cs.rit.edu/~dprl/ARQMath-backup/) is linked by the [ARQMath organizers](https://www.cs.rit.edu/~dprl/ARQMath/). Raw inputs:

- `Formulas/latex_representation_v3.zip`, complete 101 TSV shards, expanded size 1,917,108,571 bytes.
- `Collection/Posts.V1.3.zip`, complete annotated question/answer collection.
- `Topics/Task2 Topics/ARQMath-2/Topics/Topics_Task2_2021_V1.1.xml`.
- `Topics/Task2 Topics/ARQMath-3/Topics/Topics_Task2_2022_V0.1.xml`.
- `Evaluation/Updates in Visual Id and QRELs/Updated QREL Files/qrel_task2_a2_v3.tsv`: 58 assessed development topics, 8,115 visual judgments.
- `Evaluation/ Scripts & Qrels/ARQMath-3/Task2/Qrel Files/qrel_task2_2022_official.tsv`: 76 assessed test topics, 11,538 visual judgments. Preserve the entire file, including grade-zero judgments.

The file named `qrel_task2_2022_all.tsv` contains 86 topics, including additional/training topics. The organizers' `ReadMe.docx` explicitly identifies the 76-topic official file for evaluation. Therefore “complete test qrels” means the complete **official** file, not the file whose basename contains `all`.

Instances in comments and with issue flags containing `d` are excluded. Formulas in question titles belong to question posts and are retained. All valid instances are kept, including duplicate visual groups and corrected (`v`) visual IDs. Use the v3 visual-ID column, never `old_visual_id`. Original formula/post IDs and LaTeX are preserved. Thread IDs are normalized to the question's own ID or answer's ParentId in Posts v1.3; older TSV thread references sometimes precede thread migration. Candidate context retains HTML and formula span IDs; query XML is reduced to ID and LaTeX, without title, body or tags. Neither relevance labels nor positive coverage determine corpus inclusion or remove a query.

The original Math Stack Exchange posts are user content, with [CC BY-SA versions determined by contribution date](https://math.stackexchange.com/help/licensing): 2.5 before 2011-04-08, 3.0 until 2018-05-02, and 4.0 thereafter. Revisions can have different applicable licenses; do not infer a blanket license solely from post creation time. Retain original post IDs, owner user IDs and source attribution: `https://math.stackexchange.com/questions/POST_ID`, `https://math.stackexchange.com/users/OWNER_ID`, and each post's timeline. ARQMath annotation and qrel redistribution terms are not explicitly licensed in the downloaded README files; organizer guidelines describe noncommercial research access. Public availability alone is not a redistribution grant. Local research validation uses official downloads; publication requires resolving annotation/qrel redistribution and attribution, with no blanket Apache license applied to these assets.

See `source-manifest.json` for original source sizes/hashes and `assets.json` for the fixed converted inputs and restoration sources.

Posts v1.3 contains eight retained answer posts whose parent question is absent from that snapshot. Their own bodies and formula instances remain available; no parent content is invented and no additional corpus filtering is applied. This does not leave any 2022 official judged visual group without a valid instance.


The public split contains five labeled development queries. Sort the 58 official 2021 queries by `(LaTeX character length, query_id)`,
split into five equal-size quantile bands, then choose the minimum SHA256 of
`formula-dev-v020/QUERY_ID` within each band. This does not use labels or model
scores. Selected IDs: B.265, B.210, B.256, B.259, B.229; all 660 official judgments
for those queries remain, including the unreachable official B.229 visual group.
All 76 official 2022 queries and all 11,538 test judgments are used for final evaluation.
