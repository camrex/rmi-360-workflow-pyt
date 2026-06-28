# RMI 360 Config Editor

A standalone, comment-preserving editor for the toolbox's `config.yaml`. Runs
**outside** the ArcGIS Pro Python environment with its own dependencies.

## Why

`config.sample.yaml` is heavily documented with inline comments. Hand-editing is
error-prone, and ordinary YAML tools strip comments. This editor treats the sample
as a **living template**: it loads it with `ruamel.yaml` (round-trip), sets values
onto it, and dumps — so every generated config keeps the sample's comments,
structure, key order, and documented defaults.

## Setup (one-time)

Create an **isolated venv** for the editor and install its deps. This is fully
separate from the ArcGIS Pro Python — installing here never touches the AGP env the
toolbox/scripts use.

```bash
# from the toolbox root
python -m venv config_editor/.venv
config_editor/.venv/Scripts/python -m pip install -r config_editor/requirements.txt
```

(`.venv/` is gitignored.) Use a standalone Python (3.10+), not the ArcGIS Pro one.

## Run

Use the venv's Python. Both commands serve the same UI.

```bash
# A) Browser dev preview (stdlib server, no pywebview needed):
config_editor/.venv/Scripts/python -m config_editor.app.serve   # http://127.0.0.1:8765

# B) Native desktop window (pywebview):
config_editor/.venv/Scripts/python -m config_editor.app.main
```

Run from the toolbox root. New (from sample defaults or a profile) → fill the form →
Validate → Save. Open an existing config to edit; if it predates the current schema
version, an **Upgrade…** button appears. **Preview** shows the live, commented
`config.yaml` that will be written. Repeatable sections (e.g. Custom Fields) have
Add/Remove. The AWS section has **Check AWS auth** (keyring/credentials validation —
needs `boto3`+`keyring`, included in the venv). In the browser preview, file dialogs
become path prompts.

```bash
pytest config_editor/tests/           # 42 tests (core + fields + api)
```

## Status

Headless **core** + **field metadata** + **pywebview GUI** are built. Core and API
are covered by tests (run `pytest config_editor/tests/`); the web UI is vanilla
HTML/CSS/JS (no build step).

```text
config_editor/
  core/
    config_io.py   # ruamel round-trip: load / overlay / render / dump
    fields.py      # sample -> form schema (sections/fields/help/choices)
    paths.py       # locate sample, configs, config_manager, profiles
    profiles.py    # org/user overlays (e.g. RMI Valuation)
    migrate.py     # upgrade an old config to a new schema version + change report
    validate.py    # arcpy-free structural validation (schema_version, completeness…)
  app/
    main.py        # pywebview entry point (python -m config_editor.app.main)
    api.py         # backend the web UI calls (testable, JSON-serializable)
    web/           # index.html, styles.css, app.js (vanilla, no build step)
  profiles/
    rmi_valuation.yaml
  tests/
```

## Annotation convention (self-contained in config.sample.yaml)

All field/section metadata lives in the sample's comments — one source of truth,
no sidecar. Annotations are plain YAML comments and do not affect how the toolbox
loads config:

- A field's **inline comment** is its help text.
- `@choices[a, b, c]` → strict dropdown (value must be one of these).
- `@secret` → password field (keep out of plaintext; prefer keyring).
- `@widget[textarea|number|text|list]` → force a widget (type is otherwise inferred).
- `# @section: Title | description` above a top-level key labels that section.
- `@repeatable @itemlabel[name]` on a map of records (e.g. `custom_fields`,
  `mosaic_fields`) makes it an add/remove collection in the editor; `itemlabel`
  names the field shown per row. The item template (record shape) is derived from
  the existing entries; a record field named `type` gets an ESRI field-type dropdown.

Tags are stripped from the displayed help. To add an enum, just append
`@choices[...]` to that field's comment in the sample.

Repeatable collections are overlaid **wholesale** on save (the user's entry set is
authoritative), so adding/removing entries is reflected exactly — while the rest of
the file keeps its comments.

## Core capabilities (all GUI-agnostic, arcpy-free)

- **New config** — `profiles.new_config_from_profile(profile, skeleton)` →
  sample defaults + profile overlay + edits, fully commented.
- **Edit config** — `config_io.render_from_skeleton(values, sample)` re-flows a
  config through the sample so comments/new keys are restored, then surgical
  value edits (`overlay_values`) change only the touched lines.
- **Upgrade** — `migrate.upgrade(old_values, new_sample, rules)` merges old values
  onto the new version's skeleton, applies rename/remove rules, sets
  `schema_version`, and returns an `UpgradeReport` (added / removed / renamed /
  carried-over).
- **Validate** — `validate.validate_structure(values, skeleton)`: supported
  `schema_version` (read from `config_manager.py` via ast), missing/unknown
  sections, unfilled `<PLACEHOLDER>` values.

## Design guarantees (covered by tests)

- **Idempotent**: `dump(load(x))` is a stable fixed point.
- **Comment-preserving**: all sample comment lines survive a round-trip.
- **Surgical edits**: changing one value changes one line (its inline comment kept).

## Profiles

Bundled profiles ship in `config_editor/profiles/`. User profiles live in
`~/.rmi360/config_profiles/` and shadow bundled ones of the same name.

## Notes

- Do not add `ruamel.yaml` / `pywebview` to the toolbox's top-level
  `requirements.txt`; keep the ArcGIS Pro base environment untouched.
- Secrets (AWS keys) should be routed to `keyring`, not written to plaintext
  `config.yaml` — to be enforced in the GUI layer.
