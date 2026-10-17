from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from almanac.storage import IngredientStore
from almanac.recipes import blank_recipe, blank_line, blank_phase, parse_recipe, recipe_record, uid
from almanac.domain import Choices, calculate
from tools.build_staples import curate


class Recipes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'app.db'
        self.store = IngredientStore(self.path, curate())
        self.raw = blank_recipe()
        self.raw.update(name='Phased eggs', servings='2', tags='breakfast, quick', instructions='Mix\nCook', notes='Test')
        egg = blank_line('usda-sr28:01123')
        egg.update(quantity='2', unit='piece')
        oil = blank_line('usda-sr28:04053')
        butter = blank_line('usda-sr28:01001')
        group = dict(id=uid(), optional=False, options=[oil, butter])
        self.raw['phases'][0]['entries'] = [egg, group]
        phase = blank_phase()
        phase['name'] = 'Finish'
        garnish = blank_line('usda-sr28:01123')
        garnish.update(optional=True, quantity='1', unit='piece')
        phase['entries'] = [garnish]
        self.raw['phases'].append(phase)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_roundtrip_edit_scale_and_archived_references(self):
        recipe = parse_recipe(self.raw)
        group = recipe.phases[0].entries[1]
        choices = Choices(alternatives={group.id: group.options[0].id})
        ingredients = {r['id']: self.store.ingredient(r['id']) for r in self.store.list()}
        expected = calculate(recipe, ingredients, choices, 3)
        self.store.save_recipe(recipe)
        self.store.archive('usda-sr28:01123')
        self.store.close()
        self.store = IngredientStore(self.path, curate())
        reopened = self.store.get_recipe(recipe.id)
        self.assertEqual(recipe, reopened)
        self.assertEqual(expected, calculate(reopened, ingredients, choices, 3))
        self.assertEqual(expected.lines[0].quantity, 3)
        raw = recipe_record(reopened)
        raw['notes'] = 'Updated'
        raw['phases'].reverse()
        self.store.save_recipe(parse_recipe(raw))
        self.assertEqual(self.store.get_recipe(recipe.id).phases[0].name, 'Finish')
        self.assertEqual(len(self.store.list_recipes('quick')), 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.conn.execute('DELETE FROM ingredients WHERE id=?', ('usda-sr28:01123',))

    def test_bad_structures_and_dangling_hidden_option_do_not_replace_saved(self):
        recipe = self.store.save_recipe(parse_recipe(self.raw))
        for change in ('empty', 'duplicate', 'optional_option', 'zero', 'no_phases', 'missing'):
            raw = deepcopy(self.raw)
            group = raw['phases'][0]['entries'][1]
            if change == 'empty': group['options'] = []
            if change == 'duplicate': group['options'][1]['ingredient_id'] = group['options'][0]['ingredient_id']
            if change == 'optional_option': group['options'][0]['optional'] = True
            if change == 'zero': raw['servings'] = '0'
            if change == 'no_phases': raw['phases'] = []
            if change == 'missing': group['options'][1]['ingredient_id'] = 'missing'
            with self.assertRaises((ValueError, KeyError)):
                self.store.save_recipe(parse_recipe(raw))
            self.assertEqual(self.store.get_recipe(recipe.id), recipe)

    def test_raw_invalid_draft_survives_reopen_and_failed_save(self):
        self.raw['servings'] = 'unfinished,'
        self.store.save_recipe_draft(self.raw)
        self.store.close()
        self.store = IngredientStore(self.path, curate())
        self.assertEqual(self.store.recipe_draft(), self.raw)
        with self.assertRaises(ValueError): parse_recipe(self.raw)
        self.assertEqual(self.store.recipe_draft(), self.raw)
        self.raw['servings'] = '2,5'
        self.store.save_recipe(parse_recipe(self.raw))
        self.assertIsNone(self.store.recipe_draft())

    def test_version_two_migration_atomic_and_populated(self):
        for table in ('recipe_ingredients', 'recipes', 'recipe_draft'):
            self.store.conn.execute('DROP TABLE ' + table)
        self.store.conn.execute('PRAGMA user_version=2')
        before = list(self.store.conn.iterdump())
        self.store.close()
        def fail(stage):
            if stage == 'schema': raise RuntimeError('interruption')
        with self.assertRaises(RuntimeError): IngredientStore(self.path, curate(), checkpoint=fail)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(list(conn.iterdump()), before)
        self.store = IngredientStore(self.path, curate())
        self.assertEqual(len(self.store.list()),169)
        self.store.save_recipe(parse_recipe(self.raw))
