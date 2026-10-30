"""Immutable partitions and checksum manifests, reusing the existing manifest writer."""
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ..data import manifest, sha256

CANONICAL = pa.schema([
    ('item_id', pa.int64()), ('name', pa.string()), ('ts', pa.int64()),
    ('avg_high_price', pa.float64()), ('avg_low_price', pa.float64()),
    ('high_price_volume', pa.int64()), ('low_price_volume', pa.int64()),
    ('mid_price', pa.float64()), ('total_volume', pa.int64()),
    ('source', pa.string()), ('economy', pa.string()), ('source_extra', pa.string()),
])


def external_root(root):
    root = Path(root).resolve()
    allowed = Path('/home/martin/osrs-data/sources').resolve()
    if root != allowed and not root.is_relative_to(allowed):
        raise ValueError('Acquisition output must be under /home/martin/osrs-data/sources')
    root.mkdir(parents=True, exist_ok=True)
    return root


def canonical(item_id, name, ts, *, source, high=None, low=None, hv=None, lv=None,
              mid=None, volume=None, economy='main', extra=None):
    return dict(item_id=int(item_id), name=name, ts=int(ts), avg_high_price=high,
                avg_low_price=low, high_price_volume=hv, low_price_volume=lv,
                mid_price=mid if mid is not None else
                ((high + low) / 2 if high is not None and low is not None else None),
                total_volume=volume if volume is not None else
                (hv + lv if hv is not None and lv is not None else None),
                source=source, economy=economy, source_extra=json.dumps(extra or {}, sort_keys=True))


def completed(path):
    path = Path(path)
    meta = path.with_suffix('.manifest.json')
    if not path.exists() or not meta.exists():
        return False
    data = json.loads(meta.read_text())
    if data['sha256'] != sha256(path):
        raise ValueError(f'Checksum mismatch: {path}')
    return True


def publish(path, rows, *, source, record, schema=CANONICAL, **extras):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if completed(path):
        return json.loads(path.with_suffix('.manifest.json').read_text())
    if path.exists():
        # Crash after parquet publication: recover only if bytes match deterministic rows.
        existing = pq.read_table(path)
        expected = pa.Table.from_pylist(rows, schema=schema)
        if not existing.equals(expected):
            raise FileExistsError(f'Incomplete partition differs: {path}')
    else:
        pending = path.with_suffix('.partial')
        pq.write_table(pa.Table.from_pylist(rows, schema=schema), pending, compression='zstd')
        pending.rename(path)
    timestamps = [r['ts'] for r in rows if r.get('ts') is not None]
    return manifest(path, source=source, rows=len(rows), fetched_at=record['fetched_at'],
                    endpoint=record['url'], payload_sha256=record['sha256'],
                    min_ts=min(timestamps) if timestamps else None,
                    max_ts=max(timestamps) if timestamps else None, **extras)
