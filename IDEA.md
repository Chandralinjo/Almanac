# App Idea: Personal Recipe Book & Nutrition Tracker

## Overview

A **personal-use, offline Android app** combining a recipe book, ingredient nutrition database, pantry-based recipe recommendations, and daily food/nutrient tracking.

The app should help me maintain my own recipes, calculate their nutritional values, find meals to make with ingredients I have at home, and record what I eat. **All application functionality must work offline.** No account, server, or cloud service is required.

## Core Features

### 1. Ingredient Database

- Browse, search, add, and edit ingredients.
- Store nutritional information in a **defined reference unit** appropriate to the ingredient:
  - **Per 100 g** for foods measured by mass.
  - **Per unit / piece** for appropriate foods, such as eggs and certain fruits or vegetables.
  - **Per volume** (e.g., 100 ml) for liquids, when appropriate.
  - Support practical recipe measurements for spices, herbs, oils, and other ingredients (e.g., teaspoons, tablespoons), where the available data permits reliable conversions.
- Record the reference unit with each nutritional value so calculations remain consistent.
- Reuse ingredient records across recipes, pantry entries, and meal logs.
- Allow corrections and custom additions to the curated starting dataset.
- Support nutritional values from existing publicly available food composition databases; **manually entering an entire basic-food database is not intended**.

### 2. Recipe Creation and Management

- Create, view, edit, and browse personal recipes.
- Each recipe includes:
  - A **list of ingredients** with quantities and units.
  - An ordered **list of instructions**.
  - Free-form **notes**.
  - **Tags** for categorization and filtering (e.g., `#spring`, `#summer`, `#dinner`, `#lunch`, `#healthy`, `#cosy`).
  - The **number of portions / servings** the recipe normally yields.
- **Scale recipes to any desired number of portions**: ingredient quantities automatically adjust proportionally, including quantities in every optional phase.
- Optionally divide a recipe into **phases / components** (e.g., base, sauce, toppings, filling), each with its own ingredients. A simple recipe does not need phases.

### 3. Ingredient Roles, Options, and Branches

A recipe ingredient or ingredient group can be:

- **Required:** Always part of the recipe.
- **Optional:** Included or omitted by choice.
- **Branching / alternatives:** Choose **one of multiple possible ingredients** (e.g., butter **or** olive oil).

- Recipe calculations and the displayed ingredient list must reflect the selected optional ingredients and branch alternatives.
- These choices need to work when scaling a recipe and when deciding what to cook.

### 4. Recipe Nutrition Calculation

- Calculate total energy and nutrients from ingredient quantities, their reference-unit nutrition values, and any supported unit conversions.
- Always include **required** ingredients.
- Include **optional** ingredients only when selected.
- Include only the **chosen alternative** from each branch.
- Recalculate nutrition whenever ingredients, optional choices, alternatives, or portion scaling change.
- Show nutritional values for the **whole recipe and per portion**; scaled ingredient amounts and total nutrition should stay consistent.
- Do not silently treat an unknown nutrient value or an unavailable unit conversion as zero.

### 5. Pantry Inventory and Recipe Recommendations

- Mark which ingredients are currently **available at home**.
- Pantry tracking is **presence/absence only**: no quantities, weights, or stock levels are needed.
- The assumption is that if an ingredient is marked present, there is enough of it for recipe recommendation purposes. If only an insignificant amount remains, I will **unmark** the ingredient.
- Identify recipes that can be made entirely from the available ingredients.
- Show recipes that are nearly possible, highlighting which ingredients would have to be bought.
- Rank recipes by the **fewest distinct missing ingredients** (not the missing weight or quantity).
- Allow filtering by:
  - A **required ingredient in the search** (i.e., recipes that use a specified ingredient).
  - One or more recipe **tags**.
- Respect the required/optional/branching structure when counting missing ingredients:
  - Required ingredients count toward what is needed.
  - Deselected optional ingredients do not count as missing.
  - Alternative branches must account for the selected or available alternative.
- Recipe scaling **does not affect pantry recommendations**, because available quantity is intentionally not tracked.

### 6. Curated Starter Ingredient Database

- Ship the app with a **curated collection of common/basic ingredients**, including their nutritional values and reference units.
- **Build the starter dataset from existing, downloadable food composition data**, selecting, standardizing, and correcting entries rather than hand-entering everything.
- Include the starter data **inside the Android installation**; it must be usable with no internet connection on first launch.
- Copy or initialize the database into **writable, persistent storage on the phone**, so new recipes, ingredient edits, and food logs survive app restarts and upgrades.
- Keep the bundled seed data distinct from the user's writable data in the installation process: do not overwrite personal changes or logs when the app is updated.
- Store source/provenance information for imported ingredient data and follow any applicable licensing/attribution requirements.

**Potential upstream data sources to evaluate (not yet selected):**

| Source | Notes |
| --- | --- |
| [Swiss Food Composition Database](https://www.naehrwertdaten.ch/en/downloads/) | Downloadable Excel data; supports several languages; free download and reuse with source acknowledgment according to its download page. |
| [USDA FoodData Central](https://fdc.nal.usda.gov/download-datasets/) | Downloadable CSV/JSON datasets, including basic foods and nutrient information; check data types and measurement conventions when curating. |
| [ANSES Ciqual 2025](https://entrepot.recherche.data.gouv.fr/dataset.xhtml?persistentId=doi:10.57745/RDMHWY) | Downloadable French food composition data under Etalab Open License 2.0; useful for common European foods. |
| [Open Food Facts](https://world.openfoodfacts.org/data) | Large database of branded food products; potentially useful later, but data completeness varies and ODbL attribution/share-alike terms need consideration if redistributing a curated database. |

This is a **build-time curation process**, not a requirement for the Android app to fetch nutrition information from the internet.

### 7. Meal Logging and Daily Nutrient Tracking

- Record **what I ate and on which day**.
- Log a saved recipe with its chosen optional ingredients/branch alternatives, the number of portions consumed, and the corresponding nutrient totals.
- Calculate and display **daily calories and nutrient intake** by summing meal logs.
- Browse past days and their entries.
- Use the correct per-portion calculations when logging part of a recipe.

### 8. Offline Backup and Phone-to-Phone Transfer

- Support **manual backup export** to a portable file stored or shared using Android's standard file picker / share mechanisms; the app itself does not require internet access.
- Support **backup import / restore** on the same phone or a different Android phone, including a new installation.
- A full backup must include **all user-owned data**: recipes, recipe phases and variations, instructions, notes, tags, custom ingredients and corrections to starter ingredients, pantry selections, meal history, and any relevant app preferences.
- Restore must preserve relationships between recipes, ingredients, variations, and logged meals, so nutrition calculations remain correct.
- The restore workflow must **warn before replacing existing data** and should validate that the backup is compatible and intact before applying it.
- Bundled starter ingredients are installed with the app; backup should preserve **user edits and additions** without requiring the entire unmodified starter dataset to be duplicated.
- No account, cloud backup service, or network connection is required. Files may be transferred between phones by any method the user chooses.

## Key User Flows

1. **Manage ingredients:** Search the local ingredient database, correct an existing entry, or add a missing ingredient with a defined nutrition reference unit.
2. **Create a recipe:** Add ingredients, quantities, units, instructions, notes, tags, optional phases, ingredient roles, and the recipe's usual number of portions.
3. **Adapt a recipe:** Select optional ingredients and alternatives; choose a target number of portions; see adjusted ingredient amounts and nutrition per recipe/per portion.
4. **Find something to cook:** Mark ingredients present in the pantry, filter by recipe ingredient/tags, and see suggestions sorted by the number of ingredients to buy.
5. **Track a meal:** Pick what was eaten, specify recipe variation and portions consumed, assign a date, and review daily nutrient totals.
6. **Back up or migrate:** Export a complete personal-data backup, move the file to another phone, and import it into the app there.

## Platform, Storage, and Design Constraints

- **Platform:** Android.
- **Language:** Python (preferred, based on existing experience).
- **Possible UI framework:** Kivy (to evaluate in implementation planning).
- **Database:** Local SQLite is a suitable initial choice.
- **Connectivity:** **Offline-only at runtime.** Recipe creation, search, recommendation, nutrition calculation, pantry management, and logging must not require a network connection.
- **Starter data:** Included at installation; used to initialize the on-device database.
- **Persistence:** Recipes, ingredients, customizations, pantry selections, and meal history are stored locally on the phone.
- **Portability:** Full offline export/import for backups and migration between Android phones.
- **Audience:** A single personal user, at least initially.

## Additional notes:

1. **Nutrients to track:** Only calories/protein/carbohydrates/fats
2. **Different nutrition units:** Each ingredient with numerical values knows its conversions between numbers and metric (1egg = 53g, 1carrot = 60g)
3. **Recipe recommendations:** Recommendation system does not count optional ingredients as necessary when searching for a recipe based on available ingredients
4. **Recipe recommendations:** Recommendation does not care about quantities. If the user says they have flour, system assumes that they have infinite flour.

## Non-Goals for the First Version

- No login, accounts, social sharing, public recipe marketplace, or cloud synchronization.
- No runtime dependency on external food APIs or other online services.
- No pantry quantity/stock-level management.
- No manual transcription of a complete base ingredient catalog.
- No additional features beyond the confirmed scope without discussion.
