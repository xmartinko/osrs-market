"""Item bonuses, weights/alchemy and monster drop definitions (not realized supply)."""
import json

import pyarrow as pa

from .storage import completed, publish

SCHEMAS = {
    'items': pa.schema([('item_id', pa.int64()), ('name', pa.string()),
                        ('weight', pa.float64()), ('cost', pa.int64()),
                        ('lowalch', pa.int64()), ('highalch', pa.int64()),
                        ('buy_limit', pa.int64()), ('last_updated', pa.string()),
                        ('equipment_json', pa.string()), ('weapon_json', pa.string()),
                        ('raw_json', pa.string())]),
    'monsters': pa.schema([('monster_id', pa.int64()), ('name', pa.string()),
                           ('last_updated', pa.string()), ('raw_json', pa.string())]),
    'drops': pa.schema([('monster_id', pa.int64()), ('item_id', pa.int64()),
                        ('name', pa.string()), ('quantity', pa.string()),
                        ('rarity', pa.float64()), ('rolls', pa.float64()),
                        ('raw_json', pa.string())]),
}
REPOSITORIES = {'osrsbox': 'osrsbox/osrsbox-db',
                'osrsreboxed': '0xNeffarion/osrsreboxed-db'}


def adapt(payload, kind):
    rows, drops = [], []
    for raw in payload.values():
        if kind == 'items':
            rows.append(dict(item_id=raw['id'], name=raw['name'],
                             **{k: raw.get(k) for k in ('weight', 'cost', 'lowalch', 'highalch',
                                                       'buy_limit', 'last_updated')},
                             equipment_json=json.dumps(raw.get('equipment')),
                             weapon_json=json.dumps(raw.get('weapon')),
                             raw_json=json.dumps(raw, sort_keys=True)))
        else:
            rows.append(dict(monster_id=raw['id'], name=raw['name'],
                             last_updated=raw.get('last_updated'), raw_json=json.dumps(raw)))
            for drop in raw.get('drops') or []:
                drops.append(dict(monster_id=raw['id'], item_id=drop.get('id'),
                                  name=drop.get('name'), quantity=str(drop.get('quantity')),
                                  rarity=drop.get('rarity'), rolls=drop.get('rolls'),
                                  raw_json=json.dumps(drop, sort_keys=True)))
    return rows, drops


def run(client, root, *, repository='osrsreboxed', snapshot='2026-10-30'):
    directory = root / repository / snapshot
    directory.mkdir(parents=True, exist_ok=True)
    results = []
    for kind in ('items', 'monsters'):
        path = directory / f'{kind}.parquet'
        if completed(path) and (kind == 'items' or completed(directory / 'drops.parquet')):
            continue
        url = f'https://raw.githubusercontent.com/{REPOSITORIES[repository]}/master/docs/{kind}-complete.json'
        payload, record = client.json(url)
        rows, drops = adapt(payload, kind)
        results.append(publish(path, rows, source=repository, record=record, schema=SCHEMAS[kind],
                               table=kind, price_observations=False))
        if kind == 'monsters':
            results.append(publish(directory / 'drops.parquet', drops, source=repository,
                                   record=record, schema=SCHEMAS['drops'], table='drops',
                                   price_observations=False))
    return results
