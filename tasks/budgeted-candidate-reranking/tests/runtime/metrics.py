"""Linear-gain TREC nDCG; IDCG always uses complete judgments."""
import math


def ndcg(ids, judgments, k=10):
    gains = sorted(judgments.values(), reverse=True)[:k]
    ideal = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    actual = sum(judgments.get(d, 0) / math.log2(i + 2)
                 for i, d in enumerate(ids[:k]))
    return actual / ideal if ideal else 0.0


def validate_result(message, query):
    if set(message) != {'type', 'ids'} or message['type'] != 'result':
        raise ValueError('Expected {"type":"result","ids":[...]}')
    ids = message['ids']
    if not isinstance(ids, list) or len(ids) > 10 or any(type(d) is not str for d in ids):
        raise ValueError('ids must contain at most ten string IDs')
    if len(set(ids)) != len(ids) or not set(ids) <= {d['doc_id'] for d in query['candidates']}:
        raise ValueError('Duplicate or out-of-pool ID')
    return ids
