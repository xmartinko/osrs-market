"""Offline parser/provenance checks using small recorded response excerpts."""
import json
from datetime import datetime, timezone

import pyarrow.parquet as pq
import pytest
from fixtures.source_records import LUA, MONSTER, WIKI

from osrs_ml.sources import (
    activity,
    mediawiki,
    metadata,
    storage,
    supplementary,
    wayback,
    wiki,
    wiki_features,
)


def test_v2_fractional_prices_unknown_ids_and_regime():
    rows = wiki.adapt(WIKI, {2: 'Steel cannonball'}, '5m',
                      expected_timestamp=WIKI['timestamp'])
    assert rows[0]['avg_high_price'] == 205.61
    assert rows[0]['total_volume'] == 116141
    assert json.loads(rows[0]['source_extra'])['regime'] == 'jagex_all_clients'
    assert wiki.adapt(WIKI, {}, '5m')[0]['economy'] == 'unclassified_legacy'
    assert json.loads(wiki.point(2, {}, wiki.REGIME_BREAK - 1, endpoint='5m')
                      ['source_extra'])['regime'] == 'runelite_only'
    with pytest.raises(ValueError, match='different bucket'):
        wiki.adapt(WIKI, {}, '5m', expected_timestamp=1)


def test_revision_price_date_is_distinct_from_revision_time_and_nil_stays_missing():
    rev = dict(revid=1, timestamp='2019-03-24T12:00:00Z', slots={'main': {'*': LUA}})
    payload = {'query': {'pages': {'1': dict(pageid=57763, title='Module:Exchange/Abyssal whip',
                                           revisions=[rev])}}}
    row = mediawiki.adapt(payload)[0]
    assert row['item_id'] == 4151 and row['price'] == 2790107
    assert row['volume'] == 6510 and '23 March 2019' in row['volume_date_literal']
    assert row['revision_ts'] == int(datetime(2019, 3, 24, 12, tzinfo=timezone.utc).timestamp())
    assert mediawiki.numeric('price = mw.loadData("x").price,', 'price') is None
    assert mediawiki.numeric('volume = nil,', 'volume') is None


def test_metadata_retains_drop_definition_and_incomplete_flag():
    monsters, drops = metadata.adapt(MONSTER, 'monsters')
    assert json.loads(monsters[0]['raw_json'])['incomplete'] is True
    assert drops[0]['rarity'] == 0.013671875
    assert drops[0]['quantity'] == '1'
    assert 'noted' in json.loads(drops[0]['raw_json'])


def test_wayback_embedded_tokens_retain_conflicts_without_fabricating_volume():
    # Recorded chart tokens; repeated and conflicting tokens exercise archive handling.
    text = ('<div class="GEdataprices" data-data="1427414400:2040584|'
            '1427500800:2057864|1427414400:2040584"></div>'
            '<div class="GEdataprices" data-data="1427414400:2057864"></div>')
    rows = wayback.adapt(text)
    assert len(rows) == 3 and all(r['total_volume'] is None for r in rows)
    assert sum(json.loads(r['source_extra'])['timestamp_conflict'] for r in rows) == 2
    with pytest.raises(ValueError, match='No embedded'):
        wayback.adapt('<html>Store price: Not sold</html>')


def test_publishing_float_schema_resume_and_corruption(tmp_path):
    path = tmp_path / 'rows.parquet'
    record = dict(url='https://example.org/recorded', fetched_at='2026-10-30T00:00:00Z', sha256='raw')
    rows = wiki.adapt(WIKI, {2: 'Steel cannonball'}, '5m')
    meta = storage.publish(path, rows, source='wiki-v2', record=record)
    original = path.read_bytes()
    assert storage.publish(path, [], source='wiki-v2', record=record) == meta
    assert path.read_bytes() == original
    assert pq.read_table(path)['avg_high_price'][0].as_py() == 205.61
    path.with_suffix('.manifest.json').unlink()
    storage.publish(path, rows, source='wiki-v2', record=record)
    assert path.read_bytes() == original  # recover manifest only after a crash
    path.write_bytes(original + b'corruption')
    with pytest.raises(ValueError, match='Checksum'):
        storage.completed(path)


def test_recorded_alchemy_metadata_keeps_null_limit_and_source_literals():
    raw = dict(item_id='10344', name='3rd age amulet', limit='', value='50500',
               highalch='30300.0', lowalch='20200.0')
    row = supplementary.alchemy([raw])[0]
    assert row['highalch'] == 30300 and row['buy_limit'] is None
    assert json.loads(row['source_extra']) == raw


def test_recorded_world_population_unknown_population_never_becomes_zero():
    text = '''<tr class="server-list__row"><td><a id="slu-world-393">393</a></td>
        <td>69 players</td><td>United States</td><td>Free</td><td>750 skill total</td></tr>
        <tr class="server-list__row"><td><a id="slu-world-394">394</a></td>
        <td>OFFLINE</td><td>United States</td><td>Members</td><td>-</td></tr>'''
    rows = activity.adapt(text, 1793381338)
    assert rows[0]['players'] == 69 and rows[1]['players'] is None


def test_wiki_literal_facts_keep_nested_links_and_do_not_evaluate_templates():
    page = dict(title='Abyssal whip', revision_id=1, revision_ts=1789274728,
                wikitext='{{Infobox Item\n|value = 120001\n|weight = 0.453\n'
                         '|image = [[File:Abyssal whip.png|thumb]]\n}}\n'
                         '{{Infobox Bonuses\n|aslash = +82\n|str = {{Unknown|82}}\n}}')
    facts = {r['field']: r for r in wiki_features.adapt(page, {'Abyssal whip': 4151})}
    assert facts['aslash']['numeric_literal'] == 82
    assert facts['weight']['numeric_literal'] == 0.453
    assert facts['image']['literal'] == '[[File:Abyssal whip.png|thumb]]'
    assert facts['str']['literal'] == '{{Unknown|82}}'
    assert facts['str']['numeric_literal'] is None and facts['str']['page_item_id'] == 4151
