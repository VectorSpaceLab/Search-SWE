"""Select the median-time response from five independent serving runs."""
import math

REPEATS = 5
BUILD_TIMEOUT = 3600
LOAD_TIMEOUT = 120
WARMUP_TIMEOUT = 30
QUERY_TIMEOUT = 0.05
METRICS = ('ndcg_prime', 'map_prime', 'p_prime_10')


def successful(attempt):
    seconds = attempt.get('seconds')
    return (attempt.get('valid') is True and type(seconds) in (int, float)
            and math.isfinite(seconds) and 0 <= seconds <= QUERY_TIMEOUT)


def median_result(attempts):
    if len(attempts) != REPEATS:
        raise ValueError(f'Expected exactly {REPEATS} query attempts')
    ordered = sorted(enumerate(attempts), key=lambda item: (
        item[1]['seconds'] if successful(item[1]) else math.inf, item[0]))
    index, selected = ordered[REPEATS // 2]
    valid = successful(selected)
    return {
        **{metric: selected[metric] if valid else 0.0 for metric in METRICS},
        'valid': valid,
        'seconds': selected['seconds'] if valid else None,
        'median_repeat': index + 1,
        'successful_attempts': sum(successful(attempt) for attempt in attempts),
        'attempts': attempts,
    }
