# USDA staple catalog

26 generic staple foods from USDA National Nutrient Database for Standard
Reference, Release 28 (2015). This is the older SR28 release, not a current
FoodData Central export. It provides a small, fixed, reproducible starting set.

Source documentation: https://www.ars.usda.gov/ARSUserFiles/80400525/Data/SR/SR28/sr28_doc.pdf
Official release archive: https://www.ars.usda.gov/northeast-area/beltsville-md-bhnrc/beltsville-human-nutrition-research-center/mafcl-site-pages/sr11-sr28/
Public-domain USDA data. USDA's current data policy is published at
https://fdc.nal.usda.gov/api-guide/ (CC0/public domain). Credit USDA Agricultural
Research Service, Nutrient Data Laboratory. No third-party application code is
copied from the mirror.

The upstream text records were obtained from https://github.com/maxsu/USDA-SR28
at commit `e9cf1bca802131e6a16f0e3cd35b6361b9026b69`. `usda/provenance.json`
records SHA-256 hashes for both full source files and the checked-in subsets.
`usda/selection.json` explicitly selects NDB IDs and WEIGHT sequence IDs.

To reproduce extraction, check out that mirror commit and run:

```sh
python tools/extract_usda.py /path/to/USDA-SR28
python tools/build_staples.py
```

Normal builds need no network or full upstream checkout. `build_staples.py`
validates source hashes and reads the checked-in rows, producing `staples.json`
and `setup/foods.db`. Rebuilds are byte-for-byte deterministic on the tested
Python/SQLite version. JSON and SQL contents are the portability contract;
SQLite file bytes can differ across SQLite versions.

The four nutrient IDs are 208 (energy, kcal), 203 (protein, g), 205 (carbohydrate
by difference, g), and 204 (total lipid, g), all per 100 g edible food.
Missing source nutrients remain null, never zero. No calorie/macronutrient
reconciliation or density guesses are applied. Raw and cooked rice are distinct
records. Original USDA descriptions retain preparation details.

Conversions use only selected USDA household weights: grams divided by the
source household amount. A `piece` is specifically a large raw egg (50 g), medium
apple (182 g), medium banana (118 g), or medium carrot (61 g). Spoon weights are
food-specific; pepper uses ground pepper, not whole peppercorns. These are source
estimates, not universal sizes. Descriptions are preserved in JSON and SQLite.
There is no automatic mass/volume conversion or inferred teaspoon-to-tablespoon
conversion. Add an explicitly documented mapping when another measure is needed.

The SQLite file is a reproducible M1 seed asset and legacy-migration fixture.
M2 packages `staples.json`, validates it, and reconciles it into a distinct writable
`almanac.db` inside Kivy's persistent app directory. Personal overrides/custom
foods are separate from seed baselines. The earlier phone `foods.db` is imported
once and retained untouched; upgrades now expose the 26-food catalog without
clearing app data. See `docs/M2.md` for the transaction and override rules.
