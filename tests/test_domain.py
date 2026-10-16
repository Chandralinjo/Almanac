import unittest
from dataclasses import replace
from almanac.domain import (Ingredient, Nutrition, Line, Alternative, Phase, Recipe, Choices,
                            MissingConversion, calculate, food_nutrition, combine_totals, recommend)


def food(id='a', calories=200, protein=10, **kwargs):
    return Ingredient(id, id, Nutrition(calories, protein, 20, 5), **kwargs)


def recipe(entries, servings=2, **kwargs):
    return Recipe('r', 'Recipe', servings, (Phase('base', 'Base', tuple(entries)),), **kwargs)


def line(id, ingredient=None, **kwargs):
    return Line(id, ingredient or id, 100, 'g', **kwargs)


class Calculations(unittest.TestCase):
    def test_reference_amount(self):
        self.assertEqual(food_nutrition(food(), 150, 'g').calories.value, 300)
        self.assertEqual(food_nutrition(food(), .15, 'kg').calories.value, 300)

    def test_piece_conversion(self):
        egg = food('egg', conversions={'piece': 53})
        self.assertEqual(food_nutrition(egg, 2, 'piece').calories.value, 212)
        result = food_nutrition(food('egg'), 2, 'piece')
        self.assertIsNone(result.calories.value)
        self.assertEqual(result.calories.issues[0].ingredient_id, 'egg')
        with self.assertRaises(MissingConversion):
            food('egg').factor('piece')

    def test_volume_and_reference_piece(self):
        milk = Ingredient('milk', 'Milk', Nutrition(60, 3, 5, 4), 100, 'ml')
        self.assertEqual(food_nutrition(milk, .5, 'l').calories.value, 300)
        self.assertIsNone(food_nutrition(milk, 1, 'g').calories.value)
        egg = Ingredient('egg', 'Egg', Nutrition(80, 7, 0, 5), 1, 'piece', {'g': 1/53})
        self.assertAlmostEqual(food_nutrition(egg, .106, 'kg').calories.value, 160)

    def test_phase_scaling_and_consumption(self):
        r = Recipe('r', 'Recipe', 2, (Phase('base', 'Base', (line('a'),)),
                                    Phase('sauce', 'Sauce', (line('b'),))))
        c = calculate(r, {'a': food(), 'b': food('b', 400)}, target_servings=3)
        self.assertEqual([x.quantity for x in c.lines], [150, 150])
        self.assertEqual([x.phase_id for x in c.lines], ['base', 'sauce'])
        self.assertEqual(c.whole.calories.value, 900)
        self.assertEqual(c.per_serving.calories.value, 300)
        self.assertEqual(c.consumed(.5).calories.value, 150)

    def test_optional_alternative_and_optional_group(self):
        r = recipe((line('a'), line('garnish', optional=True),
                    Alternative('fat', (line('butter'), line('oil'))),
                    Alternative('topping', (line('nuts'), line('seeds')), optional=True)))
        catalog = {i: food(i) for i in ('a', 'garnish', 'butter', 'oil', 'nuts', 'seeds')}
        c = calculate(r, catalog, Choices(alternatives={'fat': 'oil'}))
        self.assertEqual([x.ingredient_id for x in c.lines], ['a', 'oil'])
        c = calculate(r, catalog, Choices({'garnish', 'topping'}, {'fat': 'butter', 'topping': 'nuts'}))
        self.assertEqual(c.whole.calories.value, 800)
        for choice in (Choices(), Choices(alternatives={'fat': 'wrong'}),
                       Choices(alternatives={'fat': 'oil', 'topping': 'nuts'}),
                       Choices({'oil'}, {'fat': 'oil'})):
            with self.assertRaises(ValueError):
                calculate(r, catalog, choice)

    def test_missing_values_keep_known_totals_and_day_completeness(self):
        r = recipe((line('a'), line('b')))
        c = calculate(r, {'a': food(), 'b': food('b', protein=None)})
        self.assertEqual(c.whole.calories.value, 400)
        self.assertIsNone(c.whole.protein.value)
        self.assertEqual(c.whole.protein.known, 10)
        self.assertEqual(c.whole.fat.value, 10)
        day = combine_totals((c.consumed(.5), food_nutrition(food('egg', conversions={'piece':53}), 2, 'piece')))
        self.assertEqual(day.calories.value, 312)
        self.assertIsNone(day.protein.value)

    def test_missing_conversion_affects_all_nutrients(self):
        c = calculate(recipe((Line('egg', 'egg', 2, 'piece'),)), {'egg': food('egg')})
        self.assertIsNone(c.whole.calories.value)
        self.assertEqual(c.whole.calories.issues[0].line_id, 'egg')

    def test_validation_numbers(self):
        for value in (0, -1, float('nan'), float('inf'), True, '1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                recipe((line('a'),), servings=value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                Line('a', 'a', value, 'g')
        for value in (-1, float('nan'), float('inf'), True):
            with self.assertRaises(ValueError):
                Nutrition(value)
        self.assertEqual(Nutrition(0).calories, 0)
        with self.assertRaises(ValueError):
            food(conversions={'piece':0})
        with self.assertRaises(ValueError):
            food(conversions={'kg':1})
        with self.assertRaises(ValueError):
            food(reference_amount=0)

    def test_invalid_recipes_and_missing_references(self):
        with self.assertRaises(ValueError):
            Alternative('g', (line('a'),))
        with self.assertRaises(ValueError):
            Alternative('g', (line('a', optional=True), line('b')))
        with self.assertRaises(ValueError):
            recipe((line('a'), line('a')))
        with self.assertRaises(ValueError):
            calculate(recipe((line('a', optional=True),)), {})
        for target in (0, -1, float('nan')):
            with self.assertRaises(ValueError):
                calculate(recipe((line('a'),)), {'a':food()}, target_servings=target)

    def test_values_do_not_mutate(self):
        mapping = {'piece':53}
        f = food(conversions=mapping)
        mapping['piece'] = 1
        self.assertEqual(f.factor('piece'), 53)
        with self.assertRaises(TypeError):
            f.conversions['piece'] = 10
        c = calculate(recipe((line('a'),)), {'a': f})
        f = replace(f, nutrition=Nutrition(999, 0, 0, 0))
        self.assertEqual(c.whole.calories.value, 200)


class Recommendations(unittest.TestCase):
    def test_repeated_missing_is_distinct(self):
        r = Recipe('r', 'R', 2, (Phase('p1', 'P1', (line('l1', 'a'),)),
                                Phase('p2', 'P2', (line('l2', 'a'),))))
        self.assertEqual(recommend((r,), ())[0].missing, {'a'})

    def test_shared_alternatives_global_optimum(self):
        r = recipe((Alternative('g1', (line('a1', 'a'), line('b1', 'b'))),
                    Alternative('g2', (line('b2', 'b'), line('c2', 'c')))))
        result = recommend((r,), ())[0]
        self.assertEqual(result.missing, {'b'})
        self.assertEqual(dict(result.choices.alternatives), {'g1':'b1', 'g2':'b2'})
        self.assertEqual(recommend((r,), {'a', 'c'})[0].missing_count, 0)
        self.assertEqual(recommend((r,), (), choices_by_recipe={'r':Choices(alternatives={'g1':'a1','g2':'c2'})})[0].missing_count, 2)

    def test_filter_uses_matching_configuration_and_all_tags(self):
        r = recipe((Alternative('g', (line('butter'), line('oil'))),), tags={'dinner','summer'})
        result = recommend((r,), {'butter'}, tags={'summer'}, ingredient_id='oil')[0]
        self.assertEqual(result.missing, {'oil'})
        self.assertEqual(dict(result.choices.alternatives), {'g':'oil'})
        self.assertFalse(recommend((r,), (), tags={'summer','winter'}))
        self.assertFalse(recommend((r,), (), ingredient_id='egg'))

    def test_optional_filter_requires_selection_and_servings_invariant(self):
        r = recipe((line('a'), line('garnish', optional=True)))
        self.assertEqual(recommend((r,), {'a'})[0].missing_count, 0)
        self.assertFalse(recommend((r,), {'a'}, ingredient_id='garnish'))
        selected = recommend((r,), {'a'}, ingredient_id='garnish', choices_by_recipe={'r':Choices({'garnish'})})[0]
        self.assertEqual(selected.missing, {'garnish'})
        self.assertEqual(recommend((replace(r, servings=6),), {'a'})[0].missing_count, 0)

    def test_stable_ranking(self):
        r = recipe((line('a'),))
        s = replace(r, id='s', name='Another', phases=(Phase('p', 'P', (line('b'),)),))
        self.assertEqual([x.recipe.id for x in recommend((r,s), {'a'})], ['r','s'])
        self.assertEqual([x.recipe.id for x in recommend((r,s), ())], ['s','r'])


if __name__ == '__main__':
    unittest.main()
