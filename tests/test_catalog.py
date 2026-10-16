import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from almanac.catalog import load_catalog
from almanac.domain import food_nutrition
from tools.build_staples import ROOT, build, curate


class CatalogTests(unittest.TestCase):
    def test_catalog_validates_and_has_real_portions(self):
        ingredients = load_catalog(ROOT / 'data/staples.json')
        self.assertEqual(len(ingredients), 169)
        egg = ingredients['usda-sr28:01123']
        self.assertEqual(egg.nutrition.calories, 143)
        self.assertEqual(egg.factor('piece'), 50)
        self.assertEqual(food_nutrition(egg, 2, 'piece').calories.value, 143)
        self.assertEqual(ingredients['usda-sr28:04053'].factor('tbsp'), 13.5)
        self.assertEqual(ingredients['usda-sr28:09003'].factor('piece'), 182)

    def test_common_cooking_staples_are_bundled(self):
        ingredients = load_catalog(ROOT / 'data/staples.json')
        # Representative coverage across the expanded cooking categories.
        for ndb in ('05062', '16426', '16014', '20120', '20035', '20080',
                    '04582', '11216', '11260', '11821', '01053', '02010',
                    '18372', '19165', '12118', '16123'):
            with self.subTest(ndb=ndb):
                self.assertIn('usda-sr28:' + ndb, ingredients)
        self.assertNotEqual(ingredients['usda-sr28:16014'].nutrition,
                            ingredients['usda-sr28:16015'].nutrition)

    def test_reproducible_seed_and_setup_search_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'foods.db'
            json_path = Path(directory) / 'staples.json'
            build(database, json_path)
            self.assertEqual(json_path.read_bytes(), (ROOT / 'data/staples.json').read_bytes())
            with sqlite3.connect(database) as generated, sqlite3.connect(ROOT / 'setup/foods.db') as bundled:
                self.assertEqual(tuple(generated.iterdump()), tuple(bundled.iterdump()))
            with sqlite3.connect(database) as conn:
                self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(conn.execute('SELECT count(*) FROM foods').fetchone()[0], 169)
                self.assertEqual(conn.execute('SELECT name,category,calories,protein,carbs,fat FROM foods WHERE name LIKE ?', ('%Milk, whole%',)).fetchone()[2], 61)
                self.assertEqual(conn.execute('SELECT count(*) FROM foods WHERE source_id IS NULL').fetchone()[0], 0)
            before = database.read_bytes()
            build(database, json_path)
            self.assertEqual(before, database.read_bytes())

    def test_changed_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'usda'
            shutil.copytree(ROOT / 'data/usda', source)
            with (source / 'NUT_DATA.txt').open('a') as stream:
                stream.write('corrupt')
            with self.assertRaisesRegex(ValueError, 'integrity failure'):
                curate(source)

    def test_missing_nutrient_is_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'usda'
            shutil.copytree(ROOT / 'data/usda', source)
            # Simulate a legitimately curated upstream record with no protein.
            path = source / 'NUT_DATA.txt'
            from tools.build_staples import rows
            import csv
            import hashlib
            data = [r for r in rows(path) if (r[0],r[1]) != ('01123','203')]
            with path.open('w',encoding='latin1',newline='') as stream:
                csv.writer(stream, delimiter='^', quotechar='~', quoting=csv.QUOTE_ALL).writerows(data)
            metadata = json.loads((source / 'provenance.json').read_text())
            metadata['files']['NUT_DATA.txt']['subset_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            (source / 'provenance.json').write_text(json.dumps(metadata))
            egg = next(f for f in curate(source)['foods'] if f['source_id']=='01123')
            self.assertIsNone(egg['nutrition']['protein'])


if __name__ == '__main__':
    unittest.main()
