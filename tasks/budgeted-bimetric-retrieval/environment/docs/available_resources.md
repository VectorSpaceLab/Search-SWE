# Available Resources

Use the supplied document collection, local vectors, development oracle and installed runtime.

## Local resources

- `/task/public/corpus.parquet`: document collection and task-local document IDs.
- `/task/public/cheap.f32`: cheap document vectors.
- `/task/public/dev-queries.jsonl`: development questions and their cheap query vectors.
- `/task/public/dev-qrels.tsv`: development relevance labels.
- `/task/public/config.json`: representation details and fixed scoring references.

Read `/task/docs/environment.md` for the installed Python environment, packages and system tools. Treat `/task` as read-only.

## Development oracle

The development oracle is a separate container. Its only input beyond public data is the expensive document representation and the 500 development query representations. It has no test queries or test labels. It exposes a Unix-domain HTTP socket at `/run/oracle/oracle.sock`; there are no credentials or external endpoints. Import `call` from `/task/tools/oracle_client.py`.

`call('/begin', {'query_id': 'train-example'})` starts a session for a public development query (use its actual ID and ordinary JSON quotes). The response contains a `token`. Send `{'op':'score','token':token,'doc_ids':[... ]}` to `/score` within that session. The response preserves document order and reports `distances`, `used` and `remaining`. Every listed document costs one call, including duplicates. The limit is 20 and the session expires after two seconds. A session is global and sequential; simultaneous development clients are unsupported. A fresh public session may be started for another diagnostic run.

Final verification instead mediates score requests over the submission's stdin and stdout. It binds scores to the current hidden query and offers no reset, vector substitution, vector export or expensive full-corpus ANN operation. The expensive representation is private: do not access its files, bypass current-query/count controls, or access the verifier's labels, queries or reward files.

## Public tools and baselines

The optional baseline programs are under `/task/baseline`. `/task/tools/evaluate.py` exercises the public service and protocol. `/task/public/config.json` gives the supplied representations and fixed scoring references B and U. Inspect the baseline code for its implementation and command-line options.

## Data and representation

The corpus and public questions come from BEIR Natural Questions. Cheap vectors use TaylorAI/bge-micro-v2 (MIT); expensive vectors use Salesforce/SFR-Embedding-Mistral (CC BY-NC 4.0, research use). Corpus source terms are CC BY-SA 4.0. Task IDs are `doc{i}` in both matrices; `source_id` records the upstream ID. The supplied vectors define the task. The oracle computes Euclidean L2 using stored vectors converted to FP64. Use the supplied configuration for representation details. Source terms do not grant unrestricted redistribution of derived assets.

## Network and resource restrictions

No external retrieval, embedding or generative API, task API key, downloaded model or GPU is available. The development oracle is accessible only through the local socket described above. Use only the supplied inputs, permitted development parameters and installed runtime.
