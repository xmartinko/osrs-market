"""Public Kaggle dumps, without credentials, cookies, login or access-wall workarounds."""
import json
import shutil
import zipfile

from .columnar import normalize
from .http import atomic_json

REF = 'antonygarand/osrs-ge-5m'


def run(client, root, mapping):
    directory = root / 'kaggle-5m'
    archive = directory / 'raw' / 'dataset-v1.zip'
    record = client.download(f'https://www.kaggle.com/api/v1/datasets/download/{REF}?datasetVersionNumber=1',
                             archive)
    checkpoint = directory / 'checkpoint-v2.json'
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            if member.is_dir():
                continue
            from pathlib import PurePosixPath
            parts = PurePosixPath(member.filename).parts
            if '..' in parts or member.filename.startswith('/'):
                raise ValueError('Unsafe archive member')
            raw = directory / 'raw' / member.filename
            if not raw.exists():
                raw.parent.mkdir(parents=True, exist_ok=True)
                pending = raw.with_suffix('.partial')
                with z.open(member) as source, pending.open('wb') as target:
                    shutil.copyfileobj(source, target, length=1024*1024)
                pending.rename(raw)
            if member.filename.startswith('prices_5m/') and member.filename.endswith('.parquet'):
                main = normalize(raw, directory / 'canonical-v2/main' / member.filename,
                                 record=record, source='kaggle-5m', mapping=mapping,
                                 timestamp_scale=300, item_filter='listed')
                quarantine = normalize(
                    raw, directory / 'canonical-v2/unclassified_legacy' / member.filename,
                    record=record, source='kaggle-5m', mapping=mapping, timestamp_scale=300,
                    item_filter='unlisted', economy='unclassified_legacy')
                state[member.filename] = dict(main=main, unclassified_legacy=quarantine)
                atomic_json(checkpoint, state)
    return dict(source='kaggle-5m', partitions=len(state),
                rows=sum(r['main']['rows']+r['unclassified_legacy']['rows'] for r in state.values()),
                unclassified_rows=sum(r['unclassified_legacy']['rows'] for r in state.values()))
