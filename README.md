# Almanac

Offline Android recipe and nutrient tracker using Python/Kivy. The `setup/`
directory contains the phone deployment spike. M1 now provides a UI-independent
domain engine, tested without Kivy, plus a sourced starter catalog of 26 foods.

From the repository root (Python 3.9+; tested with Python 3.12):

```sh
python -m unittest discover -v
python tools/build_staples.py
```

The build reads bundled source rows and needs no network. Data provenance,
nutrient definitions, portion assumptions, and reproduction instructions are in
`data/README.md`. `setup/foods.db` is packaged by the existing Buildozer config.
Run the spike with `cd setup` then `python main.py` in an environment with Kivy.
The previously tested Android toolchain is retained; this milestone does not
claim a new APK or device verification.

## M1 API

`almanac/domain.py` has frozen ingredient, reference-unit, recipe, phase,
individual alternative, choice, calculation, and recommendation models.
Nutrition accepts unknown (`None`) values separately for calories, protein,
carbohydrate, and fat. Reference amounts and recipe quantities are positive;
nutrients can be zero. Nonfinite/negative numbers and contradictory structures
are rejected. A simple recipe uses one phase.

Units are explicit, case-sensitive strings. Metric conversions work within mass
(`g`/`kg`) or volume (`ml`/`l`). Other conversions are ingredient-specific factors
expressed as reference units per input unit. No density or piece weight is
assumed. For example, `conversions={'piece': 53}` maps one piece to 53 g on a
mass-based synthetic ingredient; the real USDA large egg uses 50 g.

```python
from almanac.domain import Line, Phase, Recipe, calculate
from almanac.catalog import load_catalog

foods = load_catalog('data/staples.json')
recipe = Recipe('eggs', 'Two eggs', 1, (
    Phase('main', 'Main', (Line('eggs', 'usda-sr28:01123', 2, 'piece'),)),
))
result = calculate(recipe, foods, target_servings=2)
assert result.whole.calories.value == 286
assert result.consumed(0.5).calories.value == 71.5
```

`Choices` explicitly enables optional entry IDs and maps every active alternative
ID to exactly one option-line ID. Unknown, inactive, and missing choices fail
validation. An optional alternative must be enabled as a group; its options are
individual, non-optional lines. Calculation scales every selected line in every
phase by target/base servings. Results include scaled lines, whole nutrition,
per-serving nutrition, and consumed-serving calculations.

A nutrient total exposes `value` only when complete. Otherwise it exposes `None`,
a `known` subtotal, and issues identifying ingredient/line/nutrient and reason.
An unsupported conversion makes all four nutrients incomplete for that line.
`combine_totals` preserves incomplete status when combining foods/recipes/days.
Results contain immutable numbers and issues, with no live ingredient references;
persisted historical meal snapshots and their editing flows belong to M5.

`recommend` uses presence-only pantry IDs and optimizes the number of distinct
missing ingredients over all required alternatives jointly. Optional entries are
excluded by default. Pass `choices_by_recipe` to respect explicit selections.
All requested tags must match; an ingredient filter must occur in the actual
chosen configuration. As confirmed, optional foods match only when explicitly
selected. Returned choices can be passed directly to `calculate`.

Ties use sorted missing IDs then option IDs; recipes rank by missing count, name,
and ID. The M1 search enumerates branch combinations for exact results, including
shared alternatives. Its worst case is exponential; large recipe collections and
branch-heavy recipes need M4 performance profiling before UI integration.

M2–M6 retain responsibility for persistent user data, ingredient and recipe
screens, pantry UI, meal storage, migration, and backup. No runtime API or network
access is introduced by M1.
