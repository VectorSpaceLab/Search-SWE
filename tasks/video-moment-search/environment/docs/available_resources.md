# Available Resources

Network access is disabled. The supplied resources are video vectors, original text descriptions, public interval labels, fixed model weights and installed tools. No external model, video, dataset, embedding, reranking or generative API is available.

The video vectors were generated with CLIP ViT-B/32. The same fixed image and text encoder is available at `/task/models/clip/`. Feature files contain L2-normalized projected 512-dimensional frame vectors in float16 NumPy arrays. Load NumPy files with `allow_pickle=False`.

Video timing is defined by each record's supplied time-grid file, in seconds. Sampling intervals vary across records. Requests contain the original natural-language descriptions; no text vectors or tokenized descriptions are supplied.

Public interval labels may be used for the optional small temporal/scoring component. Keep its weights and runtime code under `/app`. Training and validation inputs are development resources; the indexing and retrieval runtime receives the corpus, fixed model and current queries.
