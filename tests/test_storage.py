from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from almanac.storage import IngredientStore, SCHEMA_VERSION
from almanac.forms import blank_record, parse_form
from almanac.domain import food_nutrition
from tools.build_staples import ROOT


def catalog():
    return json.loads((ROOT / 'data/staples.json').read_text())


def custom(name='My food'):
    r = blank_record()
    r.update(name=name, category='Personal', nutrition=dict(calories=123, protein=None, carbs=0, fat=1),
             conversions={'piece':53}, conversion_descriptions={'piece':'small'})
    return r


class StoreFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'almanac.db'
        self.stores = []

    def tearDown(self):
        for s in self.stores:
            try:
                s.close()
            except sqlite3.ProgrammingError:
                pass
        self.temp.cleanup()

    def open(self, seed=None, **kwargs):
        store = IngredientStore(self.path, catalog() if seed is None else seed, **kwargs)
        self.stores.append(store)
        return store


class StorageTests(StoreFixture):
    def test_offline_initialize_reopen_and_domain_bridge(self):
        store = self.open()
        self.assertEqual(len(store.list()), 169)
        self.assertEqual(store.conn.execute('PRAGMA foreign_keys').fetchone()[0], 1)
        self.assertEqual(store.conn.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
        self.assertEqual(food_nutrition(store.ingredient('usda-sr28:01123'), 2, 'piece').calories.value, 143)
        store.close()
        self.assertEqual(len(self.open().list()), 169)

    def test_custom_edits_archive_and_unknown_survive_reopen(self):
        store = self.open()
        record = store.create(custom())
        record['name'] = 'Updated food'
        store.save(record)
        store.archive(record['id'])
        self.assertEqual(len(store.list()), 169)
        self.assertEqual(len(store.list(include_archived=True)), 170)
        store.close()
        store = self.open()
        saved = store.get(record['id'])
        self.assertEqual(saved['name'], 'Updated food')
        self.assertIsNone(saved['nutrition']['protein'])
        self.assertEqual(saved['conversions'], {'piece':53})
        self.assertTrue(saved['archived'])
        store.archive(record['id'], False)
        self.assertEqual(len(store.list('updated personal')), 1)

    def test_catalog_upgrade_preserves_each_nutrient_override_and_custom_data(self):
        seed = catalog()
        store = self.open(seed)
        id = seed['foods'][0]['id']
        record = store.get(id)
        record['nutrition']['protein'] = 99
        record['name'] = 'My butter'
        record['conversions'] = {'piece':20}
        record['conversion_descriptions'] = {'piece':'my portion'}
        store.save(record)
        store.archive(id)
        added = store.create(custom())
        store.close()
        upgraded = deepcopy(seed)
        upgraded['catalog_version'] = 'next'
        upgraded['foods'][0]['nutrition'].update(protein=100, calories=500)
        upgraded['foods'][0]['name'] = 'New starter name'
        upgraded['foods'][0]['conversions'] = {'piece':30}
        upgraded['foods'][0]['conversion_descriptions'] = {'piece':'new portion'}
        upgraded['foods'].append(dict(custom('New seed'), id='usda:added'))
        store = self.open(upgraded)
        actual = store.get(id)
        self.assertEqual(actual['nutrition']['protein'], 99)
        self.assertEqual(actual['nutrition']['calories'], 500)
        self.assertEqual(actual['name'], 'My butter')
        self.assertEqual(actual['conversions'], {'piece':20})
        self.assertTrue(actual['archived'])
        self.assertEqual(store.get(added['id'])['nutrition']['calories'], 123)
        self.assertEqual(store.get('usda:added')['name'], 'New seed')
        store.reset(id)
        self.assertEqual(store.get(id)['nutrition']['protein'], 100)
        self.assertEqual(store.get(id)['name'], 'New starter name')
        self.assertTrue(store.get(id)['archived'])

    def test_user_reference_change_keeps_its_nutrient_basis_on_upgrade(self):
        seed = catalog()
        store = self.open(seed)
        id = seed['foods'][0]['id']
        record = store.get(id)
        record['reference_amount'] = 1
        record['nutrition']['calories'] = 7
        store.save(record)
        store.close()
        upgraded = deepcopy(seed)
        upgraded['catalog_version'] = 'next'
        upgraded['foods'][0]['nutrition']['fat'] = 99
        actual = self.open(upgraded).get(id)
        self.assertEqual(actual['reference_amount'], 1)
        self.assertEqual(actual['nutrition'], record['nutrition'])

    def test_measurement_basis_change_pins_edited_baseline(self):
        seed = catalog()
        store = self.open(seed)
        id = seed['foods'][0]['id']
        record = store.get(id)
        record['nutrition']['calories'] = 700
        store.save(record)
        store.close()
        upgraded = deepcopy(seed)
        upgraded['catalog_version'] = 'different basis'
        upgraded['foods'][0]['reference_amount'] = 1
        upgraded['foods'][0]['nutrition']['calories'] = 7
        store = self.open(upgraded)
        self.assertTrue(store.get(id)['pinned'])
        self.assertEqual(store.get(id)['reference_amount'], 100)
        self.assertEqual(store.get(id)['nutrition']['calories'], 700)

    def test_removed_seed_retained_and_custom_never_overwritten(self):
        seed = catalog()
        store = self.open(seed)
        id = seed['foods'][0]['id']
        store.close()
        upgraded = deepcopy(seed)
        upgraded['foods'].pop(0)
        store = self.open(upgraded)
        self.assertEqual(len(store.list()), 169)
        self.assertFalse(store.get(id)['catalog_available'])

    def test_failure_at_each_initialization_checkpoint_rolls_back(self):
        for stage in ('schema','catalog','legacy','ready'):
            def fail(current):
                if current == stage:
                    raise RuntimeError('simulated failure')
            with self.subTest(stage=stage):
                if self.path.exists():
                    self.path.unlink()
                with self.assertRaises(RuntimeError):
                    self.open(checkpoint=fail)
                store = self.open()
                self.assertEqual(len(store.list()), 169)
                store.close()

    def test_abrupt_process_death_retries_initialization(self):
        code = '''import json,os,sys
from almanac.storage import IngredientStore
seed=json.load(open('data/staples.json'))
def stop(stage):
    if stage == sys.argv[2]: os._exit(77)
IngredientStore(sys.argv[1], seed, checkpoint=stop)
'''
        for stage in ('schema','catalog','legacy','ready'):
            with self.subTest(stage=stage):
                path = Path(self.temp.name) / f'{stage}.db'
                result = subprocess.run([sys.executable, '-c', code, str(path), stage], cwd=ROOT)
                self.assertEqual(result.returncode, 77)
                store = IngredientStore(path, catalog())
                self.stores.append(store)
                self.assertEqual(len(store.list()), 169)
                self.assertEqual(store.conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_interrupted_populated_upgrade_keeps_old_data_and_retries(self):
        seed = catalog()
        store = self.open(seed)
        id = seed['foods'][0]['id']
        changed = store.get(id)
        changed['name'] = 'Edited'
        store.save(changed)
        added = store.create(custom())
        before = list(store.conn.iterdump())
        store.close()
        upgraded = deepcopy(seed)
        upgraded['catalog_version'] = 'new'
        upgraded['foods'][0]['nutrition']['calories'] = 100
        def fail(stage):
            if stage == 'catalog':
                raise OSError('out of storage')
        with self.assertRaises(OSError):
            self.open(upgraded, checkpoint=fail)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(list(conn.iterdump()), before)
        store = self.open(upgraded)
        self.assertEqual(store.get(id)['name'], 'Edited')
        self.assertEqual(store.get(id)['nutrition']['calories'], 100)
        self.assertEqual(store.get(added['id'])['name'], 'My food')

    def test_newer_schema_and_bad_catalog_leave_existing_data(self):
        store = self.open()
        store.conn.execute('PRAGMA user_version=999')
        before = list(store.conn.iterdump())
        store.close()
        with self.assertRaisesRegex(ValueError,'newer'):
            self.open()
        invalid = catalog()
        invalid['foods'][-1]['nutrition']['fat'] = -1
        with self.assertRaises(ValueError):
            self.open(invalid)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(list(conn.iterdump()), before)
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],999)

    def test_foreign_key_and_invalid_edit_atomicity(self):
        store = self.open()
        with self.assertRaises(sqlite3.IntegrityError):
            with store.transaction():
                store.conn.execute("INSERT INTO ingredients(id,seed_id) VALUES ('bad','missing')")
        record = store.get('usda-sr28:01123')
        original = deepcopy(record)
        record['nutrition']['protein'] = -1
        with self.assertRaises(ValueError):
            store.save(record)
        self.assertEqual(store.get(record['id']), original)

    def test_version_one_schema_migrates_with_populated_records(self):
        seed = catalog()
        store = self.open(seed)
        record = store.create(custom())
        store.archive(record['id'])
        store.conn.execute('ALTER TABLE seed_records DROP COLUMN pinned')
        store.conn.execute('ALTER TABLE seed_records DROP COLUMN available')
        store.conn.execute('PRAGMA user_version=1')
        store.close()
        store = self.open(seed)
        self.assertTrue(store.get(record['id'])['archived'])
        self.assertEqual(store.conn.execute('PRAGMA user_version').fetchone()[0],2)

    def test_sourced_spike_import_once_leaves_original_untouched(self):
        legacy = Path(self.temp.name) / 'foods.db'
        import shutil
        shutil.copyfile(ROOT / 'setup/foods.db', legacy)
        with sqlite3.connect(legacy) as conn:
            conn.execute("UPDATE foods SET protein=88 WHERE source_id='01123'")
        before = legacy.read_bytes()
        store = self.open(legacy_path=legacy)
        self.assertEqual(store.get('usda-sr28:01123')['nutrition']['protein'],88)
        record = store.get('usda-sr28:01123')
        record['nutrition']['protein'] = 77
        store.save(record)
        store.close()
        store = self.open(legacy_path=legacy)
        self.assertEqual(store.get(record['id'])['nutrition']['protein'],77)
        self.assertEqual(legacy.read_bytes(),before)

    def test_original_spike_imports_changes_and_custom_food(self):
        legacy = Path(self.temp.name) / 'foods.db'
        with sqlite3.connect(legacy) as conn:
            conn.execute('CREATE TABLE foods(id INTEGER PRIMARY KEY,name TEXT,category TEXT,calories REAL,protein REAL,carbs REAL,fat REAL)')
            conn.executemany('INSERT INTO foods VALUES (?,?,?,?,?,?,?)', [
                (1,'Whole Milk','Dairy',61,3.2,4.8,3.3),
                (2,'Eggs (Whole, Raw)','Dairy & Eggs',143,42,.7,9.5),
                (3,'My custom snack','Personal',100,None,2,3)])
        store = self.open(legacy_path=legacy)
        self.assertEqual(len(store.list()),170)
        self.assertFalse(store.get('usda-sr28:01077')['modified'])
        self.assertEqual(store.get('usda-sr28:01123')['nutrition']['protein'],42)
        self.assertIsNone(store.get('legacy:3')['nutrition']['protein'])


class FormTests(unittest.TestCase):
    def values(self):
        return dict(name='My ingredient', category='Other', reference_amount='100', reference_unit='g',
                    calories='12,5', protein='', carbs='0', fat='1')

    def test_form_accepts_decimal_comma_and_blank_unknown(self):
        record = parse_form(self.values(), [('piece','53','large'), ('','','')], blank_record())
        self.assertEqual(record['nutrition'], dict(calories=12.5,protein=None,carbs=0,fat=1))
        self.assertEqual(record['conversions'], {'piece':53})

    def test_form_rejects_invalid_numbers_empty_units_and_duplicate_conversions(self):
        for field, value in (('name',''),('reference_amount','0'),('reference_unit',''),
                             ('protein','-1'),('calories','nan'),('fat','inf'),('carbs','abc')):
            values = self.values()
            values[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse_form(values,[],blank_record())
        for rows in ([('','5','')], [('piece','0','')], [('g','2','')], [('piece','1',''),('piece','2','')]):
            with self.assertRaises(ValueError):
                parse_form(self.values(),rows,blank_record())

class UpgradeRecoveryTests(StoreFixture):
    def test_abrupt_process_death_during_populated_upgrade(self):
        store = self.open()
        r = store.get('usda-sr28:01123')
        r['nutrition']['protein'] = 88
        store.save(r)
        added = store.create(custom())
        before = tuple(store.conn.iterdump())
        store.close()
        seed = catalog()
        seed['catalog_version'] = 'upgraded'
        seed['foods'][0]['nutrition']['calories'] = 999
        seed_path = Path(self.temp.name)/'next.json'
        seed_path.write_text(json.dumps(seed))
        code = '''import json,os,sys
from almanac.storage import IngredientStore
def stop(stage):
    if stage=='catalog': os._exit(77)
IngredientStore(sys.argv[1],json.load(open(sys.argv[2])),checkpoint=stop)
'''
        result = subprocess.run([sys.executable,'-c',code,str(self.path),str(seed_path)],cwd=ROOT)
        self.assertEqual(result.returncode,77)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(tuple(conn.iterdump()),before)
        store = self.open(seed)
        self.assertEqual(store.get('usda-sr28:01123')['nutrition']['protein'],88)
        self.assertEqual(store.get(added['id'])['name'],'My food')
        self.assertEqual(store.conn.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_failed_legacy_import_rolls_back_all_rows_and_retries(self):
        path=Path(self.temp.name)/'foods.db'
        with sqlite3.connect(path) as conn:
            conn.execute('CREATE TABLE foods(id INTEGER PRIMARY KEY,name TEXT,category TEXT,calories REAL,protein REAL,carbs REAL,fat REAL)')
            conn.executemany('INSERT INTO foods VALUES (?,?,?,?,?,?,?)',[
                (1,'Snack','Personal',100,1,2,3), (2,'Invalid food','Personal',-1,0,0,0)])
        with self.assertRaises(ValueError):
            self.open(legacy_path=path)
        with sqlite3.connect(path) as conn:
            conn.execute('UPDATE foods SET calories=50 WHERE id=2')
        store=self.open(legacy_path=path)
        self.assertEqual(len(store.list()),171)
        self.assertEqual(store.get('legacy:1')['nutrition']['calories'],100)

    def test_failed_schema_migration_preserves_version_and_records(self):
        store=self.open()
        added=store.create(custom())
        store.conn.execute('ALTER TABLE seed_records DROP COLUMN pinned')
        store.conn.execute('ALTER TABLE seed_records DROP COLUMN available')
        store.conn.execute('PRAGMA user_version=1')
        before=tuple(store.conn.iterdump())
        store.close()
        def fail(stage):
            if stage=='schema': raise RuntimeError('interrupted migration')
        with self.assertRaises(RuntimeError):
            self.open(checkpoint=fail)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(tuple(conn.iterdump()),before)
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],1)
        self.assertEqual(self.open().get(added['id'])['name'],'My food')

