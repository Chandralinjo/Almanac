"""Recipe serialization and raw editor drafts, independent of Kivy."""
from uuid import uuid4
from .domain import Recipe, Phase, Line, Alternative
from .forms import parse_number


def uid():
    return str(uuid4())


def blank_line(ingredient_id=''):
    return dict(id=uid(), ingredient_id=ingredient_id, quantity='100', unit='g', optional=False)


def blank_phase():
    return dict(id=uid(), name='Main', entries=[])


def blank_recipe():
    return dict(id=uid(), name='', servings='1', tags='', instructions='', notes='', phases=[blank_phase()])


def parse_recipe(raw):
    def line(value):
        return Line(value['id'], value['ingredient_id'], parse_number(str(value['quantity']), 'Quantity'),
                    value['unit'].strip(), value.get('optional', False))
    phases = []
    for phase in raw['phases']:
        entries = []
        for entry in phase['entries']:
            entries.append(Alternative(entry['id'], tuple(line(o) for o in entry['options']), entry['optional'])
                           if 'options' in entry else line(entry))
        phases.append(Phase(phase['id'], phase['name'].strip(), tuple(entries)))
    if not isinstance(raw['notes'], str) or not isinstance(raw['instructions'], str):
        raise ValueError('Instructions and notes must be text')
    return Recipe(raw['id'], raw['name'].strip(), parse_number(str(raw['servings']), 'Servings'), tuple(phases),
                  frozenset(t.strip() for t in raw['tags'].split(',') if t.strip()),
                  tuple(raw['instructions'].splitlines()), raw['notes'])


def recipe_record(recipe):
    def line(l):
        return dict(id=l.id, ingredient_id=l.ingredient_id, quantity=str(l.quantity), unit=l.unit, optional=l.optional)
    return dict(id=recipe.id, name=recipe.name, servings=str(recipe.servings), tags=', '.join(sorted(recipe.tags)),
                instructions='\n'.join(recipe.instructions), notes=recipe.notes,
                phases=[dict(id=p.id, name=p.name, entries=[
                    dict(id=e.id, optional=e.optional, options=[line(o) for o in e.options])
                    if isinstance(e, Alternative) else line(e) for e in p.entries]) for p in recipe.phases])
