"""Rebuild bundled seed assets from checked-in USDA SR28 rows; stdlib only."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from almanac.domain import Ingredient, Nutrition


def rows(path):
    with path.open(encoding='latin1', newline='') as stream:
        return list(csv.reader(stream, delimiter='^', quotechar='~'))


def curate(source=ROOT / 'data/usda'):
    provenance = json.loads((source / 'provenance.json').read_text())
    for name, hashes in provenance['files'].items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != hashes['subset_sha256']:
            raise ValueError(f'USDA source integrity failure: {name}')
    foods = {r[0]: r for r in rows(source / 'FOOD_DES.txt')}
    groups = {r[0]: r[1] for r in rows(source / 'FD_GROUP.txt')}
    weights = {(r[0], r[1]): r for r in rows(source / 'WEIGHT.txt')}
    nutrients = {}
    for row in rows(source / 'NUT_DATA.txt'):
        key = row[0], row[1]
        if key in nutrients:
            raise ValueError(f'Duplicate nutrient: {key}')
        nutrients[key] = float(row[2]) if row[2] else None
    selection = json.loads((source / 'selection.json').read_text())
    result, seen = [], set()
    for chosen in selection['foods']:
        ndb = chosen['ndb_id']
        if ndb in seen:
            raise ValueError(f'Duplicate selected food: {ndb}')
        seen.add(ndb)
        row = foods[ndb]
        conversions, descriptions = {}, {}
        for unit, sequence in chosen['conversions'].items():
            weight = weights[ndb, sequence]
            conversions[unit] = float(weight[4]) / float(weight[2])
            descriptions[unit] = weight[3]
        nutrition = dict(zip(('calories', 'protein', 'carbs', 'fat'),
                             (nutrients.get((ndb, key)) for key in ('208', '203', '205', '204'))))
        record = dict(id=f'usda-sr28:{ndb}', name=row[2], category=groups[row[1]],
                      nutrition=nutrition, reference_amount=100, reference_unit='g',
                      conversions=conversions, conversion_descriptions=descriptions,
                      source=provenance['dataset'], source_id=ndb)
        Ingredient(record['id'], record['name'], Nutrition(**nutrition), conversions=conversions)
        result.append(record)
    return dict(schema_version=1, catalog_version='usda-sr28-staples-2', provenance=provenance, foods=result)


def write_database(catalog, destination):
    """Build a seed asset only; never target a user's writable database."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        path = Path(temporary) / 'foods.db'
        conn = sqlite3.connect(path)
        try:
            conn.executescript('''
                PRAGMA foreign_keys=ON;
                PRAGMA user_version=1;
                CREATE TABLE foods (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
                    calories REAL CHECK(calories>=0), protein REAL CHECK(protein>=0),
                    carbs REAL CHECK(carbs>=0), fat REAL CHECK(fat>=0),
                    reference_amount REAL NOT NULL CHECK(reference_amount>0),
                    reference_unit TEXT NOT NULL, source TEXT NOT NULL, source_id TEXT NOT NULL
                );
                CREATE TABLE conversions (
                    food_id TEXT REFERENCES foods(id), unit TEXT NOT NULL,
                    reference_units REAL NOT NULL CHECK(reference_units>0),
                    description TEXT NOT NULL, PRIMARY KEY(food_id,unit)
                );
                CREATE TABLE catalog_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE INDEX foods_name ON foods(name COLLATE NOCASE);
            ''')
            with conn:
                for food in catalog['foods']:
                    n = food['nutrition']
                    conn.execute('INSERT INTO foods VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                                 (food['id'], food['name'], food['category'], n['calories'], n['protein'],
                                  n['carbs'], n['fat'], 100, 'g', food['source'], food['source_id']))
                    conn.executemany('INSERT INTO conversions VALUES (?,?,?,?)',
                                     ((food['id'], u, v, food['conversion_descriptions'][u])
                                      for u, v in food['conversions'].items()))
                conn.execute('INSERT INTO catalog_metadata VALUES (?,?)', ('catalog_version', catalog['catalog_version']))
                conn.execute('INSERT INTO catalog_metadata VALUES (?,?)', ('provenance', json.dumps(catalog['provenance'], sort_keys=True)))
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Seed integrity check failed')
        finally:
            conn.close()
        path.replace(destination)


def build(database=ROOT / 'setup/foods.db', json_path=ROOT / 'data/staples.json'):
    catalog = curate()
    write_database(catalog, database)
    Path(json_path).write_text(json.dumps(catalog, indent=2, sort_keys=True) + '\n')
    return catalog


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT / 'setup/foods.db')
    parser.add_argument('--json', type=Path, default=ROOT / 'data/staples.json')
    args = parser.parse_args()
    catalog = build(args.database, args.json)
    print(f"Built {len(catalog['foods'])} USDA staples")
