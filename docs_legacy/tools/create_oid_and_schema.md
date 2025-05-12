# 🛠️ Tools: Create OID Schema Template & Create Oriented Imagery Dataset

This stage defines and instantiates the schema for an Oriented Imagery Dataset (OID) used in the RMI Mosaic 360 workflow. It ensures that all required fields — including ESRI standard, Mosaic-specific, linear referencing, and custom fields — are created with consistent names, types, aliases, and optional default values.

---

## 🔧 Components & Tool Mapping

| Toolbox Tool | Script(s) | Description |
|--------------|-----------|-------------|
| **CreateOIDTemplateTool** | `create_oid_template_tool.py` + `build_oid_schema.py` | Generates a reusable schema table in a file GDB from config |
| **CreateOrientedImageryDatasetTool** | `create_oid_tool.py` + `create_oid_feature_class.py` | Uses the template to create a point feature class with the correct schema |

---

## 📌 Purpose

These tools support the structured generation of OID datasets with project-specific fields, such as:
- Standard OID attributes (`CameraHeight`, `AcquisitionDate`, etc.)
- Mosaic-specific fields like `Reel`, `Frame`
- Linear referencing fields like `MP_Pre`, `MP_Num`
- Custom metadata such as `RR` (Railroad Code)

They ensure compatibility with downstream tools like `Add Images to OID`, `Update Metadata`, and `Generate OID Service`.

---

## 🛠 Create OID Schema Template

### ✔️ Parameters

| Parameter | Required | Description |
|----------|----------|-------------|
| `Config File` | ✅ | Path to `config.yaml` with schema structure |

### ⚙️ Output

- A template table in the GDB defined at:  
  `config.oid_schema_template.template.gdb_path`

- Template name (default):  
  `oid_schema_template`

- Saved inside `templates_dir`, e.g.:  
  `templates/templates.gdb/oid_schema_template`

### 🔍 Key Logic (in `build_oid_schema.py`)
- Loads field definitions from:
  - ESRI registry YAML (`field_registry`)
  - `mosaic_fields`, `grp_idx_fields`, `linear_ref_fields`, `custom_fields` in config
- Adds fields using `arcpy.management.AddField`
- Backs up any existing template with a timestamp
- Creates GDB if missing

### ✅ Validation
`validate_tool_build_oid_schema()` in `validate_config.py`:
- Checks required config keys (`field_registry`, `template_name`, etc.)
- Validates all field definitions
- Ensures no duplicates

---

## 🛠 Create Oriented Imagery Dataset

### ✔️ Parameters

| Parameter | Required | Description |
|----------|----------|-------------|
| `Output Oriented Imagery Dataset` | ✅ | Path to new feature class (e.g., `my.gdb/MyOID`) |
| `Spatial Reference` | ⬜️ | Overrides default GCS/VCS from config |
| `Config File` | ✅ | Path to `config.yaml` |
| `Project Folder` | ⬜️ | Optional override for `project_folder` context |

### ⚙️ Output
- Feature class with all OID fields, Z-values enabled
- Created using:  
  `arcpy.oi.CreateOrientedImageryDataset(...)`
- Uses online terrain service for elevation

### 🔍 Key Logic (in `create_oid_feature_class.py`)
- Loads config, resolves paths
- Resolves spatial reference:
  - Defaults to GCS 4326 (horizontal) + VCS 5703 (ellipsoidal height)
- Validates that schema template exists and is current
- Creates the feature class from template

### ✅ Validation
`validate_tool_create_oriented_imagery_dataset()`:
- Confirms `spatial_ref.gcs_horizontal_wkid` and `vcs_vertical_wkid` are defined and resolvable
- Optionally resolves `pcs_horizontal_wkid` if used in other tools (like footprints)

---

## 🧩 Config Sections Used

```yaml
oid_schema_template:
  template:
    templates_dir: "../templates"
    gdb_path: "templates.gdb"
    template_name: "oid_schema_template"
  esri_default:
    field_registry: "../configs/esri_oid_fields_registry.yaml"
    standard: true
    not_applicable: false

mosaic_fields:
  mosaic_reel: ...
  mosaic_frame: ...

linear_ref_fields:
  route_identifier: ...
  route_measure: ...

custom_fields:
  custom1:
    name: "RR"
    expression: "config.project.rr_mark"
```

---

## 🧪 Example Usage

```python
from utils.build_oid_schema import create_oid_schema_template
from utils.create_oid_feature_class import create_oriented_imagery_dataset

# Step 1: Create schema template
create_oid_schema_template(config_file="config.yaml")

# Step 2: Create OID feature class from template
create_oriented_imagery_dataset(
    output_fc_path="C:/GIS/project.gdb/MyOID",
    config_file="config.yaml"
)
```

---

## 📝 Notes
- Schema templates are versionable and reusable
- Run the schema creation tool **once per config change**
- OID creation step is mandatory before using `Add Images to OID`
- Uses `DEM` from ESRI online service by default (can be extended)
