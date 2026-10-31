"""Offline checks using recorded market-response excerpts."""
import copy
import json
from pathlib import Path

import httpx
import pyarrow.parquet as pq
import pytest

from osrs_ml.sources import ge_tracker as ge
from osrs_ml.sources import http, report

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/ge_tracker.json').read_text())


def test_weekly_recorded_columns_counts_and_extras():
    rows = ge.adapt_graph(FIXTURE['graph'], 4151, 'Abyssal whip')
    assert len(rows) == 2
    first = rows[0]
    assert first['ts'] == 1488412800
    assert first['avg_high_price'] == 1684421 and first['avg_low_price'] == 1683475
    assert first['mid_price'] == 1683910
    assert first['total_volume'] == 36306  # deliberately differs from side sum
    assert first['high_price_volume'] == 17754 and first['low_price_volume'] == 18519
    extra = json.loads(first['source_extra'])
    assert extra['point'] == FIXTURE['graph']['data'][0]
    assert extra['envelope']['source'] == 'runelite'
    assert rows[-1]['ts'] - first['ts'] == 504 * 604800


def test_fixture_variants_fractional_prices_nulls_and_duplicates(tmp_path):
    payload = copy.deepcopy(FIXTURE['graph'])
    payload['data'][0].update(overallPrice=1.25, buyingPrice=1.5,
                              sellingPrice=1.125, overallCompleted=None)
    rows = ge.adapt_graph(payload, 4151)
    record = dict(url=ge.BASE+'/graph/4151/all', fetched_at='2026-10-30T00:00:00Z', sha256='fixture')
    ge.publish(tmp_path / 'recorded.parquet', rows, source='ge-tracker-weekly', record=record)
    restored = pq.read_table(tmp_path / 'recorded.parquet').to_pylist()[0]
    assert restored['avg_high_price'] == 1.5 and restored['avg_low_price'] == 1.125
    assert restored['mid_price'] == 1.25 and restored['total_volume'] is None
    payload['data'].append(payload['data'][0])
    with pytest.raises(ValueError, match='Duplicate'):
        ge.adapt_graph(payload, 4151)
    payload['data'].pop()
    payload['data'][0]['ts'] += 1
    with pytest.raises(ValueError, match='millisecond'):
        ge.adapt_graph(payload, 4151)


def test_rich_details_keep_all_fields_without_inventing_turnover():
    item = FIXTURE['details']['data']
    row = ge.adapt_item(item, '2026-10-30T22:22:29+00:00', source='ge-tracker-details')
    assert row['item_id'] == 4151  # internal id=19 is not the game item ID
    assert row['total_volume'] is None and row['high_price_volume'] is None
    assert json.loads(row['source_extra'])['item'] == item
    assert json.loads(row['source_extra'])['item']['buySellRatio'] == 1.11


class RecordedClient:
    def __init__(self):
        self.calls = []
        self.fail_details = False

    def json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith('/market-watch'):
            raise http.FetchError('HTTP 401 recorded anonymous response', status=401)
        if '/graph/' in url:
            payload = FIXTURE['graph']
        elif url.endswith('/items'):
            payload = {'data': [FIXTURE['details']['data']]}
        else:
            if self.fail_details and not kwargs.get('refresh'):
                raise http.FetchError('HTTP 503 recorded transport condition', status=503)
            payload = FIXTURE['details']
        return payload, dict(url=url, status=200, fetched_at='2026-10-30T22:22:29Z', sha256='fixture')


def test_resume_does_not_duplicate_and_records_credentials_absent(tmp_path, monkeypatch):
    client = RecordedClient()
    absent = tmp_path / 'absent.env'
    first = ge.run(client, tmp_path, snapshot='recorded', credentials=absent)
    assert first['weekly_rows'] == 2 and first['detail_rows'] == 1
    assert first['catalogue_rows'] == 1
    assert first['authenticated']['state'] == 'credentials not supplied'
    assert len(report.groups(tmp_path)['ge-tracker-weekly']) == 1
    features = report.feature_groups(tmp_path)
    assert len(features['ge-tracker-items']) == len(features['ge-tracker-details']) == 1
    assert not features['ge-tracker-market-watch']
    n = len(client.calls)
    checkpoint = tmp_path / 'ge-tracker/recorded/checkpoint.json'
    checkpoint_writes = []
    original_atomic_json = ge.atomic_json
    def record_write(path, value):
        if path == checkpoint:
            checkpoint_writes.append(path)
        return original_atomic_json(path, value)
    monkeypatch.setattr(ge, 'atomic_json', record_write)
    assert ge.run(client, tmp_path, credentials=absent) == first
    assert len(client.calls) == n + 1
    assert not checkpoint_writes
    checkpoint.write_text('{}')  # crash after publish, before checkpoint
    assert ge.run(client, tmp_path, credentials=absent) == first
    assert json.loads(checkpoint.read_text())['4151']['weekly']['rows'] == 2
    assert len(checkpoint_writes) == 1


def test_failure_is_checkpointed_and_resume_preserves_completed_graph(tmp_path):
    client = RecordedClient()
    client.fail_details = True
    absent = tmp_path / 'absent.env'
    with pytest.raises(http.FetchError, match='503'):
        ge.run(client, tmp_path, snapshot='recorded', credentials=absent)
    state = json.loads((tmp_path / 'ge-tracker/recorded/checkpoint.json').read_text())
    assert state['4151']['weekly']['status'] == 'complete'
    assert state['4151']['details']['http_status'] == 503
    n = len(client.calls)
    client.fail_details = False
    result = ge.run(client, tmp_path, credentials=absent)
    assert result['weekly_rows'] == 2 and result['detail_rows'] == 1
    assert all('/graph/' not in url for url, _ in client.calls[n:])


def test_credentials_are_optional_secure_and_never_in_errors(tmp_path):
    path = tmp_path / 'headers.env'
    assert ge.credential_headers(path) is None
    content = "GE_TRACKER_HEADERS_JSON='" + json.dumps({'Authorization': 'recorded-placeholder'}) + "'\n"
    path.write_text(content)
    path.chmod(0o644)
    with pytest.raises(ValueError, match='0600'):
        ge.credential_headers(path)
    path.chmod(0o600)
    assert ge.credential_headers(path) == {'Authorization': 'recorded-placeholder'}
    link = tmp_path / 'link.env'
    link.symlink_to(path)
    with pytest.raises(ValueError, match='securely'):
        ge.credential_headers(link)
    for value in ['GE_TRACKER_HEADERS_JSON=recorded-placeholder',
                  'GE_TRACKER_HEADERS_JSON={"User-Agent":"recorded-placeholder"}']:
        path.write_text(value)
        with pytest.raises(ValueError) as exc:
            ge.credential_headers(path)
        assert 'recorded-placeholder' not in str(exc.value)


def test_private_http_never_archives_secrets_or_response_body(tmp_path, monkeypatch):
    monkeypatch.setattr(http.time, 'sleep', lambda _: None)
    client = http.Client(tmp_path / 'http', interval=0)
    assert client.interval == 1.05
    observed = []
    def handler(request):
        observed.append(request)
        return httpx.Response(200, headers={'Set-Cookie': 'private-placeholder'}, json=FIXTURE['details'])
    client.session.close()
    client.session = httpx.Client(transport=httpx.MockTransport(handler),
                                  headers={'User-Agent': http.USER_AGENT})
    payload, record = client.json(ge.BASE+'/market-watch', private=True,
                                  headers={'Authorization': 'recorded-placeholder'})
    assert payload == FIXTURE['details'] and record['body_archived'] is False
    assert observed[0].headers['user-agent'] == http.USER_AGENT
    assert observed[0].headers['authorization'] == 'recorded-placeholder'
    assert not list(client.root.glob('*.body')) and not client.session.cookies
    for path in tmp_path.rglob('*'):
        if path.is_file():
            assert 'recorded-placeholder' not in path.read_text()
            assert 'private-placeholder' not in path.read_text()
    with pytest.raises(ValueError, match='User-Agent'):
        client.json(ge.BASE+'/market-watch', private=True, headers={'User-Agent': 'other'})


def test_identity_payload_is_rejected_without_echoing_value():
    with pytest.raises(ValueError) as exc:
        ge.market_only({'account': 'recorded-private-placeholder'})
    assert 'recorded-private-placeholder' not in str(exc.value)


def test_route_probe_resumes_after_recorded_transport_failure(tmp_path):
    client = RecordedClient()
    original = client.json
    failed = [False]
    def interrupted(url, **kwargs):
        if url.endswith('/items/4151') and not failed[0]:
            failed[0] = True
            raise http.FetchError('HTTP 503', status=503)
        return original(url, **kwargs)
    client.json = interrupted
    with pytest.raises(http.FetchError):
        ge.route_probe(client, tmp_path)
    saved = json.loads((tmp_path / 'routes.json').read_text())
    assert saved['/items']['status'] == 200 and saved['/items/4151']['status'] == 503
    result = ge.route_probe(client, tmp_path)
    assert len(result) == 4 and result['/market-watch']['status'] == 401
    assert sum(url.endswith('/items') for url, _ in client.calls) == 1


def test_authenticated_market_fixture_uses_explicit_headers_and_safe_summary(tmp_path):
    class AuthenticatedFixtureClient:
        def json(self, url, **kwargs):
            assert kwargs['private'] is True
            assert kwargs['headers'] == {'Authorization': 'recorded-placeholder'}
            return {'data': [FIXTURE['details']['data']]}, dict(
                url=url, status=200, fetched_at='2026-10-30T22:22:29Z', sha256='fixture')
    result = ge.collect_authenticated(AuthenticatedFixtureClient(), tmp_path,
                                      {'/market-watch': {'status': 401}},
                                      {'Authorization': 'recorded-placeholder'})
    assert result['state'] == 'complete' and result['rows'] == 1
    assert 'recorded-placeholder' not in json.dumps(result)
    assert pq.read_metadata(tmp_path / 'market-watch/snapshot.parquet').num_rows == 1


def test_research_report_keeps_weekly_and_snapshot_totals_separate(tmp_path):
    ge.run(RecordedClient(), tmp_path, snapshot='recorded', credentials=tmp_path/'absent.env')
    record = dict(url=ge.BASE+'/market-watch', fetched_at='2026-10-30T22:22:29Z', sha256='fixture')
    ge.publish(tmp_path/'ge-tracker/recorded/market-watch/snapshot.parquet', [],
               source='ge-tracker-market-watch', record=record)
    result = report.run(tmp_path)
    assert result['canonical_source_rows'] == 2
    assert result['features']['ge-tracker-items']['rows'] == 1
    assert result['features']['ge-tracker-details']['rows'] == 1
    assert result['features']['ge-tracker-market-watch']['rows'] == 0
    assert result['features']['ge-tracker-market-watch']['sample'] == {}


def test_http_200_application_error_is_deferred_then_refreshed(tmp_path, monkeypatch):
    client = RecordedClient()
    original = client.json
    failed = [False]
    refreshed = []
    def application_error(url, **kwargs):
        payload, record = original(url, **kwargs)
        if '/graph/' in url and not kwargs.get('refresh') and not failed[0]:
            failed[0] = True
            return FIXTURE['graph_error'], record
        if '/graph/' in url and kwargs.get('refresh') and failed[0]:
            refreshed.append(url)
        return payload, record
    client.json = application_error
    monkeypatch.setattr(ge.time, 'time', lambda: 1793398949)
    first = ge.run(client, tmp_path, snapshot='recorded', credentials=tmp_path/'absent.env')
    assert first['weekly_rows'] == 0 and first['detail_rows'] == 1
    assert first['selection_complete'] is False and first['pending_items'] == [4151]
    # A rerun before the provider's minute has elapsed does not repeat the request.
    again = ge.run(client, tmp_path, credentials=tmp_path/'absent.env')
    assert again == first and not refreshed
    monkeypatch.setattr(ge.time, 'time', lambda: 1793399011)
    recovered = ge.run(client, tmp_path, credentials=tmp_path/'absent.env')
    assert recovered['weekly_rows'] == 2 and recovered['detail_rows'] == 1
    assert recovered['selection_complete'] is True and recovered['pending_items'] == []
    assert len(refreshed) == 1
