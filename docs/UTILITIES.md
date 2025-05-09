
# 🧰 Shared Utilities – RMI 360 Imaging Workflow Python Toolboxx

This guide explains the utility functions and helpers that power nearly every tool in the Mosaic 360 Toolbox. These are mostly located in the `utils/` directory and are reused across tools, orchestrators, and validation scripts.

---

## 📋 Logging: `log_message()`

### Location: `utils/logging_utils.py`
Unified logging function used throughout the toolbox.

```python
log_message("Process started...", level="info", messages=messages)
```

- Outputs to ArcGIS `messages` if available
- Falls back to `print()` for CLI use
- Supports: `"info"`, `"warn"`, `"error"`, `"success"` levels

---

## ⚙️ Config Load & Resolution

### `prepare_config()`
- Loads and expands `config.yaml`
- Automatically sets `__project_root__`
- Resolves any `config["..."]` paths relative to config location

### `resolve_config()`
- Entry point for tools that need to support various config loading modes

### `get_camera_offset_values()`
- Computes Z offset and camera height based on:
  ```yaml
  camera_offset:
    z: -7.5
    camera_height: 67.5
  ```

---

## 🧠 Expression Resolution

### Location: `utils/expression_utils.py`

Used for resolving dynamic expressions in filenames, metadata, and custom fields.

- `resolve_expression(expr, row, config)` — main resolver
- `resolve_field_expr()` — parses `field.AcquisitionDate.date(...)`
- `resolve_config_expr()` — parses `config.project.slug.strip("-")`

Supports chaining, functions, and date formatting.

---

## 📁 Path Utilities

### `get_log_path(log_key, config)`
- Resolves a log path based on `logs.path` and optional prefix
- Uses `resolve_expression()` to evaluate `logs.prefix`

### `resolve_relative_to_config(config, relative_path)`
- Converts a path like `templates/oid_schema_template` into an absolute path relative to the config file’s directory.

### `resolve_relative_to_pyt(relative_path)`
- Resolves path relative to the toolbox root (e.g., for `templates/`, lambdas, etc.)

---

## ⏳ Progress Feedback

### `Progressor` context manager
```python
with Progressor(label="Uploading images...", total=500) as prog:
    prog.update(i)
```
- Updates ArcGIS Pro’s progress bar if available
- Falls back to simple CLI counter

---

## 🧾 CSV and EXIF Helpers

### `write_csv(path, rows, headers)`
- Writes a list of dicts to a CSV file

### `build_exiftool_args_file()`
- Used to create `.args` batch file for ExifTool
- Automatically quoted and formatted for multiline execution

---

## 📚 Related Documentation

- [Configuration Guide](./CONFIG_GUIDE.md)
- [Tool Guides](./TOOL_GUIDES.md)
