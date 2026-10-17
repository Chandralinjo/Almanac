"""Run separately with Kivy installed and an SDL/OpenGL window (offscreen works)."""
from pathlib import Path
import tempfile
import unittest

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from almanac.ui import FoodLoggerApp
from almanac.storage import IngredientStore
from tools.build_staples import curate


class IngredientScreens(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = FoodLoggerApp()
        self.app.store = IngredientStore(Path(self.directory.name)/'almanac.db', curate())
        self.app.root = self.app.build()
        Window.add_widget(self.app.root)
        Clock.tick()

    def tearDown(self):
        for child in list(Window.children):
            if isinstance(child, Popup):
                child.dismiss(animation=False)
        Window.remove_widget(self.app.root)
        self.app.on_stop()
        self.directory.cleanup()

    def tap(self, text, root=None):
        matches = [w for w in (root or self.app.root).walk() if isinstance(w, Button) and w.text==text]
        self.assertTrue(matches, f'Button not found: {text}')
        matches[0].dispatch('on_release')
        Clock.tick()

    def test_browse_search_detail_and_seed_correction(self):
        self.assertEqual(len(self.app.results.children),169)
        self.app.search.text = 'egG, WHOle'
        self.assertEqual(len(self.app.results.children),1)
        self.app.results.children[0].dispatch('on_release')
        self.assertEqual(self.app.current_id,'usda-sr28:01123')
        self.tap('Edit ingredient')
        self.app.form_inputs['protein'].text = '22,5'
        self.app.conversion_inputs[0][1].text = '53'
        self.tap('Save ingredient')
        self.assertEqual(self.app.screen,'detail')
        saved = self.app.store.get('usda-sr28:01123')
        self.assertEqual(saved['nutrition']['protein'],22.5)
        self.assertEqual(saved['conversions']['piece'],53)

    def test_add_validation_unknown_nutrition_archive_restore(self):
        self.tap('Add ingredient')
        self.tap('Save ingredient')
        self.assertEqual(self.app.screen,'editor')
        self.assertIn('Not saved',self.app.status.text)
        self.app.form_inputs['name'].text='My snack'
        self.app.form_inputs['calories'].text='50'
        self.app.form_inputs['protein'].text='0'
        self.tap('Add conversion')
        for widget,value in zip(self.app.conversion_inputs[0],('piece','20','one small piece')):
            widget.text=value
        self.tap('Save ingredient')
        self.assertEqual(self.app.screen,'detail')
        id = self.app.current_id
        self.assertTrue(id.startswith('custom:'))
        self.assertIsNone(self.app.store.get(id)['nutrition']['carbs'])
        self.tap('Archive ingredient')
        self.tap('Back to ingredients')
        self.app.search.text='My snack'
        self.assertIn('0 ingredients',self.app.status.text)
        self.app.include_archived=True
        self.app.refresh_results()
        self.assertIn('1 ingredients',self.app.status.text)
        self.app.results.children[0].dispatch('on_release')
        self.tap('Unarchive ingredient')
        self.assertFalse(self.app.store.get(id)['archived'])

    def test_cancel_and_android_back_require_discard(self):
        self.app.show_editor('usda-sr28:01123')
        self.app.form_inputs['name'].text='Not saved'
        self.assertTrue(self.app.keyboard(Window,27))
        popup=next(c for c in Window.children if isinstance(c,Popup))
        self.tap('Keep editing',popup)
        self.assertEqual(self.app.screen,'editor')
        Clock.tick()
        self.tap('Cancel')
        popup=next(c for c in Window.children if isinstance(c,Popup))
        self.tap('Discard edits',popup)
        self.assertEqual(self.app.screen,'detail')
        self.assertNotEqual(self.app.store.get('usda-sr28:01123')['name'],'Not saved')

    def test_conversion_removal_and_reset_confirmation(self):
        before = self.app.store.get('usda-sr28:01123')
        self.app.show_editor('usda-sr28:01123')
        self.tap('Remove this conversion')
        self.tap('Save ingredient')
        self.assertEqual(self.app.store.get(before['id'])['conversions'],{})
        self.tap('Reset personal corrections')
        popup=next(c for c in Window.children if isinstance(c,Popup))
        self.tap('Reset corrections',popup)
        self.assertEqual(self.app.store.get(before['id'])['conversions'],before['conversions'])

    def test_recipe_create_reopen_preview_and_draft_recovery(self):
        from almanac.recipes import blank_line, blank_recipe, uid
        from almanac.domain import calculate, Choices
        raw = blank_recipe()
        raw.update(name='Egg choice', servings='2')
        egg = blank_line('usda-sr28:01123')
        egg.update(quantity='2', unit='piece')
        oil = blank_line('usda-sr28:04053')
        butter = blank_line('usda-sr28:01001')
        raw['phases'][0]['entries'] = [egg, dict(id=uid(), optional=False, options=[oil,butter])]
        self.app.recipe_editor(raw=raw)
        self.tap('Save recipe')
        self.assertEqual(self.app.screen,'recipe_detail')
        recipe = self.app.store.get_recipe(raw['id'])
        self.tap('Cooking preview')
        group = recipe.phases[0].entries[1]
        foods = {r['id']:self.app.store.ingredient(r['id']) for r in self.app.store.list()}
        self.assertEqual(self.app.preview_result, calculate(recipe, foods,
                         Choices(alternatives={group.id:group.options[0].id})))
        self.app.recipe_editor(recipe.id)
        fields = [w for w in self.app.body.walk() if hasattr(w,'text') and w.text=='Egg choice']
        fields[0].text = 'Unfinished title'
        self.assertEqual(self.app.store.recipe_draft()['name'],'Unfinished title')
        self.assertTrue(self.app.on_pause())
        self.assertTrue(self.app.keyboard(Window,27))
        self.assertEqual(self.app.screen,'recipes')
        self.tap('Resume unfinished recipe')
        self.assertEqual(self.app.recipe_raw['name'],'Unfinished title')
        self.app.recipe_raw['phases'][0]['entries'][1]['options'] = []
        self.tap('Save recipe')
        self.assertEqual(self.app.screen,'recipe_editor')
        self.assertIn('Not saved',self.app.status.text)
        self.assertEqual(self.app.store.get_recipe(recipe.id),recipe)
        self.tap('Discard draft')
        popup=next(c for c in Window.children if isinstance(c,Popup))
        self.tap('Discard draft',popup)
        self.assertIsNone(self.app.store.recipe_draft())

    def test_recipe_editor_controls_and_preview_choice_updates(self):
        from kivy.uix.spinner import Spinner
        from kivy.uix.textinput import TextInput
        from kivy.uix.togglebutton import ToggleButton
        from almanac.domain import calculate, Choices
        self.app.recipe_editor()
        # Set metadata directly; exercise structure and ingredient selection through controls.
        self.app.recipe_raw['name'] = 'Options'
        self.tap('Add alternative group')
        spinners = [w for w in self.app.body.walk() if isinstance(w,Spinner)]
        for spinner, food in zip(spinners, ('usda-sr28:01123','usda-sr28:04053')):
            spinner.text = next(v for v in spinner.values if food in v)
        self.tap('Add phase')
        self.assertEqual(len(self.app.recipe_raw['phases']),2)
        self.tap('Move phase up')
        toggle = next(w for w in self.app.body.walk() if isinstance(w,ToggleButton))
        toggle.state = 'down'
        self.tap('Save recipe')
        self.assertEqual(self.app.screen,'recipe_detail')
        id = self.app.recipe_id
        self.app.cooking_preview(id)
        self.assertEqual(len(self.app.preview_result.lines),0)
        toggle = next(w for w in self.app.body.walk() if isinstance(w,ToggleButton))
        toggle.state = 'down'
        spinner = next(w for w in self.app.body.walk() if isinstance(w,Spinner))
        spinner.text = spinner.values[1]
        target = next(w for w in self.app.body.walk() if isinstance(w,TextInput))
        target.text = '3'
        recipe = self.app.store.get_recipe(id)
        group = next(e for p in recipe.phases for e in p.entries)
        foods = {r['id']:self.app.store.ingredient(r['id']) for r in self.app.store.list()}
        self.assertEqual(self.app.preview_result, calculate(recipe, foods,
            Choices(frozenset([group.id]), {group.id:group.options[1].id}),3))
        target.text = '0'
        self.assertIsNone(self.app.preview_result)
        self.assertIn('Cannot preview',self.app.status.text)

    def test_production_startup_imports_legacy_and_reopens(self):
        from unittest.mock import PropertyMock, patch
        import shutil
        import sqlite3
        from tools.build_staples import ROOT
        self.app.on_stop()
        Window.remove_widget(self.app.root)
        directory = Path(self.directory.name) / 'production'
        directory.mkdir()
        shutil.copyfile(ROOT / 'setup/foods.db', directory / 'foods.db')
        with sqlite3.connect(directory / 'foods.db') as conn:
            conn.execute("UPDATE foods SET protein=44 WHERE source_id='01123'")
        with patch.object(FoodLoggerApp, 'user_data_dir', new_callable=PropertyMock, return_value=str(directory)):
            self.app = FoodLoggerApp()
            self.app.root = self.app.build()
            Window.add_widget(self.app.root)
            self.assertEqual(self.app.store.path, directory / 'almanac.db')
            self.assertEqual(len(self.app.results.children), 169)
            self.assertEqual(self.app.store.get('usda-sr28:01123')['nutrition']['protein'], 44)
            self.app.store.close()
            self.app.store = None
            self.app.open_store()
            self.assertEqual(len(self.app.store.list()), 169)


if __name__=='__main__':
    unittest.main()
