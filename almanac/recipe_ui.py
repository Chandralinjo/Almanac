"""Recipe book, structured draft editor and domain-backed cooking preview."""
from copy import deepcopy
import sqlite3
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.togglebutton import ToggleButton
from .recipes import blank_recipe, blank_phase, blank_line, parse_recipe, recipe_record, uid
from .domain import Alternative, Choices, calculate, NUTRIENTS


class RecipeScreens:
    def recipe_book(self, query=''):
        self.page('recipes')
        self.body.add_widget(self.recipe_button('Ingredients', self.show_list))
        self.body.add_widget(self.recipe_button('Create recipe', lambda: self.recipe_editor()))
        draft = self.store.recipe_draft()
        if draft:
            self.body.add_widget(self.recipe_button('Resume unfinished recipe', lambda: self.recipe_editor(raw=draft)))
        search = TextInput(text=query, hint_text='Search recipes or tags', multiline=False,
                           size_hint_y=None, height=dp(48))
        self.body.add_widget(search)
        column = self.scroll_column()
        def refresh(*_):
            column.clear_widgets()
            for recipe in self.store.list_recipes(search.text):
                column.add_widget(self.recipe_button(recipe.name, lambda id=recipe.id: self.recipe_detail(id)))
            if not column.children:
                column.add_widget(self.recipe_label('No recipes yet. Create your first recipe.'))
        search.bind(text=refresh)
        refresh()

    def recipe_detail(self, id):
        recipe = self.store.get_recipe(id)
        self.page('recipe_detail')
        self.recipe_id = id
        self.body.add_widget(self.recipe_button('Back to recipes', self.recipe_book))
        self.body.add_widget(self.recipe_button('Edit recipe', lambda: self.recipe_editor(id)))
        self.body.add_widget(self.recipe_button('Cooking preview', lambda: self.cooking_preview(id)))
        column = self.scroll_column()
        column.add_widget(self.recipe_label(f'{recipe.name}\n{recipe.servings:g} servings\nTags: {", ".join(sorted(recipe.tags))}'))
        for phase in recipe.phases:
            column.add_widget(self.recipe_label(phase.name))
            for entry in phase.entries:
                prefix = 'Optional: ' if entry.optional else 'Required: '
                lines = entry.options if isinstance(entry, Alternative) else (entry,)
                descriptions = [f'{l.quantity:g} {l.unit} {self.store.get(l.ingredient_id)["name"]}' for l in lines]
                column.add_widget(self.recipe_label(prefix + ' OR '.join(descriptions)))
        column.add_widget(self.recipe_label('Instructions\n' + '\n'.join(recipe.instructions)))
        column.add_widget(self.recipe_label('Notes\n' + recipe.notes))

    def recipe_editor(self, id=None, raw=None):
        pending = self.store.recipe_draft()
        if raw is None and pending is not None:
            self.recipe_book()
            self.status.text = 'Resume or discard the unfinished recipe before starting another edit.'
            return
        self.recipe_raw = deepcopy(raw if raw is not None else
                                   recipe_record(self.store.get_recipe(id)) if id else blank_recipe())
        self.store.save_recipe_draft(self.recipe_raw)
        self.render_recipe_editor()

    def draft_changed(self):
        try:
            self.store.save_recipe_draft(self.recipe_raw)
            self.status.text = ''
        except (ValueError, OSError, sqlite3.Error) as error:
            self.status.text = f'Draft could not be saved: {error}. Keep this screen open and retry.'

    def draft_field(self, column, obj, key, title, multiline=False):
        column.add_widget(self.recipe_label(title))
        widget = TextInput(text=str(obj[key]), multiline=multiline, size_hint_y=None,
                           height=dp(120 if multiline else 48))
        def changed(_, value):
            obj[key] = value
            self.draft_changed()
        widget.bind(text=changed)
        column.add_widget(widget)
        return widget

    def draft_action(self, action):
        action()
        self.draft_changed()
        self.render_recipe_editor()

    def render_recipe_editor(self):
        self.page('recipe_editor')
        self.body.add_widget(self.recipe_button('Back / keep draft', self.leave_recipe_editor))
        self.body.add_widget(self.recipe_button('Save recipe', self.save_recipe_editor))
        self.body.add_widget(self.recipe_button('Discard draft', self.discard_recipe_editor))
        column = self.scroll_column()
        raw = self.recipe_raw
        for key, title in (('name','Recipe name'), ('servings','Base servings'), ('tags','Tags (comma separated)'),
                           ('instructions','Instructions (one step per line)'), ('notes','Notes')):
            self.draft_field(column, raw, key, title, key in ('instructions','notes'))
        for phase in raw['phases']:
            self.draft_field(column, phase, 'name', 'Phase name (phases cook in displayed order)')
            self.order_controls(column, raw['phases'], phase, 'phase')
            for entry in phase['entries']:
                toggle = ToggleButton(text='Optional' if entry['optional'] else 'Required',
                                      state='down' if entry['optional'] else 'normal', size_hint_y=None, height=dp(48))
                def optional(widget, state, e=entry):
                    e['optional'] = state == 'down'
                    widget.text = 'Optional' if e['optional'] else 'Required'
                    self.draft_changed()
                toggle.bind(state=optional)
                column.add_widget(toggle)
                if 'options' in entry:
                    column.add_widget(self.recipe_label('Choose exactly one of these individual ingredients when cooking:'))
                    for option in entry['options']:
                        self.line_editor(column, option)
                        column.add_widget(self.recipe_button('Remove option', lambda o=option, e=entry:
                            self.draft_action(lambda: e['options'].remove(o))))
                    column.add_widget(self.recipe_button('Add alternative option', lambda e=entry:
                        self.draft_action(lambda: e['options'].append(blank_line()))))
                else:
                    self.line_editor(column, entry)
                self.order_controls(column, phase['entries'], entry, 'entry')
            column.add_widget(self.recipe_button('Add ingredient to phase', lambda p=phase:
                self.draft_action(lambda: p['entries'].append(blank_line()))))
            column.add_widget(self.recipe_button('Add alternative group', lambda p=phase:
                self.draft_action(lambda: p['entries'].append(dict(id=uid(), optional=False,
                                                                 options=[blank_line(), blank_line()])))))
        column.add_widget(self.recipe_button('Add phase', lambda:
            self.draft_action(lambda: raw['phases'].append(blank_phase()))))

    def order_controls(self, column, items, item, title):
        def move(offset):
            index = items.index(item)
            target = index + offset
            if 0 <= target < len(items):
                items[index], items[target] = items[target], items[index]
        column.add_widget(self.recipe_button('Move ' + title + ' up', lambda: self.draft_action(lambda: move(-1))))
        column.add_widget(self.recipe_button('Move ' + title + ' down', lambda: self.draft_action(lambda: move(1))))
        column.add_widget(self.recipe_button('Remove ' + title, lambda: self.draft_action(lambda: items.remove(item))))

    def line_editor(self, column, line):
        # Names are accompanied by stable IDs so similarly named foods remain distinct.
        records = self.store.list(include_archived=True)
        names = {f'{r["name"]} [{r["id"]}]': r['id'] for r in records}
        selected = next((name for name, id in names.items() if id == line['ingredient_id']), 'Select ingredient')
        search = TextInput(hint_text='Filter ingredient choices', multiline=False, size_hint_y=None, height=dp(48))
        column.add_widget(search)
        spinner = Spinner(text=selected, values=tuple(names), size_hint_y=None, height=dp(64))
        search.bind(text=lambda _, value: setattr(spinner, 'values', tuple(n for n in names if value.casefold() in n.casefold())))
        def choose(_, value):
            if value in names:
                line['ingredient_id'] = names[value]
                self.draft_changed()
        spinner.bind(text=choose)
        column.add_widget(spinner)
        self.draft_field(column, line, 'quantity', 'Quantity at base servings')
        self.draft_field(column, line, 'unit', 'Unit (g, ml, piece, or explicit ingredient conversion)')

    def save_recipe_editor(self):
        try:
            recipe = parse_recipe(self.recipe_raw)
            self.store.save_recipe(recipe)
        except (ValueError, KeyError, OSError, sqlite3.Error) as error:
            self.status.text = f'Not saved: {error}'
            return
        self.recipe_detail(recipe.id)
        self.status.text = 'Recipe saved on this device.'

    def leave_recipe_editor(self):
        self.draft_changed()
        # Retaining the draft is the default navigation action; discard is explicit.
        self.recipe_book()
        self.status.text = 'Unfinished recipe kept. Tap Resume unfinished recipe to continue.'

    def discard_recipe_editor(self):
        self.confirm('Discard recipe draft?', 'Permanently discard this unfinished recipe? Saved recipes stay unchanged.',
                     self.clear_and_leave_recipe, action_text='Discard draft')

    def clear_and_leave_recipe(self):
        self.store.clear_recipe_draft()
        self.recipe_book()

    def cooking_preview(self, id):
        recipe = self.store.get_recipe(id)
        self.page('preview')
        self.recipe_id = id
        self.body.add_widget(self.recipe_button('Back to recipe', lambda: self.recipe_detail(id)))
        column = self.scroll_column()
        target = TextInput(text=str(recipe.servings), hint_text='Target servings', multiline=False,
                           size_hint_y=None, height=dp(48))
        column.add_widget(self.recipe_label('Target servings'))
        column.add_widget(target)
        optional, alternatives = set(), {}
        selected_options = {}
        output = None
        def refresh(*_):
            if output is None:
                return
            output.clear_widgets()
            try:
                from .forms import parse_number
                ingredients = {r['id']: self.store.ingredient(r['id']) for r in self.store.list(include_archived=True)}
                result = calculate(recipe, ingredients, Choices(frozenset(optional), alternatives),
                                   parse_number(target.text, 'Target servings'))
                self.preview_result = result
                self.status.text = ''
                for phase in recipe.phases:
                    output.add_widget(self.recipe_label(phase.name))
                    for line in result.lines:
                        if line.phase_id == phase.id:
                            output.add_widget(self.recipe_label(f'{line.quantity:g} {line.unit} {ingredients[line.ingredient_id].name}'))
                for title, totals in (('Whole recipe', result.whole), ('Per serving', result.per_serving)):
                    output.add_widget(self.recipe_label(title))
                    for nutrient in NUTRIENTS:
                        total = getattr(totals, nutrient)
                        unit = 'kcal' if nutrient == 'calories' else 'g'
                        value = f'{total.value:g} {unit}' if total.complete else f'Incomplete (known subtotal {total.known:g} {unit})'
                        output.add_widget(self.recipe_label(f'{nutrient.capitalize()}: {value}'))
                        for issue in total.issues:
                            output.add_widget(self.recipe_label(f'{ingredients[issue.ingredient_id].name} · line {issue.line_id}: {issue.reason}'))
            except (ValueError, KeyError, sqlite3.Error) as error:
                self.preview_result = None
                self.status.text = f'Cannot preview: {error}'
        for phase in recipe.phases:
            column.add_widget(self.recipe_label(phase.name + ' choices'))
            for entry in phase.entries:
                if entry.optional:
                    toggle = ToggleButton(text='Include optional ingredient/group', size_hint_y=None, height=dp(48))
                    def include(_, state, e=entry):
                        if state == 'down':
                            optional.add(e.id)
                            if isinstance(e, Alternative):
                                alternatives[e.id] = selected_options[e.id]
                        else:
                            optional.discard(e.id)
                            alternatives.pop(e.id, None)
                        refresh()
                    toggle.bind(state=include)
                    column.add_widget(toggle)
                if isinstance(entry, Alternative):
                    options = {f'{l.quantity:g} {l.unit} {self.store.get(l.ingredient_id)["name"]} [{l.id}]': l.id for l in entry.options}
                    selected_options[entry.id] = entry.options[0].id
                    if not entry.optional:
                        alternatives[entry.id] = entry.options[0].id
                    spinner = Spinner(text=next(iter(options)), values=tuple(options), size_hint_y=None, height=dp(64))
                    def select(_, value, e=entry, opts=options):
                        selected_options[e.id] = opts[value]
                        if not e.optional or e.id in optional:
                            alternatives[e.id] = opts[value]
                        refresh()
                    spinner.bind(text=select)
                    column.add_widget(spinner)
                elif entry.optional:
                    column.add_widget(self.recipe_label(self.store.get(entry.ingredient_id)['name']))
        output = self.recipe_output = BoxLayout(
            orientation='vertical', size_hint_y=None, spacing=dp(8))
        output.bind(minimum_height=output.setter('height'))
        column.add_widget(output)
        target.bind(text=refresh)
        refresh()
