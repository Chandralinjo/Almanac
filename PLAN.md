- During restore, resolve unchanged matching seed records by ID/hash. For a referenced baseline absent or changed in the installed catalog, retain the backed-up definition as a local pinned baseline and apply its user overrides; do not silently change recipe calculations or discard missing references. Future catalog updates must preserve those pins.
- Validate format/schema compatibility, required files, hashes, record types, numeric ranges, unique IDs, relationship integrity, and completeness of the dependency subset before touching live data. Bound archive size and extraction, and reject unsafe archive paths. Integrity hashes detect corruption, not proof of the file's origin.
- Build and validate a temporary database first. Show a summary and an explicit warning that restore replaces existing data; require confirmation in the app. Keep existing data intact on cancellation, a validation failure, or a failed write.
- Apply restoration atomically using a tested database replacement/transaction strategy. Retain a local recovery copy until successful reopen and verification, and define interruption recovery rather than deleting the old database early.
- Import with the system file picker; export with create-document and share using Android-supported URIs. Handle cancelled pickers, unavailable destinations, revoked URI access, low storage, and malformed files with actionable messages.
- Explain that app uninstall can remove local data and that the user should export a backup before uninstalling or moving phones. Files are portable and unencrypted in the proposed first version; no account or cloud component is introduced.

Acceptance: a backup from one phone restores onto a fresh offline install, including a different seed version, with equivalent recipes, choices, calculations, pantry state, and historical daily totals. A rejected or interrupted restore leaves the original data usable.

## 7. Delivery milestones

### M0 — Decisions and Android feasibility

- [x] Resolve alternative structure, language/catalog focus, and direct food logging; incorporate the answers throughout this plan.
- [x] Record the sole intended device: Samsung Galaxy S25 running Android 16.
- [x] Verify ARM64/API 36 packaging support and test installation on the actual phone.
- [x] Complete the minimal Kivy APK, persistence, picker, export/import, and share spike.
- [ ] Pin a working toolchain and document clean build/install commands.
- [ ] Evaluate data-source availability, license, nutrient definitions, and a small representative sample.

**Exit:** the preferred stack works on Android with offline storage and native file transfer; a primary data source is justified. This is the gate before full UI implementation.

**Immediate next deliverable:** a small installable feasibility APK, reproducible build instructions, and a short Galaxy S25 test checklist. The developer can prepare the build and automated checks; the user must install and exercise it on the phone unless device access is explicitly connected. Record actual device results before marking M0 complete. Evaluate a small USDA basic-food sample during this milestone, then proceed to M1's calculation engine and M2's persistent ingredient catalog once the stack is validated.

### M1 — Domain model and calculation engine

Uses the confirmed individual-ingredient alternative model; use synthetic food fixtures before catalog curation is complete. Pure domain work can start while the Android spike runs.

- [x] Implement ingredient/reference-unit models, explicit conversions, and validation.
- [x] Implement recipe choice validation, phase-aware scaling, nutrition completeness, and consumed-serving calculations.
- [x] Implement presence-only recommendation ranking and consistent ingredient/tag filtering.
- [x] Capture the numerical and ranking examples below as focused regression tests.

**Exit:** independently tested functions produce correct totals and rankings for simple and multi-phase recipes, missing data, optional ingredients, and alternatives.

### M2 — Persistence and curated ingredients

Depends on M0's data selection and M1's ingredient contracts.

- [x] Create versioned SQLite schema/repositories with foreign keys, transactions, migrations, and archive behavior.
- [x] Implement reproducible curation, bundled seed initialization, provenance, and user override precedence.
- [x] Build ingredient browse/search/detail/edit/add screens, including reference units and conversion editing.
- [x] Verify interrupted initialization and upgrade behavior against a populated fixture database.

**Exit:** a fresh offline install has useful foods; custom edits and new records survive process restarts and a tested upgrade.

### M3 — Recipe book and cooking preview

Depends on M1 and M2.

- [x] Build recipe list, detail, and editor with ingredients, instructions, notes, tags, servings, and ordered phases.
- [x] Add the confirmed required/optional/alternative editor; prevent invalid empty or contradictory choice structures.
- [x] Add a cooking preview for target servings and selected choices, with whole/per-serving nutrition and visible missing-data explanations.
- [x] Preserve unfinished edits across routine Android lifecycle events; show validation inline and prevent accidental loss when navigating back.

**Exit:** create, save, reopen, edit, and scale a recipe with phases and alternatives; preview matches the domain calculations exactly.

### M4 — Pantry and meal recommendations

Depends on M3 and M1's ranking engine.

- [ ] Build searchable pantry toggles and persist presence flags.
- [ ] Build can-make and ranked missing-ingredient results with tag and ingredient filters.
- [ ] Show the chosen alternative configuration and carry it into cooking preview.
- [ ] Measure ranking on a representative recipe collection and recipes with many overlapping alternatives.

**Exit:** changes to presence affect rankings immediately; optional ingredients and serving count do not change default missing counts.

### M5 — Meal history and daily totals

Depends on M3 and the snapshot persistence model.

- [ ] Log a recipe variation with consumed servings and a chosen day.
- [ ] Save immutable nutritional snapshots; add edit/delete flows with clear confirmation for deletion.
- [ ] Build day navigation, meal entries, and totals for the four tracked nutrients, including incomplete-day indicators.
- [ ] Add direct ingredient logging with a selected food, positive quantity/unit, and chosen date, using the same snapshot/completeness rules. No recipe creation should be necessary to log an apple or egg.

**Exit:** both foods and recipes appear in daily totals; past totals remain unchanged after editing ingredients, conversion factors, recipes, or catalog data; partial servings and date boundaries work correctly.

### M6 — Complete backup and phone transfer

Depends on M2–M5's final data structures; file integration was already de-risked in M0.

- [ ] Implement consistent export, backup format migrations, dependency subsets, and provenance retention.
- [ ] Implement validation, preview, replacement warning, temporary restore, atomic application, and recovery.
- [ ] Wire document-picker and share actions into settings and test Android lifecycle interruptions.
- [ ] Exercise same-version and cross-catalog-version round trips, corrupted archives, newer unsupported formats, and interrupted writes.

**Exit:** complete restoration succeeds on a clean isolated installation or emulator without internet, and export/import works on the Galaxy S25; failure cases preserve existing data. A second physical phone is not required.

### M7 — First complete release

Depends on all prior milestones.

- [ ] Walk through every key flow in `IDEA.md` in airplane mode, including first launch and backup restoration.
- [ ] Check long recipes, long ingredient names, the Galaxy S25's display/font scaling settings, decimal input, keyboard obstruction, back navigation, rotation, and resume after process death.
- [ ] Verify performance with a representative catalog/history and keep long work off the UI thread.
- [ ] Test upgrading a populated older installation, including migrations and catalog corrections.
- [ ] Build a signed APK, verify permissions, document installation/update/backup steps, and preserve the signing key securely for future updates.
- [ ] Include source attribution and a known-limitations note covering unsupported conversions and any incomplete source values.

**Exit:** all acceptance scenarios pass on the target Android device; no core function depends on a server or network request.

Do not assign calendar estimates until M0 establishes packaging/data effort and the available development time. The main dependency chain is M0 → M1/M2 → M3 → M4/M5 → M6 → M7; M1 domain work and M2 curation can progress independently once their contracts are agreed.

## 8. Verification examples and release criteria

| Area | Concrete scenario and expected result |
| --- | --- |
| Reference amount | A food with 200 kcal per 100 g used at 150 g contributes 300 kcal. |
| Piece mapping | With an explicit 53 g/egg mapping, two eggs contribute nutrition for 106 g. Without it, a mass-based egg record cannot silently accept two pieces. |
| Scaling/logging | A two-serving recipe with 600 kcal scales to three servings and 900 kcal; each serving stays 300 kcal; logging half a serving records 150 kcal. |
| Direct food logging | Log two eggs using the explicit piece mapping without creating a recipe; combine their four nutrient contributions with recipe meals on the selected day. |
| Choices/phases | Deselected optional lines contribute nothing; exactly one active alternative contributes; included lines in every phase scale equally. |
| Missing values | A selected ingredient with unknown protein makes recipe and daily protein incomplete while known calorie/fat totals remain valid. A missing conversion identifies the unresolved ingredient. |
| Distinct missing count | Two phases requiring the same absent ingredient contribute one missing ingredient. |
| Shared alternatives | Two groups choose A/B and B/C, all absent: selecting B in both yields one distinct missing ingredient, not two. |
| Filters | A recipe offering butter or oil matches an oil filter only using an oil-containing configuration; all selected tags must match. |
| Pantry invariance | Optional garnish absence and changing from two to six servings leave the recommendation's missing count unchanged. |
| Historical stability | Log a recipe, then change its ingredient nutrition, piece weight, and servings; the old log and daily totals remain identical until explicitly edited. |
| Upgrade safety | Upgrade with custom ingredients and modified seed entries; user changes, recipes, pantry, and meals remain intact. |
| Transfer safety | Restore a backup into a clean install with a changed seed record; the stored baseline preserves recipe meaning and historical totals without fetching old data online. |
| Restore rejection | Corrupt hashes, dangling IDs, unsupported versions, cancellation, and simulated failure leave the original database usable. |

Use unit tests for domain invariants, SQLite integration tests for migrations/transactions, and round-trip fixtures for export/restore. Use manual Android checks for packaging, permissions, keyboard behavior, content URIs, lifecycle, and real device migration. CI should run domain/integration tests and seed validation; add a reproducible Android build job after M0. Documentation-only planning does not require running application tests that do not yet exist.

The release is complete when the source document's six user flows plus direct food logging are usable offline, all personal data survives restart/upgrade/transfer, incomplete nutrition is visible, and the confirmed product decisions above are reflected in the implementation.
