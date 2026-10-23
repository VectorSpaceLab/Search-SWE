"""Fixed parameters for the current task contract."""

REFERENCE = {'status': 'frozen',
 'score_kind': 'high_recall_relative_speed_v1',
 'baseline_query_seconds': 91.68791509233415,
 'reference_query_seconds': 67.90060943178833,
 'minimum_recall': 0.99,
 'query_hard_timeout_seconds': 600,
 'baseline_hard_timeout_seconds': 600,
 'load_timeout_seconds': 120,
 'warmup_timeout_seconds': 30,
 'cpu_model': 'AMD EPYC 7742 64-Core Processor',
 'numpy': '2.5.2',
 'runtime_versions': {'faiss': '1.15.0',
                      'orjson': '3.12.0',
                      'psutil': '7.2.2',
                      'python': '3.12.14'}}
