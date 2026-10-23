"""Export measured curves without exposing query vectors or answer IDs."""
import csv
import json
from runtime_limits import REFERENCES
import os
from pathlib import Path


def export_curves(outputs, root):
    os.environ['MPLCONFIGDIR'] = str(root / '.matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    columns = ['dataset', 'stage', 'live_rows', 'recall', 'rss_bytes',
               'reference_live_rss_bytes', 'query_seconds', 'query_budget_seconds',
               'delete_seconds', 'storage_bytes', 'reported_edge_count',
               'reported_distance_computations']
    figure, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
    with (root / 'stage-metrics.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, columns, extrasaction='ignore')
        writer.writeheader()
        for row, name in enumerate(['sift', 'gist']):
            result = outputs[name]
            reference = REFERENCES[name]
            stages = result['stages']
            for stage in stages:
                writer.writerow(stage | {'dataset': name,
                    'reference_live_rss_bytes': reference['live_rss_bytes'][stage['stage'] - 1]})
            memory, latency = axes[row]
            memory.plot(range(1, 101), [v / (1 << 30) for v in reference['live_rss_bytes']],
                        color='gray', label='Rebuilt live HNSW reference')
            memory.axhline(reference['initial_rss_bytes'] / (1 << 30), color='gray',
                           linestyle=':', label='Full HNSW reference')
            points = [(s['stage'], s['rss_bytes']) for s in stages]
            if 'initial_calibration' in result:
                points.insert(0, (0, result['initial_calibration']['rss_bytes']))
            if points:
                memory.plot([t for t, _ in points], [v / (1 << 30) for _, v in points],
                            color='#1864ab', label='Submission query peak RSS')
            latency.plot(range(1, 101), [.2 * v for v in reference['full_scan_seconds']],
                         color='#d9480f', label='Stage time limit')
            if stages:
                latency.plot([s['stage'] for s in stages], [s['query_seconds'] for s in stages],
                             color='#1864ab', label='Submission')
            status = 'valid' if result['valid'] else 'failed; partial measurements'
            memory.set_title(f'{name.upper()}: {status}')
            memory.set_ylabel('RSS (GiB)')
            latency.set_title(f'{name.upper()}: complete query phase')
            latency.set_ylabel('Wall time (seconds)')
            for axis in [memory, latency]:
                axis.set_xlabel('Deletion stage')
                axis.grid(alpha=.2)
                axis.legend(fontsize=8)
    figure.savefig(root / 'resource-curves.png', dpi=160)
    plt.close(figure)
