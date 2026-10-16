"""M2 ingredient catalog screens. All persisted values pass domain validation."""
import json
from pathlib import Path
import sqlite3

from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from .forms import blank_record, parse_form
from .storage import IngredientStore

ROOT = Path(__file__).resolve().parents[1]


def fmt(value):
    return '' if value is None else f'{value:g}'


def label(text):
    widget = Label(text=text, size_hint_y=None, halign='left', valign='middle')
    widget.bind(width=lambda w, width: setattr(w, 'text_size', (max(1, width), None)),
                texture_size=lambda w, size: setattr(w, 'height', size[1] + dp(16)))
    return widget


def button(text, action, height=48):
    widget = Button(text=text, size_hint_y=None, height=dp(height))
    widget.bind(on_release=lambda *_: action())
    return widget


class FoodLoggerApp(App):
    # Retain the spike's class name: Kivy derives the existing data directory from it.
    def build(self):
        self.title = 'Almanac — Ingredients'
        Window.softinput_mode = 'below_target'
        Window.bind(on_keyboard=self.keyboard)
        self.screen = 'list'
        self.query = ''
        self.include_archived = False
        self.form_inputs = {}
        self.conversion_inputs = []
        self.shell = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(8))
        self.shell.add_widget(label('Almanac · Ingredients'))
        self.status = label('')
        self.shell.add_widget(self.status)
        self.body = BoxLayout(orientation='vertical', spacing=dp(8))
        self.shell.add_widget(self.body)
        if getattr(self, 'store', None) is None:
            self.open_store()
        else:
            self.show_list()
        return self.shell

    def open_store(self):
        try:
            catalog = json.loads((ROOT / 'data/staples.json').read_text())
            directory = Path(self.user_data_dir)
            self.store = IngredientStore(directory / 'almanac.db', catalog, directory / 'foods.db')
            self.show_list()
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            self.status.text = f'Could not open your ingredients: {error}. Check free storage and retry.'
            self.body.clear_widgets()
            self.body.add_widget(button('Retry opening database', self.open_store))

    def page(self, screen):
        self.screen = screen
        self.status.text = ''
        self.body.clear_widgets()

    def scroll_column(self):
        scroll = ScrollView(do_scroll_x=False)
        column = BoxLayout(orientation='vertical', spacing=dp(8), size_hint_y=None)
        column.bind(minimum_height=column.setter('height'))
        scroll.add_widget(column)
        self.body.add_widget(scroll)
        return column

    def show_list(self):
        self.page('list')
        self.search = TextInput(text=self.query, hint_text='Search foods or categories',
                                multiline=False, do_wrap=False, size_hint_y=None, height=dp(48))
        self.search.bind(text=self.refresh_results)
        self.body.add_widget(self.search)
        actions = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        actions.add_widget(button('Add ingredient', lambda: self.show_editor()))
        toggle = ToggleButton(text='Include archived', state='down' if self.include_archived else 'normal')
        toggle.bind(state=self.toggle_archived)
        actions.add_widget(toggle)
        self.body.add_widget(actions)
        self.results = self.scroll_column()
        self.refresh_results()

    def toggle_archived(self, widget, state):
        self.include_archived = state == 'down'
        self.refresh_results()

    def refresh_results(self, *_):
        self.query = self.search.text
        try:
            records = self.store.list(self.query, self.include_archived)
            self.results.clear_widgets()
            self.status.text = f'{len(records)} ingredients. Tap one for details.'
            for record in records:
                nutrition = record['nutrition']
                kcal = 'unknown kcal' if nutrition['calories'] is None else fmt(nutrition['calories']) + ' kcal'
                state = ' [archived]' if record['archived'] else ''
                entry = button(f"{record['name']}{state}\n{kcal} / {fmt(record['reference_amount'])} {record['reference_unit']}",
                               lambda id=record['id']: self.show_detail(id), 88)
                entry.halign = 'left'
                entry.bind(width=lambda w, width: setattr(w, 'text_size', (max(1,width-dp(16)), None)))
                self.results.add_widget(entry)
            if not records:
                self.results.add_widget(label('No matches. Try another search or add an ingredient.'))
        except (ValueError, sqlite3.Error) as error:
            self.status.text = f'Could not read ingredients: {error}'

    def show_detail(self, id):
        try:
            record = self.store.get(id)
        except (KeyError, ValueError, sqlite3.Error) as error:
            self.status.text = f'Could not open ingredient: {error}'
            return
        self.page('detail')
        self.current_id = id
        self.body.add_widget(button('Back to ingredients', self.show_list))
        column = self.scroll_column()
        column.add_widget(label(record['name']))
        column.add_widget(label(record['category'] or 'No category'))
        if record['archived']:
            column.add_widget(label('Archived: hidden from the default ingredient list.'))
        column.add_widget(label(f"Nutrition per {fmt(record['reference_amount'])} {record['reference_unit']} (edible portion):"))
        for nutrient, unit in (('calories','kcal'), ('protein','g'), ('carbs','g'), ('fat','g')):
            value = record['nutrition'][nutrient]
            column.add_widget(label(f"{nutrient.capitalize()}: {'Unknown' if value is None else fmt(value) + ' ' + unit}"))
        column.add_widget(label('Additional measurements'))
        for unit, factor in record['conversions'].items():
            description = record['conversion_descriptions'].get(unit, '')
            column.add_widget(label(f"1 {unit} = {fmt(factor)} {record['reference_unit']}" + (f' ({description})' if description else '')))
        if not record['conversions']:
            column.add_widget(label('No extra conversions. Metric units convert within mass or volume only.'))
        source = record['source'] or 'Personal ingredient'
        column.add_widget(label('Source: ' + source + (f"\nSource ID: {record['source_id']}" if record['source_id'] else '')))
        if record['is_seed']:
            column.add_widget(label('Starter ingredient' + (' · personally corrected' if record['modified'] else '') +
                                    f"\nCatalog: {record['catalog_version']}"))
            if record['pinned']:
                column.add_widget(label('Kept the earlier baseline to preserve your measurements and corrections.'))
            elif not record['catalog_available']:
                column.add_widget(label('Retained from an earlier catalog; your data is preserved.'))
        column.add_widget(button('Edit ingredient', lambda: self.show_editor(id)))
        column.add_widget(button('Unarchive ingredient' if record['archived'] else 'Archive ingredient',
                                 lambda: self.change_archive(id, not record['archived'])))
        if record['is_seed'] and record['modified']:
            column.add_widget(button('Reset personal corrections', lambda: self.confirm(
                'Reset corrections?', 'Replace your corrected values with this ingredient’s stored starter baseline?',
                lambda: self.reset_ingredient(id))))

    def change_archive(self, id, archived):
        try:
            self.store.archive(id, archived)
            self.show_detail(id)
        except (ValueError, sqlite3.Error) as error:
            self.status.text = f'Could not change archive state: {error}'

    def reset_ingredient(self, id):
        try:
            self.store.reset(id)
            self.show_detail(id)
        except (ValueError, sqlite3.Error) as error:
            self.status.text = f'Could not reset corrections: {error}'

    def show_editor(self, id=None):
        record = blank_record() if id is None else self.store.get(id)
        self.page('editor')
        self.editing_id = id
        self.original = record
        actions = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        actions.add_widget(button('Cancel', self.leave_editor))
        actions.add_widget(button('Save ingredient', self.save_editor))
        self.body.add_widget(actions)
        self.form = self.scroll_column()
        self.form.add_widget(label('Add ingredient' if id is None else 'Edit ingredient'))
        self.form_inputs = {}
        for key, title in (('name','Name'), ('category','Category'),
                           ('reference_amount','Nutrition reference amount'), ('reference_unit','Reference unit (g, ml, piece, …)')):
            self.add_field(key, title, record[key])
        self.form.add_widget(label('Enter nutrition for exactly the reference amount above. Blank means unknown; enter 0 only for a known zero.'))
        for key, title in (('calories','Energy (kcal)'), ('protein','Protein (g)'), ('carbs','Carbohydrates (g)'), ('fat','Fat (g)')):
            self.add_field(key, title, fmt(record['nutrition'][key]))
        self.form.add_widget(label('Conversions: 1 input unit = the entered amount of your reference unit. Example for g: piece = 50. Include size/preparation in the description.'))
        self.conversion_box = BoxLayout(orientation='vertical', spacing=dp(8), size_hint_y=None)
        self.conversion_box.bind(minimum_height=self.conversion_box.setter('height'))
        self.form.add_widget(self.conversion_box)
        self.conversion_inputs = []
        for unit, factor in record['conversions'].items():
            self.add_conversion(unit, fmt(factor), record['conversion_descriptions'].get(unit, ''))
        self.form.add_widget(button('Add conversion', self.add_conversion))
        self.initial_form = self.form_state()

    def add_field(self, key, title, value):
        self.form.add_widget(label(title))
        widget = TextInput(text=fmt(value) if isinstance(value, (int,float)) else str(value),
                           multiline=False, do_wrap=False, size_hint_y=None, height=dp(48))
        self.form_inputs[key] = widget
        self.form.add_widget(widget)

    def add_conversion(self, unit='', factor='', description=''):
        box = BoxLayout(orientation='vertical', spacing=dp(4), size_hint_y=None, height=dp(244))
        row = []
        for value, hint in ((unit,'Input unit, e.g. piece'), (factor,'Amount in reference units, e.g. 50'),
                            (description,'Description, e.g. large egg, edible portion')):
            widget = TextInput(text=value, hint_text=hint, multiline=False, do_wrap=False, size_hint_y=None, height=dp(48))
            box.add_widget(widget)
            row.append(widget)
        box.add_widget(button('Remove this conversion', lambda: self.remove_conversion(box, row)))
        self.conversion_inputs.append(row)
        self.conversion_box.add_widget(box)

    def remove_conversion(self, box, row):
        self.conversion_inputs.remove(row)
        self.conversion_box.remove_widget(box)

    def form_state(self):
        return ({k:v.text for k,v in self.form_inputs.items()},
                [tuple(w.text for w in row) for row in self.conversion_inputs])

    def save_editor(self):
        try:
            values, rows = self.form_state()
            record = parse_form(values, rows, self.original)
            saved = self.store.create(record) if self.editing_id is None else self.store.save(record)
        except (ValueError, KeyError, OSError, sqlite3.Error) as error:
            self.status.text = f'Not saved: {error}'
            return
        self.show_detail(saved['id'])
        self.status.text = 'Ingredient saved on this device.'

    def leave_editor(self):
        def leave():
            self.show_list() if self.editing_id is None else self.show_detail(self.editing_id)
        if self.form_state() != self.initial_form:
            self.confirm('Discard edits?', 'Your changes have not been saved.', leave)
        else:
            leave()

    def confirm(self, title, message, action):
        content = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(8))
        content.add_widget(label(message))
        popup = Popup(title=title, content=content, size_hint=(.95, None), height=dp(290), auto_dismiss=False)
        content.add_widget(button('Keep editing' if self.screen == 'editor' else 'Cancel', popup.dismiss))
        def proceed():
            popup.dismiss()
            action()
        content.add_widget(button('Discard edits' if self.screen == 'editor' else 'Reset corrections', proceed))
        popup.open()

    def keyboard(self, window, key, *_):
        if key not in (27,1001):
            return False
        if self.screen == 'editor':
            self.leave_editor()
            return True
        if self.screen == 'detail':
            self.show_list()
            return True
        return False

    def on_pause(self):
        return True

    def on_stop(self):
        Window.unbind(on_keyboard=self.keyboard)
        if getattr(self, 'store', None) is not None:
            self.store.close()
            self.store = None
