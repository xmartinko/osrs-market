"""Seasonal dumps: each Deadman/FSW economy stays physically and logically separate."""
import shutil
import tarfile

from .columnar import normalize

REPO = 'https://raw.githubusercontent.com/weirdgloop/runelite-ge-dumps/master'
ECONOMIES = ('deadman_reborn', 'fsw_2022', 'deadman_apocalypse',
             'deadman_armageddon', 'deadman_annihilation')


def run(client, root, mapping):
    directory = root / 'seasonal-dumps'
    results = []
    for economy in ECONOMIES:
        archive = directory / 'raw' / f'{economy}.tar.gz'
        record = client.download(f'{REPO}/{economy}.tar.gz', archive)
        with tarfile.open(archive) as tar:
            members = [m for m in tar.getmembers() if m.isfile()
                       and m.name.endswith('.csv') and not m.name.rsplit('/', 1)[-1].startswith('._')]
            if len(members) != 1:
                raise ValueError('Require one market CSV per archive')
            raw = directory / 'raw' / f'{economy}.csv'
            if not raw.exists():
                pending = raw.with_suffix('.partial')
                with tar.extractfile(members[0]) as source, pending.open('wb') as output:
                    shutil.copyfileobj(source, output)
                pending.rename(raw)
        results.append(normalize(raw, directory / economy / 'observations.parquet',
                                 source='seasonal-dumps', economy=economy, record=record,
                                 timestamp='unixTime', mapping=mapping, format='csv'))
    return results
