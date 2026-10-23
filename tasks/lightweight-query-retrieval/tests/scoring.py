"""Original graded nDCG@10, a quality gate, and linear runtime scoring.

The task sets fast_seconds=0 and slow_seconds=0.8: full credit is a
theoretical zero-runtime limit, with no positive-runtime full-credit interval.
"""
import json
import math


class VerificationError(ValueError):
    pass


def strict_json(text):
    def pairs(items):
        output = {}
        for key, value in items:
            if key in output:
                raise VerificationError(f"Duplicate JSON key: {key}")
            output[key] = value
        return output

    def nonfinite(value):
        raise VerificationError(f"Nonfinite JSON value: {value}")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)


def validate_response(response, queries, corpus):
    if not isinstance(response, dict) or not isinstance(response.get("results"), list):
        raise VerificationError("Expected an object containing a results list")
    expected = {q["query_id"]: q for q in queries}
    if len(expected) != len(queries) or len(response["results"]) != len(queries):
        raise VerificationError("Query coverage mismatch")
    predictions = {}
    for row in response["results"]:
        if not isinstance(row, dict) or not isinstance(row.get("query_id"), str):
            raise VerificationError("Invalid query ID")
        qid = row["query_id"]
        if qid not in expected or qid in predictions:
            raise VerificationError("Unknown or duplicate query ID")
        results = row.get("results")
        if not isinstance(results, list) or len(results) > 10:
            raise VerificationError("Return at most ten documents per query")
        seen, previous = [], None
        for item in results:
            if not isinstance(item, dict):
                raise VerificationError("Invalid document result")
            doc_id, score = item.get("doc_id"), item.get("score")
            if not isinstance(doc_id, str) or doc_id not in corpus or doc_id in seen:
                raise VerificationError("Unknown or duplicate document ID")
            collection, _ = corpus[doc_id]
            if collection != expected[qid]["collection"]:
                raise VerificationError("Document belongs to another collection")
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise VerificationError("Score must be a finite number")
            try:
                score = float(score)
            except (OverflowError, ValueError) as exc:
                raise VerificationError("Nonfinite score") from exc
            if not math.isfinite(score):
                raise VerificationError("Nonfinite score")
            if previous is not None and score > previous:
                raise VerificationError("Results must be score-descending")
            previous = score
            seen.append(doc_id)
        predictions[qid] = seen
    if predictions.keys() != expected.keys():
        raise VerificationError("Missing query output")
    return predictions


def ndcg_at_10(prediction, relevance):
    if not relevance or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in relevance.values()):
        raise VerificationError("Invalid reference relevance grades")
    # trec_eval / BEIR ndcg_cut uses the qrel value as the gain, not 2**grade-1.
    ideal = math.fsum(g / math.log2(i+2) for i, g in enumerate(sorted(relevance.values(), reverse=True)[:10]))
    actual = math.fsum(relevance.get(d, 0) / math.log2(i+2) for i, d in enumerate(prediction[:10]))
    return actual / ideal


def quality(predictions, gold):
    if not gold or predictions.keys() != gold.keys():
        raise VerificationError("Prediction/reference coverage mismatch")
    groups, detail = {}, []
    for qid, row in gold.items():
        value = ndcg_at_10(predictions[qid], row["relevance"])
        groups.setdefault(row["collection"], []).append(value)
        detail.append({"query_id": qid, "collection": row["collection"], "ndcg_at_10": value})
    means = {name: math.fsum(values)/len(values) for name, values in groups.items()}
    return math.fsum(means.values())/len(means), means, detail


def speed_reward(q, seconds, minimum_quality, fast_seconds, slow_seconds):
    values = (q, seconds, minimum_quality, fast_seconds, slow_seconds)
    if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in values):
        raise VerificationError("Invalid quality or timing")
    if not 0 <= q <= 1+1e-12 or not 0 < minimum_quality <= 1 or not 0 <= fast_seconds < slow_seconds or seconds < 0:
        raise VerificationError("Invalid scoring bounds")
    if q < minimum_quality:
        return 0.0
    return max(0.0, min(1.0, (slow_seconds-seconds)/(slow_seconds-fast_seconds)))
