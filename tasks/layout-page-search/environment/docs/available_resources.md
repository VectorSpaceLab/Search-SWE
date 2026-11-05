# Available Resources

Network access is disabled. The supplied resources are page images, extracted document text, public examples, model weights and installed tools. No external embedding, reranking, generation or search service is available.

ColQwen2.5 weights and processor are at `/task/models/page-encoder/`; the underlying retrieval backbone is at `/task/models/vision-backbone/`. The adapter configuration refers to that supplied directory. Model files are read-only. The encoders remain fixed; optional scoring or adaptation components may be trained using public examples within the task's overall time and resource limits.
