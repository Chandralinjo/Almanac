"""Offline domain contracts. No Kivy, database, or network dependency.

Nutrition is per ingredient reference amount, for edible food as described.
Unit maps give reference units per input unit (e.g. piece -> 53 for g).
"""
from dataclasses import dataclass, field
from itertools import product
from math import isfinite
from types import MappingProxyType
from typing import Mapping, Optional, Tuple, Union


NUTRIENTS = ('calories', 'protein', 'carbs', 'fat')
METRIC = {'g': ('mass', 1), 'kg': ('mass', 1000),
          'ml': ('volume', 1), 'l': ('volume', 1000)}


def number(value, label, positive=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not isfinite(value) or value < 0 or (positive and value == 0)):
        raise ValueError(f'{label} must be finite and {"positive" if positive else "nonnegative"}')
    return value


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a nonempty string')


def unique(values, label):
    if len(values) != len(set(values)):
        raise ValueError(f'Duplicate {label}')


@dataclass(frozen=True)
class Nutrition:
    calories: Optional[float] = None
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None

    def __post_init__(self):
        for key in NUTRIENTS:
            if getattr(self, key) is not None:
                number(getattr(self, key), key)


@dataclass(frozen=True)
class Ingredient:
    id: str
    name: str
    nutrition: Nutrition
    reference_amount: float = 100
    reference_unit: str = 'g'
    conversions: Mapping[str, float] = field(default_factory=dict)
    source: str = ''

    def __post_init__(self):
        text(self.id, 'ingredient ID')
        text(self.name, 'ingredient name')
        text(self.reference_unit, 'reference unit')
        number(self.reference_amount, 'reference amount', True)
        if not isinstance(self.nutrition, Nutrition):
            raise ValueError('nutrition must be Nutrition')
        conversions = dict(self.conversions)
        for unit, factor in conversions.items():
            text(unit, 'conversion unit')
            number(factor, 'conversion factor', True)
            intrinsic = metric_factor(unit, self.reference_unit)
            if intrinsic is not None and factor != intrinsic:
                raise ValueError('Conversion contradicts metric/reference unit')
            if unit in METRIC:
                for other, other_factor in conversions.items():
                    relative = metric_factor(unit, other)
                    if relative is not None and factor != relative * other_factor:
                        raise ValueError('Explicit metric conversions contradict each other')
        object.__setattr__(self, 'conversions', MappingProxyType(conversions))

    def factor(self, unit):
        intrinsic = metric_factor(unit, self.reference_unit)
        if intrinsic is not None:
            return intrinsic
        if unit in self.conversions:
            return self.conversions[unit]
        # Permit kg/ml multiples of an explicitly mapped g/ml quantity.
        if unit in METRIC:
            dimension, scale = METRIC[unit]
            for base in ('g', 'ml'):
                if METRIC[base][0] == dimension and base in self.conversions:
                    return scale * self.conversions[base]
        raise MissingConversion(f'{self.id}: no conversion from {unit} to {self.reference_unit}')


def metric_factor(unit, reference):
    if unit == reference:
        return 1
    if unit in METRIC and reference in METRIC and METRIC[unit][0] == METRIC[reference][0]:
        return METRIC[unit][1] / METRIC[reference][1]
    return None


class MissingConversion(ValueError):
    pass


@dataclass(frozen=True)
class Line:
    id: str
    ingredient_id: str
    quantity: float
    unit: str
    optional: bool = False

    def __post_init__(self):
        for value, label in ((self.id, 'line ID'), (self.ingredient_id, 'ingredient ID'), (self.unit, 'unit')):
            text(value, label)
        number(self.quantity, 'quantity', True)
        if not isinstance(self.optional, bool):
            raise ValueError('optional must be bool')


@dataclass(frozen=True)
class Alternative:
    id: str
    options: Tuple[Line, ...]
    optional: bool = False

    def __post_init__(self):
        text(self.id, 'alternative ID')
        object.__setattr__(self, 'options', tuple(self.options))
        if len(self.options) < 2 or any(not isinstance(x, Line) or x.optional for x in self.options):
            raise ValueError('An alternative needs at least two non-optional individual lines')
        unique([x.id for x in self.options], 'alternative option ID')
        unique([x.ingredient_id for x in self.options], 'alternative ingredient')
        if not isinstance(self.optional, bool):
            raise ValueError('optional must be bool')


@dataclass(frozen=True)
class Phase:
    id: str
    name: str
    entries: Tuple[Union[Line, Alternative], ...]

    def __post_init__(self):
        text(self.id, 'phase ID')
        text(self.name, 'phase name')
        object.__setattr__(self, 'entries', tuple(self.entries))
        if any(not isinstance(x, (Line, Alternative)) for x in self.entries):
            raise ValueError('Phase entries must be lines or alternatives')


@dataclass(frozen=True)
class Recipe:
    id: str
    name: str
    servings: float
    phases: Tuple[Phase, ...]
    tags: frozenset = frozenset()
    instructions: Tuple[str, ...] = ()
    notes: str = ''

    def __post_init__(self):
        text(self.id, 'recipe ID')
        text(self.name, 'recipe name')
        number(self.servings, 'servings', True)
        object.__setattr__(self, 'phases', tuple(self.phases))
        object.__setattr__(self, 'tags', frozenset(self.tags))
        object.__setattr__(self, 'instructions', tuple(self.instructions))
        if not self.phases or any(not isinstance(p, Phase) for p in self.phases):
            raise ValueError('Recipe needs phases (use one unnamed component for a simple recipe)')
        if not any(p.entries for p in self.phases):
            raise ValueError('Recipe needs at least one entry')
        unique([p.id for p in self.phases], 'phase ID')
        ids = []
        for p in self.phases:
            for e in p.entries:
                ids.append(e.id)
                if isinstance(e, Alternative):
                    ids.extend(x.id for x in e.options)
        unique(ids, 'recipe entry ID')
        for tag in self.tags:
            text(tag, 'tag')


@dataclass(frozen=True)
class Choices:
    optional_ids: frozenset = frozenset()
    alternatives: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, 'optional_ids', frozenset(self.optional_ids))
        object.__setattr__(self, 'alternatives', MappingProxyType(dict(self.alternatives)))


def selected_lines(recipe, choices):
    """Validate the entire configuration before returning (phase ID, line) pairs."""
    entries = [(p.id, e) for p in recipe.phases for e in p.entries]
    optional = {e.id for _, e in entries if e.optional}
    if not choices.optional_ids <= optional:
        raise ValueError('Unknown or non-optional selection')
    groups = {e.id: e for _, e in entries if isinstance(e, Alternative)}
    active = {key for key, e in groups.items() if not e.optional or key in choices.optional_ids}
    if set(choices.alternatives) != active:
        raise ValueError('Choose exactly one option for every active alternative; no inactive choices')
    for key, option in choices.alternatives.items():
        if option not in {x.id for x in groups[key].options}:
            raise ValueError(f'Invalid option {option} for {key}')
    result = []
    for phase_id, e in entries:
        if e.optional and e.id not in choices.optional_ids:
            continue
        line = next(x for x in e.options if x.id == choices.alternatives[e.id]) if isinstance(e, Alternative) else e
        result.append((phase_id, line))
    return tuple(result)


@dataclass(frozen=True)
class Issue:
    ingredient_id: str
    line_id: str
    nutrient: str
    reason: str


@dataclass(frozen=True)
class NutrientTotal:
    known: float
    issues: Tuple[Issue, ...] = ()

    def __post_init__(self):
        number(self.known, 'known nutrient total')
        object.__setattr__(self, 'issues', tuple(self.issues))

    @property
    def complete(self):
        return not self.issues

    @property
    def value(self):
        return self.known if self.complete else None


@dataclass(frozen=True)
class Totals:
    calories: NutrientTotal
    protein: NutrientTotal
    carbs: NutrientTotal
    fat: NutrientTotal

    def scaled(self, factor):
        number(factor, 'scale', True)
        return Totals(*(NutrientTotal(getattr(self, n).known * factor, getattr(self, n).issues) for n in NUTRIENTS))


def combine_totals(totals):
    totals = tuple(totals)
    return Totals(*(NutrientTotal(sum(getattr(t, n).known for t in totals),
                                tuple(i for t in totals for i in getattr(t, n).issues)) for n in NUTRIENTS))


def food_nutrition(ingredient, quantity, unit, line_id='food'):
    number(quantity, 'quantity', True)
    text(unit, 'unit')
    try:
        multiplier = quantity * ingredient.factor(unit) / ingredient.reference_amount
    except MissingConversion as error:
        return Totals(*(NutrientTotal(0, (Issue(ingredient.id, line_id, n, str(error)),)) for n in NUTRIENTS))
    return Totals(*(NutrientTotal(getattr(ingredient.nutrition, n) * multiplier)
                    if getattr(ingredient.nutrition, n) is not None else
                    NutrientTotal(0, (Issue(ingredient.id, line_id, n, 'Unknown nutrient value'),)) for n in NUTRIENTS))


@dataclass(frozen=True)
class ScaledLine:
    phase_id: str
    line_id: str
    ingredient_id: str
    quantity: float
    unit: str


@dataclass(frozen=True)
class Calculation:
    servings: float
    lines: Tuple[ScaledLine, ...]
    whole: Totals
    per_serving: Totals

    def consumed(self, servings):
        number(servings, 'consumed servings', True)
        return self.per_serving.scaled(servings)


def calculate(recipe, ingredients, choices=None, target_servings=None):
    choices = Choices() if choices is None else choices
    servings = recipe.servings if target_servings is None else target_servings
    number(servings, 'target servings', True)
    # Dangling references are invalid even when hidden by a current choice.
    for phase in recipe.phases:
        for entry in phase.entries:
            for line in entry.options if isinstance(entry, Alternative) else (entry,):
                if line.ingredient_id not in ingredients or ingredients[line.ingredient_id].id != line.ingredient_id:
                    raise ValueError(f'Unknown ingredient {line.ingredient_id}')
    lines = tuple(ScaledLine(p, l.id, l.ingredient_id, l.quantity * servings / recipe.servings, l.unit)
                  for p, l in selected_lines(recipe, choices))
    whole = combine_totals(food_nutrition(ingredients[l.ingredient_id], l.quantity, l.unit, l.line_id) for l in lines)
    return Calculation(servings, lines, whole, whole.scaled(1 / servings))


@dataclass(frozen=True)
class Recommendation:
    recipe: Recipe
    choices: Choices
    missing: frozenset
    ingredient_ids: frozenset

    @property
    def missing_count(self):
        return len(self.missing)


def recommend(recipes, pantry, tags=frozenset(), ingredient_id=None, choices_by_recipe=None):
    """Exact distinct-missing optimization, with deterministic ties.

    Explicit configurations are respected. Otherwise enumerate required branches,
    omitting optional entries. An ingredient filter applies to that actual choice.
    Exhaustive search is intentional for M1; large branch sets need M4 profiling.
    """
    pantry, tags = frozenset(pantry), frozenset(tags)
    choices_by_recipe = {} if choices_by_recipe is None else choices_by_recipe
    recipes = tuple(recipes)
    unique([r.id for r in recipes], 'recipe ID')
    if not set(choices_by_recipe) <= {r.id for r in recipes}:
        raise ValueError('Choices supplied for an unknown recipe')
    results = []
    for recipe in recipes:
        if not tags <= recipe.tags:
            continue
        if recipe.id in choices_by_recipe:
            candidates = (choices_by_recipe[recipe.id],)
        else:
            groups = [e for p in recipe.phases for e in p.entries if isinstance(e, Alternative) and not e.optional]
            candidates = (Choices(alternatives=dict(zip((g.id for g in groups), option_ids)))
                          for option_ids in product(*(tuple(x.id for x in g.options) for g in groups)))
        best, best_key = None, None
        for choices in candidates:
            ids = frozenset(l.ingredient_id for _, l in selected_lines(recipe, choices))
            if ingredient_id is not None and ingredient_id not in ids:
                continue
            missing = ids - pantry
            key = (len(missing), tuple(sorted(missing)), tuple(sorted(choices.alternatives.items())))
            if best_key is None or key < best_key:
                best, best_key = Recommendation(recipe, choices, missing, ids), key
        if best is not None:
            results.append(best)
    return tuple(sorted(results, key=lambda r: (r.missing_count, r.recipe.name.casefold(), r.recipe.id)))
