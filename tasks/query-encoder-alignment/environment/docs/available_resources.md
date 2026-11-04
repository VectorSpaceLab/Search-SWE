# Available Resources

Use the supplied local models and public data. No task API credentials or external retrieval, embedding, reranking, generation or answer services are provided or permitted, during training or final inference. The coding agent's own model connection is separate from the submitted retrieval system.

Development network access is limited to openrouter.ai and api.jina.ai; external task API calls remain prohibited. Final inference must run offline.

Qwen3-Embedding-0.6B is the required backbone. Qwen3-Embedding-4B is available for running the public time reference and local development, including teacher signals on public data. It is not an allowed final inference backbone and is inaccessible to the unprivileged final process. Do not copy it into a submission. Training and adaptation must use public inputs, never hidden queries, labels, precomputed answers or hard-coded query-to-document mappings. A detected violation of these resource or integrity rules makes the whole task score zero.
