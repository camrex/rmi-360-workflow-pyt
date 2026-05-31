
# 📂 `PathManager` Documentation

The `PathManager` class standardizes access to all file and folder paths used in the RMI 360 Workflow Python Toolbox.

---

## 📁 Expected Project Structure

```text
rmi-360-workflow-pyt/
├── rmi_360_workflow.pyt
├── templates/
├── configs/
├── aws_lambdas/
├── tools/
├── utils/
└── tests/
```

---

## 🚀 Initialization

```python
from utils.manager.path_manager import PathManager

pm = PathManager(project_base=Path(project_folder), config=config)
```

Optional from file:

```python
pm = PathManager.from_config_file("config.yaml", Path(project_folder))
```

---

## 🔑 Properties Overview

### 🎛️ Script Base Paths (relative to script location)

| Property             | Description                                                                                          |
| -------------------- | ---------------------------------------------------------------------------------------------------- |
| script_base          | Root of the repository (where .pyt lives)                                                            |
| templates            | HTML/GDB templates dir (from oid_schema_template.template.templates_dir)                             |
| configs              | Static config folder                                                                                 |
| lambdas              | AWS Lambda scripts                                                                                   |
| sample_config_path   | Path to config.sample.yaml                                                                           |

### 📁 Project Paths (relative to `project_base`)

| Property       | Description                                             |
| -------------- | ------------------------------------------------------- |
| `project_base` | Root of a project (user-specified)                      |
| `backups`      | Configurable via `orchestrator.backup_folder`           |
| `backup_gdb`   | GDB inside backups (`orchestrator.backup_gdb`)          |
| `logs`         | Project log directory (`logs.path`)                     |
| `report`       | Report output directory (`logs.report_path`)            |

### 🖼️ Image Output Paths

| Property   | Config Key                       | Description          |
| ---------- | -------------------------------- | -------------------- |
| panos      | image_output.folders.parent      | Base pano folder     |
| original   | image_output.folders.original    | Raw images           |
| enhanced   | image_output.folders.enhanced    | Enhanced images      |
| renamed    | image_output.folders.renamed     | Final renamed images |

### 🗂️ OID Schema Paths

| Property             | Config Key                                        | Description              |
| -------------------- | ------------------------------------------------- | ------------------------ |
| `oid_schema_gdb`     | `oid_schema_template.template.gdb_path`           | Output GDB for schema    |
| `oid_field_registry` | `oid_schema_template.esri_default.field_registry` | ESRI field registry path |

### 🌍 Geocoding Paths (Optional)

| Property                | Description                                                                 |
| ----------------------- | --------------------------------------------------------------------------- |
| geoloc500_config_path   | Path to geolocation500.config if exiftool_geodb is "geolocation500"         |
| geocustom_config_path   | Path to geocustom.config if exiftool_geodb is "geocustom"                   |

### ⚙️ Executable Paths

| Property               | Description                                   |
| ---------------------- | --------------------------------------------- |
| `exiftool_exe`         | CLI or path for `exiftool`                    |
| `mosaic_processor_exe` | Full path to Mosaic Processor executable      |
| `mosaic_processor_grp` | Path to `.grp` calibration file               |

---

## 🧪 Validation Utility

### `check_mosaic_requirements()`

Validates that required Mosaic executable and GRP file are set and exist (unless `ignore_missing_files=True`).

```python
pm.check_mosaic_requirements(messages, config, log_func, ignore_missing_files=True)
```

---

## 📎 Usage Example

```python
from utils.manager.path_manager import PathManager

pm = PathManager(project_base="F:/project", config=config)
print(pm.original)  # → project/panos/original
print(pm.templates)  # → script_base/templates
print(pm.exiftool_exe)  # → "exiftool" or absolute path
```

---

## 🧼 Notes

- All paths are resolved with `Path()` and are relative to `script_base` or `project_base`.
- Executable paths return strings (not Paths) to support `subprocess.run()`.
- Optional files (like geocoding configs or GRP) return `None` if unset.
- You should not use `__file__` directly — always let `PathManager` abstract path logic.

---

## 🔍 See Also

- `tests/test_path_manager.py` — Pytest integration test for verifying path resolution.
- `config.sample.yaml` — Defines configurable folders used in this module.
