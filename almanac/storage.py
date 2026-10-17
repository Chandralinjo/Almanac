"""Transactional, versioned SQLite ingredient repository; no Kivy dependency.

Seed baselines and user overrides are distinct. Overrides are field-level,
including individual nutrients; conversion maps are edited as one field.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .domain import Ingredient, Nutrition, NUTRIENTS

SCHEMA_VERSION = 3
FIELDS = ('name', 'category', 'reference_amount', 'reference_unit', 'conversions',
          'conversion_descriptions', 'source', 'source_id')


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def validate_record(record):
    """Validate the storage contract through the same domain constructor as M1."""
    record = deepcopy(record)
    Ingredient(record['id'], record['name'], Nutrition(**record['nutrition']),
               record['reference_amount'], record['reference_unit'], record['conversions'], record['source'])
    if not isinstance(record.get('category'), str):
        raise ValueError('Category must be text')
    if not isinstance(record['source'], str) or not isinstance(record['source_id'], str):
        raise ValueError('Source and source ID must be text')
    descriptions = record.get('conversion_descriptions', {})
    if not isinstance(descriptions, dict) or any(not isinstance(v, str) for v in descriptions.values()):
        raise ValueError('Conversion descriptions must be text')
    if not set(descriptions) <= set(record['conversions']):
        raise ValueError('Conversion description without a conversion')
    record['conversion_descriptions'] = descriptions
    record['nutrition'] = {n: record['nutrition'].get(n) for n in NUTRIENTS}
    return {k: record[k] for k in ('id', 'nutrition') + FIELDS}


def validate_catalog(catalog):
    if catalog.get('schema_version') != 1:
        raise ValueError('Unsupported catalog schema')
    if not isinstance(catalog.get('catalog_version'), str) or not catalog['catalog_version']:
        raise ValueError('Catalog version is required')
    records = [validate_record(f) for f in catalog['foods']]
    if not records or len({f['id'] for f in records}) != len(records):
        raise ValueError('Catalog must contain foods with unique IDs')
    return records


def differences(base, edited):
    changes = {k: edited[k] for k in FIELDS if edited[k] != base[k]}
    for nutrient in NUTRIENTS:
        if edited['nutrition'][nutrient] != base['nutrition'][nutrient]:
            changes['nutrition.' + nutrient] = edited['nutrition'][nutrient]
    return changes


def apply_overrides(base, overrides):
    record = deepcopy(base)
    for key, value in overrides.items():
        if key.startswith('nutrition.'):
            record['nutrition'][key.split('.')[1]] = value
        elif key in FIELDS:
            record[key] = value
        else:
            raise ValueError(f'Unknown override field: {key}')
    return validate_record(record)


# Exact values in the original deployment spike, used only for migration.
# Unmodified rounded fixture values should give way to the sourced catalog.
LEGACY = {
    'Whole Milk': ('01077', (61, 3.2, 4.8, 3.3)),
    'Eggs (Whole, Raw)': ('01123', (143, 12.6, .7, 9.5)),
    'All-Purpose Flour': ('20081', (364, 10.3, 76.3, 1.0)),
    'White Rice (Cooked)': ('20045', (130, 2.7, 28.2, .3)),
    'Oats (Rolled)': ('08120', (389, 16.9, 66.3, 6.9)),
    'Banana': ('09040', (89, 1.1, 22.8, .3)),
    'Apple (Raw with skin)': ('09003', (52, .3, 13.8, .2)),
    'Broccoli (Raw)': ('11090', (34, 2.8, 6.6, .4)),
    'Spinach (Raw)': ('11457', (23, 2.9, 3.6, .4)),
    'Olive Oil': ('04053', (884, 0.0, 0.0, 100.0)),
    'Butter': ('01001', (717, .9, .1, 81.1)),
    'Honey': ('19296', (304, .3, 82.4, 0.0)),
}
LEGACY_CATEGORIES = dict(zip(LEGACY, ('Dairy', 'Dairy & Eggs', 'Grains', 'Grains', 'Grains',
    'Fruits', 'Fruits', 'Vegetables', 'Vegetables', 'Oils & Fats', 'Oils & Fats', 'Sweeteners')))


class IngredientStore:
    def __init__(self, path, catalog, legacy_path=None, checkpoint=None):
        # Validate the entire incoming catalog before touching the live database.
        records = validate_catalog(catalog)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys=ON')
        self.conn.execute('PRAGMA busy_timeout=5000')
        self.conn.execute('PRAGMA synchronous=FULL')
        checkpoint = checkpoint or (lambda stage: None)
        try:
            with self.transaction():
                self._migrate()
                checkpoint('schema')
                self._sync_catalog(records, catalog)
                checkpoint('catalog')
                if not self._metadata('initialized'):
                    if legacy_path is not None and Path(legacy_path).exists():
                        self._import_legacy(Path(legacy_path))
                    checkpoint('legacy')
                    self.conn.execute('INSERT INTO metadata VALUES (?,?)', ('initialized', '1'))
                checkpoint('ready')
        except BaseException:
            self.conn.close()
            raise

    @contextmanager
    def transaction(self):
        self.conn.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise

    def _migrate(self):
        version = self.conn.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ValueError('This database needs a newer version of Almanac')
        if version == 0:
            tables = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if tables:
                raise ValueError('Unrecognized database; existing data was left untouched')
            # Avoid executescript: it commits implicitly and would break atomic setup.
            for statement in (
                'CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)',
                '''CREATE TABLE seed_records (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, hash TEXT NOT NULL,
                    catalog_version TEXT NOT NULL)''',
                '''CREATE TABLE ingredients (
                    id TEXT PRIMARY KEY, seed_id TEXT UNIQUE REFERENCES seed_records(id) ON DELETE RESTRICT,
                    custom_payload TEXT, overrides TEXT NOT NULL DEFAULT '{}',
                    archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
                    CHECK((seed_id IS NULL AND custom_payload IS NOT NULL) OR
                          (seed_id IS NOT NULL AND custom_payload IS NULL)))''',
            ):
                self.conn.execute(statement)
            self.conn.execute('PRAGMA user_version=1')
            version = 1
        if version == 1:
            self.conn.execute('ALTER TABLE seed_records ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0 CHECK(pinned IN (0,1))')
            self.conn.execute('ALTER TABLE seed_records ADD COLUMN available INTEGER NOT NULL DEFAULT 1 CHECK(available IN (0,1))')
            self.conn.execute('PRAGMA user_version=2')
            version = 2
        if version == 2:
            self.conn.execute('CREATE TABLE recipes(id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            self.conn.execute('''CREATE TABLE recipe_ingredients(
                recipe_id TEXT NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
                ingredient_id TEXT NOT NULL REFERENCES ingredients(id) ON DELETE RESTRICT,
                PRIMARY KEY(recipe_id,ingredient_id))''')
            self.conn.execute('CREATE TABLE recipe_draft(slot INTEGER PRIMARY KEY CHECK(slot=1), payload TEXT NOT NULL)')
            self.conn.execute('PRAGMA user_version=3')

    def _metadata(self, key):
        row = self.conn.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
        return None if row is None else row[0]

    def _sync_catalog(self, records, catalog):
        self.conn.execute('UPDATE seed_records SET available=0 WHERE pinned=0')
        for record in records:
            payload = encode(record)
            existing = self.conn.execute('SELECT pinned,payload FROM seed_records WHERE id=?', (record['id'],)).fetchone()
            if existing is not None and existing['pinned']:
                continue
            if existing is not None:
                previous = json.loads(existing['payload'])
                edits = self.conn.execute('SELECT overrides FROM ingredients WHERE seed_id=?', (record['id'],)).fetchone()
                if edits and json.loads(edits['overrides']) and any(
                        previous[k] != record[k] for k in ('reference_amount', 'reference_unit')):
                    # Do not mix corrected nutrient values with a new measurement basis.
                    self.conn.execute('UPDATE seed_records SET pinned=1,available=1 WHERE id=?', (record['id'],))
                    continue
            self.conn.execute('''INSERT INTO seed_records(id,payload,hash,catalog_version,available)
                VALUES (?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
                hash=excluded.hash,catalog_version=excluded.catalog_version,available=1''',
                (record['id'], payload, hashlib.sha256(payload.encode()).hexdigest(), catalog['catalog_version']))
            collision = self.conn.execute('SELECT seed_id FROM ingredients WHERE id=?', (record['id'],)).fetchone()
            if collision is not None and collision['seed_id'] != record['id']:
                raise ValueError('Catalog ID collides with a custom ingredient')
            self.conn.execute('INSERT OR IGNORE INTO ingredients(id,seed_id) VALUES (?,?)', (record['id'], record['id']))
            # An upgrade must not commit an invalid baseline + override combination.
            self.get(record['id'])
        provenance = encode(catalog.get('provenance', {}))
        # Keep attribution for retained/pinned records from earlier catalogs too.
        self.conn.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)',
                          ('provenance:' + catalog['catalog_version'] + ':' + hashlib.sha256(provenance.encode()).hexdigest(), provenance))
        for key, value in (('catalog_version', catalog['catalog_version']), ('provenance', provenance)):
            self.conn.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', (key, value))

    def _import_legacy(self, path):
        # Read-only connection: legacy data remains a recovery copy, never modified.
        legacy = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
        legacy.row_factory = sqlite3.Row
        try:
            columns = {r[1] for r in legacy.execute('PRAGMA table_info(foods)')}
            if not {'id','name','calories','protein','carbs','fat'} <= columns:
                raise ValueError('Unrecognized legacy foods database; import was not applied')
            sourced = 'reference_unit' in columns
            used = set()
            for row in legacy.execute('SELECT * FROM foods ORDER BY id'):
                row = dict(row)
                if sourced:
                    record = {k: row[k] for k in ('id','name','category','reference_amount','reference_unit','source','source_id')}
                    record['nutrition'] = {n: row[n] for n in NUTRIENTS}
                    record['conversions'], record['conversion_descriptions'] = {}, {}
                    for conversion in legacy.execute('SELECT * FROM conversions WHERE food_id=?', (row['id'],)):
                        record['conversions'][conversion['unit']] = conversion['reference_units']
                        record['conversion_descriptions'][conversion['unit']] = conversion['description']
                    existing = self.conn.execute('SELECT 1 FROM ingredients WHERE id=?', (record['id'],)).fetchone()
                    if existing:
                        self._save(record, preserve_overrides=False)
                    else:
                        self._insert_custom(record)
                elif row['name'] in LEGACY and row['name'] not in used:
                    used.add(row['name'])
                    ndb, original = LEGACY[row['name']]
                    id = 'usda-sr28:' + ndb
                    if self.conn.execute('SELECT 1 FROM ingredients WHERE id=?', (id,)).fetchone():
                        record = self.get(id)
                        for n, previous in zip(NUTRIENTS, original):
                            if row[n] != previous:
                                record['nutrition'][n] = row[n]
                        if (row.get('category') or '') != LEGACY_CATEGORIES[row['name']]:
                            record['category'] = row.get('category') or ''
                        self._save(record)
                    else:
                        self._import_custom_legacy(row)
                else:
                    self._import_custom_legacy(row)
        finally:
            legacy.close()

    def _import_custom_legacy(self, row):
        self._insert_custom(dict(id='legacy:' + str(row['id']), name=row['name'],
            category=row.get('category') or '', reference_amount=100, reference_unit='g',
            nutrition={n:row[n] for n in NUTRIENTS}, conversions={}, conversion_descriptions={},
            source='Imported deployment test database', source_id=str(row['id'])))

    def _insert_custom(self, record):
        record = validate_record(record)
        self.conn.execute('INSERT INTO ingredients(id,custom_payload) VALUES (?,?)', (record['id'], encode(record)))

    def get(self, id):
        row = self.conn.execute('''SELECT i.*,s.payload,s.hash,s.catalog_version,s.available,s.pinned
            FROM ingredients i LEFT JOIN seed_records s ON s.id=i.seed_id WHERE i.id=?''', (id,)).fetchone()
        if row is None:
            raise KeyError(id)
        record = apply_overrides(json.loads(row['payload'] or row['custom_payload']), json.loads(row['overrides']))
        record.update(archived=bool(row['archived']), is_seed=row['seed_id'] is not None,
                      modified=bool(json.loads(row['overrides'])), baseline_hash=row['hash'],
                      catalog_version=row['catalog_version'], catalog_available=bool(row['available']), pinned=bool(row['pinned']))
        return record

    def list(self, query='', include_archived=False):
        # Casefold in Python handles Unicode consistently across Android SQLite builds.
        words = query.casefold().split()
        records = (self.get(r[0]) for r in self.conn.execute('SELECT id FROM ingredients'))
        return sorted((r for r in records if (include_archived or not r['archived']) and
                       all(w in (r['name'] + ' ' + r['category']).casefold() for w in words)),
                      key=lambda r:(r['name'].casefold(), r['id']))

    def create(self, record):
        record = dict(record, id='custom:' + str(uuid4()))
        with self.transaction():
            self._insert_custom(record)
        return self.get(record['id'])

    def _save(self, record, preserve_overrides=True):
        record = validate_record(record)
        row = self.conn.execute('SELECT seed_id,custom_payload,overrides FROM ingredients WHERE id=?', (record['id'],)).fetchone()
        if row is None:
            raise KeyError(record['id'])
        if row['seed_id']:
            base = json.loads(self.conn.execute('SELECT payload FROM seed_records WHERE id=?', (row['seed_id'],)).fetchone()[0])
            changes = differences(base, record)
            if any(record[k] != base[k] for k in ('reference_amount', 'reference_unit')):
                # All measurements now describe the user's new basis. Updating an
                # otherwise unedited macro from the old basis would change meaning.
                changes.update((k, record[k]) for k in ('reference_amount', 'reference_unit',
                               'conversions', 'conversion_descriptions'))
                changes.update(('nutrition.' + n, record['nutrition'][n]) for n in NUTRIENTS)
            if any(record[k] != base[k] for k in ('conversions', 'conversion_descriptions')):
                # A description belongs to its exact conversion, never a newer map.
                changes.update((k, record[k]) for k in ('conversions', 'conversion_descriptions'))
            if preserve_overrides:
                # Preserve deliberate overrides that happen to equal a new baseline.
                old = json.loads(row['overrides'])
                for key, value in old.items():
                    actual = record['nutrition'][key.split('.')[1]] if key.startswith('nutrition.') else record[key]
                    if actual == value:
                        changes[key] = value
            self.conn.execute('UPDATE ingredients SET overrides=? WHERE id=?', (encode(changes), record['id']))
        else:
            self.conn.execute('UPDATE ingredients SET custom_payload=? WHERE id=?', (encode(record), record['id']))

    def save(self, record):
        with self.transaction():
            self._save(record)
        return self.get(record['id'])

    def archive(self, id, archived=True):
        if not isinstance(archived, bool):
            raise ValueError('Archive state must be boolean')
        with self.transaction():
            if self.conn.execute('UPDATE ingredients SET archived=? WHERE id=?', (int(archived), id)).rowcount != 1:
                raise KeyError(id)

    def reset(self, id):
        with self.transaction():
            row = self.conn.execute('SELECT seed_id FROM ingredients WHERE id=?', (id,)).fetchone()
            if row is None or row['seed_id'] is None:
                raise ValueError('Only starter ingredients have a baseline to restore')
            self.conn.execute("UPDATE ingredients SET overrides='{}' WHERE id=?", (id,))
        return self.get(id)

    def ingredient(self, id):
        r = self.get(id)
        return Ingredient(r['id'], r['name'], Nutrition(**r['nutrition']), r['reference_amount'],
                          r['reference_unit'], r['conversions'], r['source'])

    def save_recipe(self, recipe):
        from .recipes import recipe_record
        from .domain import Alternative
        # Revalidate even callers outside the editor, including every hidden option.
        from .recipes import parse_recipe
        raw = recipe_record(recipe)
        recipe = parse_recipe(raw)
        ids = {l.ingredient_id for p in recipe.phases for e in p.entries
               for l in (e.options if isinstance(e, Alternative) else (e,))}
        with self.transaction():
            for id in ids:
                self.get(id)
            self.conn.execute('INSERT OR REPLACE INTO recipes VALUES (?,?)', (recipe.id, encode(raw)))
            self.conn.execute('DELETE FROM recipe_ingredients WHERE recipe_id=?', (recipe.id,))
            self.conn.executemany('INSERT INTO recipe_ingredients VALUES (?,?)', ((recipe.id, id) for id in ids))
            self.conn.execute('DELETE FROM recipe_draft')
        return recipe

    def get_recipe(self, id):
        from .recipes import parse_recipe
        row = self.conn.execute('SELECT payload FROM recipes WHERE id=?', (id,)).fetchone()
        if row is None:
            raise KeyError(id)
        return parse_recipe(json.loads(row[0]))

    def list_recipes(self, query=''):
        recipes = [self.get_recipe(r[0]) for r in self.conn.execute('SELECT id FROM recipes')]
        words = query.casefold().split()
        return sorted((r for r in recipes if all(w in (r.name + ' ' + ' '.join(r.tags)).casefold() for w in words)),
                      key=lambda r: (r.name.casefold(), r.id))

    def save_recipe_draft(self, raw):
        with self.transaction():
            self.conn.execute('INSERT OR REPLACE INTO recipe_draft VALUES (1,?)', (encode(raw),))

    def recipe_draft(self):
        row = self.conn.execute('SELECT payload FROM recipe_draft WHERE slot=1').fetchone()
        return json.loads(row[0]) if row else None

    def clear_recipe_draft(self):
        with self.transaction():
            self.conn.execute('DELETE FROM recipe_draft')

    def close(self):
        self.conn.close()
