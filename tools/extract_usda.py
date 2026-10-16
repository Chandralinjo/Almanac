"""Recreate the source subset from a pinned, unmodified USDA SR28 mirror checkout."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def extract(upstream, output=ROOT / 'data/usda'):
    selection = json.loads((output / 'selection.json').read_text())
    provenance = json.loads((output / 'provenance.json').read_text())
    ids = {f['ndb_id'] for f in selection['foods']}
    # Validate everything before replacing any source subset.
    subsets = {}
    for name, hashes in provenance['files'].items():
        raw = (upstream / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != hashes['upstream_sha256']:
            raise ValueError(f'Upstream does not match pinned source: {name}')
        selected = []
        for line in raw.decode('latin1').splitlines(keepends=True):
            row = next(csv.reader([line], delimiter='^', quotechar='~'))
            if name == 'FD_GROUP.txt' or (row[0] in ids and
                    (name != 'NUT_DATA.txt' or row[1] in ('208', '203', '204', '205'))):
                selected.append(line)
        data = ''.join(selected).encode('latin1')
        if hashlib.sha256(data).hexdigest() != hashes['subset_sha256']:
            raise ValueError(f'Selection differs from pinned subset: {name}')
        subsets[name] = data
    for name, data in subsets.items():
        (output / name).write_bytes(data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream', type=Path)
    extract(parser.parse_args().upstream)
