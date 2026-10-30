"""Polite, process-shared HTTP evidence archive for private research only."""
import fcntl
import hashlib
import json
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

USER_AGENT = 'osrs-market-research/0.1 (private personal research; no contact address)'


def atomic_json(path, value):
    path = Path(path)
    pending = path.with_suffix(path.suffix + '.partial')
    pending.write_text(json.dumps(value, indent=2, default=str) + '\n')
    pending.replace(path)


class FetchError(RuntimeError):
    def __init__(self, message, *, status=None):
        super().__init__(message)
        self.status = status


class Client:
    def __init__(self, root, *, interval=1.05, retries=3, host_locks=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.interval = max(1.05, interval)
        self.retries = retries
        self.host_locks = Path(host_locks) if host_locks else self.root.parent / '.http-hosts'
        self.session = httpx.Client(headers={'User-Agent': USER_AGENT}, timeout=90,
                                    follow_redirects=False)

    def fetch(self, url, *, refresh=False, headers=None, private=False):
        # Credentialed requests never reuse anonymous cache entries or archive raw
        # bodies/cookies. The caller validates and publishes only market data.
        if headers and not private:
            raise ValueError('Request headers require private evidence mode')
        if headers and any(k.lower() == 'user-agent' for k in headers):
            raise ValueError('User-Agent cannot be overridden')
        key = hashlib.sha256(url.encode()).hexdigest()
        meta = self.root / f'{key}.json'
        body = self.root / f'{key}.body'
        if meta.exists() and not refresh and not private:
            record = json.loads(meta.read_text())
            body = self.root / record.get('body_file', body.name)
            if record['status'] == 200 and body.exists():
                content = body.read_bytes()
                if hashlib.sha256(content).hexdigest() != record['sha256']:
                    raise ValueError(f'HTTP cache checksum mismatch: {body}')
                return content, record
            if record['status'] in (401, 403, 404, 410, 451):
                raise FetchError(f"Cached HTTP {record['status']} {url}; evidence={meta}",
                                 status=record['status'])
        host = urlsplit(url).hostname
        request_headers = headers
        lockpath = self.host_locks
        lockpath.mkdir(parents=True, exist_ok=True)
        for attempt in range(self.retries + 1):
            with (lockpath / f'{host}.lock').open('a+') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                clock = lockpath / f'{host}.json'
                previous = json.loads(clock.read_text()) if clock.exists() else {}
                time.sleep(max(0, previous.get('next', 0) - time.time()))
                started = time.time()
                status, headers, error = 0, {}, None
                try:
                    self.session.cookies.clear()
                    response = self.session.get(url, headers=request_headers)
                    self.session.cookies.clear()
                    status, headers, content = response.status_code, dict(response.headers), response.content
                    headers = {k: v for k, v in headers.items()
                               if k.lower() not in ('set-cookie', 'authorization', 'proxy-authenticate')}
                    if private:
                        headers = {k: v for k, v in headers.items() if k.lower() in
                                   ('content-type', 'date', 'retry-after', 'x-ratelimit-limit',
                                    'x-ratelimit-remaining', 'x-ratelimit-reset')}
                except httpx.HTTPError as exc:
                    error = type(exc).__name__ if private else str(exc)
                    content = error.encode()
                delay = self.interval
                if status == 429 or status >= 500 or not status:
                    delay = max(delay, min(120, 2 ** (attempt + 2)) + random.uniform(0, 1))
                    retry_after = headers.get('retry-after')
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            delay = max(delay, parsedate_to_datetime(retry_after).timestamp() - time.time())
                next_request = (time.time() + delay if status == 429 or status >= 500
                                or not status else started + self.interval)
                atomic_json(clock, {'next': next_request})
                record = dict(url=url, status=status, headers=headers, error=error,
                              started_at=datetime.fromtimestamp(started, timezone.utc).isoformat(),
                              fetched_at=datetime.now(timezone.utc).isoformat(),
                              user_agent=USER_AGENT, bytes=len(content), attempt=attempt,
                              sha256=hashlib.sha256(content).hexdigest())
                # Preserve every actual response, including retries and fresh collections.
                evidence = self.root / f'{key}-{time.time_ns()}'
                if private:
                    record['body_archived'] = False
                else:
                    evidence.with_suffix('.body').write_bytes(content)
                    record['body_file'] = evidence.with_suffix('.body').name
                atomic_json(evidence.with_suffix('.json'), record)
                # Only the lookup index changes. Payloads, including the original
                # legacy cache body, are immutable; refresh never destroys evidence.
                if not private:
                    atomic_json(meta, record)
            if status == 200:
                return content, record
            if status not in (429,) and status < 500 and status != 0:
                break
        raise FetchError(f'HTTP {status} {url}; evidence={meta}', status=status)

    def json(self, url, **kwargs):
        content, record = self.fetch(url, **kwargs)
        return json.loads(content), record

    def download(self, url, path):
        """Stream public files, resume partial bytes with Range, follow normal redirects only."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata = path.with_suffix(path.suffix + '.http.json')
        if path.exists() and metadata.exists():
            record = json.loads(metadata.read_text())
            if record['original_url'] != url:
                raise ValueError('Download provenance mismatch')
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            if digest.hexdigest() != record['sha256']:
                raise ValueError('Download checksum mismatch')
            return record
        if path.exists():
            raise FileExistsError(f'Refusing to replace an existing download without provenance: {path}')
        original_url = url
        pending = path.with_suffix(path.suffix + '.partial')
        for attempt in range(self.retries + 1):
            current = original_url
            try:
                for _ in range(6):
                    host = urlsplit(current).hostname
                    locks = self.host_locks
                    locks.mkdir(parents=True, exist_ok=True)
                    with (locks / f'{host}.lock').open('a+') as lock:
                        fcntl.flock(lock, fcntl.LOCK_EX)
                        clock = locks / f'{host}.json'
                        prior = json.loads(clock.read_text()) if clock.exists() else {}
                        time.sleep(max(0, prior.get('next', 0) - time.time()))
                        offset = pending.stat().st_size if pending.exists() else 0
                        resume_meta = pending.with_suffix('.resume.json')
                        prior_download = (json.loads(resume_meta.read_text())
                                          if resume_meta.exists() else {})
                        validator = prior_download.get('headers', {}).get('etag') or \
                            prior_download.get('headers', {}).get('last-modified')
                        if offset and (not validator or
                                       prior_download.get('original_url') != original_url):
                            offset = 0
                        headers = ({'Range': f'bytes={offset}-', 'If-Range': validator}
                                   if offset else {})
                        started = time.time()
                        with self.session.stream('GET', current, headers=headers) as response:
                            status = response.status_code
                            record = dict(url=current, original_url=original_url, status=status,
                                          headers=dict(response.headers), user_agent=USER_AGENT,
                                          started_at=datetime.fromtimestamp(started, timezone.utc).isoformat(),
                                          fetched_at=datetime.now(timezone.utc).isoformat())
                            key = hashlib.sha256(current.encode()).hexdigest()
                            atomic_json(self.root / f'{key}-{time.time_ns()}.json', record)
                            delay = self.interval
                            if status == 429 or status >= 500:
                                delay = max(delay, 2 ** (attempt + 2) + random.random())
                                value = response.headers.get('retry-after')
                                if value:
                                    try:
                                        delay = max(delay, float(value))
                                    except ValueError:
                                        delay = max(delay, parsedate_to_datetime(value).timestamp()
                                                    - time.time())
                            # Reserve the host on both success and failed transfers.
                            next_request = (time.time() + delay if status == 429 or status >= 500
                                            else started + self.interval)
                            atomic_json(clock, {'next': next_request})
                            if status in (301, 302, 303, 307, 308):
                                from urllib.parse import urljoin
                                current = urljoin(current, response.headers['location'])
                                if urlsplit(current).scheme != 'https':
                                    raise FetchError('Refusing non-HTTPS redirect')
                                continue
                            if status not in (200, 206):
                                error_body = response.read()
                                (self.root / f'{key}-{time.time_ns()}.body').write_bytes(error_body)
                                raise FetchError(f'HTTP {status} {original_url}', status=status)
                            if status == 206 and not response.headers.get('content-range', '').startswith(
                                    f'bytes {offset}-'):
                                raise FetchError('Invalid Content-Range')
                            atomic_json(resume_meta, record)
                            with pending.open('ab' if status == 206 else 'wb') as stream:
                                for chunk in response.iter_bytes(1024 * 1024):
                                    stream.write(chunk)
                            if status == 206:
                                total = response.headers['content-range'].rsplit('/', 1)[1]
                                if total != '*' and pending.stat().st_size != int(total):
                                    raise httpx.ReadError('Incomplete resumed download')
                            atomic_json(clock, {'next': started + self.interval})
                        digest = hashlib.sha256()
                        with pending.open('rb') as stream:
                            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                                digest.update(chunk)
                        record.update(sha256=digest.hexdigest(), bytes=pending.stat().st_size,
                                      download_completed_at=datetime.now(timezone.utc).isoformat())
                        pending.rename(path)
                        atomic_json(metadata, record)
                        return record
                raise FetchError('Too many redirects')
            except (httpx.HTTPError, FetchError) as exc:
                if isinstance(exc, FetchError) and status not in (429,) and status < 500:
                    raise
                if attempt == self.retries:
                    raise
                time.sleep(min(60, 2 ** (attempt + 2)) + random.random())
        raise FetchError(original_url)
