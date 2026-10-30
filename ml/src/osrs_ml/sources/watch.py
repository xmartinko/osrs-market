"""Small forward-only v2 research poll, including a catch-up window."""
from .wiki import BASE, bulk


def run(client, root, mapping):
    results = []
    for resolution, step, hours in [('5m', 300, 1), ('1h', 3600, 24)]:
        latest, _ = client.json(f'{BASE}/{resolution}', refresh=True)
        end = latest['timestamp'] + step
        results.append(bulk(client, root, mapping, resolution=resolution,
                            start=end-hours*3600, end=end))
    return results
