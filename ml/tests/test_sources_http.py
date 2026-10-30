import copy
import json

import httpx
import pyarrow.parquet as pq
import pytest
from fixtures.source_records import WG

from osrs_ml.sources import http, storage, weirdgloop


def test_wg_preserves_null_volume_milliseconds_and_guide_price():
    rows = weirdgloop.adapt(WG, 4151, 'Abyssal whip')
    assert rows[0]['ts'] == 1427500800
    assert rows[0]['mid_price'] == 2057864
    assert rows[0]['avg_high_price'] is None and rows[0]['total_volume'] is None
    assert json.loads(rows[0]['source_extra'])['timestamp'] == 1427500800000
    bad = copy.deepcopy(WG)
    bad['4151'].append(bad['4151'][0])
    with pytest.raises(ValueError, match='Duplicate'):
        weirdgloop.adapt(bad, 4151)
    with pytest.raises(ValueError, match='Application error'):
        weirdgloop.adapt({'success': False, 'error': 'No results returned'}, 4151)
    bad = copy.deepcopy(WG)
    bad['4151'][0]['timestamp'] += 1
    with pytest.raises(ValueError, match='millisecond'):
        weirdgloop.adapt(bad, 4151)



def test_external_path_refuses_repo_and_symlink(tmp_path):
    with pytest.raises(ValueError, match='under'):
        storage.external_root(tmp_path)



def install_transport(client, handler):
    client.session.close()
    client.session = httpx.Client(transport=httpx.MockTransport(handler),
                                 headers={'User-Agent': http.USER_AGENT})



@pytest.fixture
def fake_time(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(http.time, 'time', lambda: now[0])
    monkeypatch.setattr(http.time, 'sleep', lambda seconds: now.__setitem__(0, now[0] + seconds))
    return now



def test_http_ua_shared_host_throttle_and_cache(tmp_path, fake_time):
    calls = []
    def handler(request):
        assert request.headers['user-agent'] == http.USER_AGENT
        calls.append(fake_time[0])
        return httpx.Response(200, json={'ok': True})
    a = http.Client(tmp_path / 'evidence' / 'http')
    b = http.Client(tmp_path / 'evidence' / 'http')
    install_transport(a, handler)
    install_transport(b, handler)
    a.json('https://example.org/a')
    b.json('https://example.org:443/b')  # same host despite an explicit default port
    a.json('https://example.org/a')
    assert len(calls) == 2 and calls[1] - calls[0] >= 1
    assert list(a.root.glob('*.body'))



def test_http_429_retry_after_and_no_auth_retry(tmp_path, fake_time):
    calls = []
    def handler(request):
        calls.append(fake_time[0])
        if len(calls) == 1:
            return httpx.Response(429, headers={'Retry-After': '30'}, text='slow down')
        return httpx.Response(200, json={'ok': True})
    c = http.Client(tmp_path / 'http')
    install_transport(c, handler)
    c.json('https://example.org/a')
    assert calls[1] - calls[0] >= 30
    def blocked(request):
        calls.append(fake_time[0])
        return httpx.Response(403, text='blocked')
    install_transport(c, blocked)
    with pytest.raises(http.FetchError, match='HTTP 403'):
        c.json('https://example.org/private')
    n = len(calls)
    with pytest.raises(http.FetchError, match='Cached HTTP 403'):
        c.json('https://example.org/private')
    assert len(calls) == n



def test_stream_resume_redirect_keeps_ua_and_range(tmp_path, fake_time):
    c = http.Client(tmp_path / 'http')
    path = tmp_path / 'archive.zip'
    pending = path.with_suffix('.zip.partial')
    pending.write_bytes(b'abc')
    original = 'https://example.org/file'
    http.atomic_json(pending.with_suffix('.resume.json'),
                     dict(original_url=original, headers={'etag': 'version-1'}))
    calls = []
    def handler(request):
        assert request.headers['user-agent'] == http.USER_AGENT
        assert request.headers['range'] == 'bytes=3-'
        assert request.headers['if-range'] == 'version-1'
        calls.append(str(request.url))
        if request.url.host == 'example.org':
            return httpx.Response(302, headers={'Location': 'https://cdn.example.org/file'})
        return httpx.Response(206, headers={'Content-Range': 'bytes 3-5/6'}, content=b'def')
    install_transport(c, handler)
    assert c.download(original, path)['bytes'] == 6
    assert path.read_bytes() == b'abcdef' and len(calls) == 2
    assert c.download(original, path)['bytes'] == 6 and len(calls) == 2



def test_stream_403_never_follows_wall(tmp_path, fake_time):
    c = http.Client(tmp_path / 'http')
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(403, text='Access denied')
    install_transport(c, handler)
    with pytest.raises(http.FetchError, match='HTTP 403'):
        c.download('https://example.org/file', tmp_path / 'file')
    assert len(calls) == 1



def test_wg_interruption_resume_and_rolling_deduplication(tmp_path):
    class RecordedClient:
        def __init__(self):
            self.calls = 0
        def json(self, url, **kwargs):
            self.calls += 1
            if 'id=561' in url:
                raise http.FetchError('HTTP 503 recorded failure')
            return WG, dict(url=url, fetched_at='2026-10-30T00:00:00Z', sha256='raw')
    client = RecordedClient()
    mapping = [{'id': 4151, 'name': 'Abyssal whip'}]
    a = weirdgloop.run(client, tmp_path, mapping, snapshot='fixed')
    assert a['rows'] == 2
    assert weirdgloop.run(client, tmp_path, mapping)['rows'] == 2
    assert client.calls == 1  # default resumes the existing backfill, even on another date
    first = weirdgloop.run(client, tmp_path, mapping, kind='last90d', snapshot='day1')
    second = weirdgloop.run(client, tmp_path, mapping, kind='last90d', snapshot='day2')
    assert first['rows'] == 2 and second['rows'] == 0
    assert pq.read_metadata(tmp_path / 'weirdgloop-last90d/day2/items/4151.parquet').num_rows == 0
    # A failed transport checkpoints the failure and returns a nonzero CLI exit via exception.
    with pytest.raises(http.FetchError, match='503'):
        weirdgloop.run(client, tmp_path, [{'id': 561, 'name': 'Nature rune'}], snapshot='failed')
    state = json.loads((tmp_path / 'weirdgloop-all/failed/checkpoint.json').read_text())
    assert state['561']['status'] == 'error'



def test_throttle_spaces_starts_and_keeps_retry_backoff_after_response(tmp_path, fake_time):
    starts = []
    def handler(request):
        starts.append(fake_time[0])
        fake_time[0] += 0.4  # recorded transport latency, while the host lock is held
        return httpx.Response(200, json={'ok': True})
    client = http.Client(tmp_path / 'http')
    install_transport(client, handler)
    client.json('https://example.org/first')
    client.json('https://example.org/second')
    assert 1.0 <= starts[1] - starts[0] <= 1.1


def test_refresh_preserves_original_payload_evidence(tmp_path, fake_time):
    client = http.Client(tmp_path / 'http')
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={'revision': len(calls)})
    install_transport(client, handler)
    _, first = client.json('https://example.org/data')
    _, second = client.json('https://example.org/data', refresh=True)
    assert first['body_file'] != second['body_file']
    assert json.loads((client.root / first['body_file']).read_text()) == {'revision': 1}
    assert client.json('https://example.org/data')[0] == {'revision': 2}
    assert len(calls) == 2


def test_download_refuses_to_overwrite_orphan_existing_file(tmp_path):
    client = http.Client(tmp_path / 'http')
    path = tmp_path / 'archive.zip'
    path.write_bytes(b'existing original bytes')
    with pytest.raises(FileExistsError, match='Refusing'):
        client.download('https://example.org/archive', path)
    assert path.read_bytes() == b'existing original bytes'


@pytest.mark.parametrize('name', ['../forward', '/tmp/data', 'a/b', 'a\\b', '..', '.'])
def test_snapshot_names_cannot_escape_research_partition(name):
    with pytest.raises(ValueError, match='single'):
        storage.snapshot_name(name)
