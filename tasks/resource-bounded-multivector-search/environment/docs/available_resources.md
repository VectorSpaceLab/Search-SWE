# Available resources

The system uses only supplied ColBERTv2 FP32 corpus/query vectors, public development truth, public high-recall OPQ/IVFPQ baseline and exhaustive MaxSim tools, installed packages and local submission files. No internet, GPU, external models/datasets, retrieval API, generative API or additional credential is provided to the submitted program. Training a lightweight transformation on the supplied public data is optional and counts toward the same development budget.

The coding agent's own provider connection is a Harbor phase-scoped exception, not a submission API. Hidden queries, hidden exact neighbors, verifier code, rewards and host credentials are unavailable to submitted processes. No answer judge or trajectory model is needed: the score measures query-time improvement relative to the pinned high-recall baseline, measured in the same verification to correct machine-speed variation, with mean Recall@100 ≥ 0.99 and resource gates.
