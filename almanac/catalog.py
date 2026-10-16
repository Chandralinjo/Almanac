"""Read a curated offline JSON catalog into domain ingredients."""
import json
from pathlib import Path
from .domain import Ingredient, Nutrition


def load_catalog(path):
    catalog = json.loads(Path(path).read_text())
    if catalog['schema_version'] != 1:
        raise ValueError('Unsupported catalog schema')
    result = {}
    for food in catalog['foods']:
        ingredient = Ingredient(food['id'], food['name'], Nutrition(**food['nutrition']),
                                food['reference_amount'], food['reference_unit'],
                                food['conversions'], food['source'])
        if ingredient.id in result:
            raise ValueError('Duplicate ingredient ID')
        result[ingredient.id] = ingredient
    return result
