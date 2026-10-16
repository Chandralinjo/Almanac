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
