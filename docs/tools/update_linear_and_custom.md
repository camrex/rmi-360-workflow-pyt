# 🛤 Tool: Update Linear Referencing and Custom Attributes

## 🧰 Tool Name
**06 – Update Linear and Custom Attributes**

---

## 🧭 Purpose

This tool updates Oriented Imagery Dataset (OID) features by:

1. **Locating each image along a route centerline** using M-values (milepost data)
2. **Populating linear referencing fields** (e.g., `MP_Pre`, `MP_Num`)
3. **Populating custom project-specific attributes** (e.g., `RR`, `ClientCode`, `MP_Label`) based on expressions in `config.yaml`

This step ensures imagery records are **milepost-referenced and metadata-enriched**, allowing consistent filenames, metadata tags, and service attributes.

---

## 🔧 Parameters (ArcGIS Toolbox)

| Parameter | Required | Description |
|----------|----------|-------------|
| `OID Feature Class` | ✅ | Oriented Imagery Dataset with geometry populated |
| `M-Enabled Centerline` | ✅ | Polyline with route calibration (M values) |
| `Route ID Field` | ✅ | Unique identifier for each route in the centerline |
| `Enable Linear Referencing` | ⬜️ | If checked, updates `MP_Pre` and `MP_Num` |
| `Config File` | ✅ | YAML config with field and expression definitions |

---

## 🧩 Components & Logic

| Script | Responsibility |
|--------|----------------|
| `update_linear_and_custom_tool.py` | ArcGIS Pro toolbox tool definition |
| `update_linear_and_custom.py` | Main update logic: field population, config resolution |
| `resolve_expression()` | Applies string-based dynamic expressions using config or field context |
| `get_located_points()` | Runs `LocateFeaturesAlongRoutes` to assign `route_id` and `mp_value` |

---

## 🗂️ Field Sources from `config.yaml`

### Linear Referencing Fields (if enabled)
```yaml
linear_ref_fields:
  route_identifier:
    name: "MP_Pre"
    type: "TEXT"
    length: 6
    alias: "Prefix"
  route_measure:
    name: "MP_Num"
    type: "DOUBLE"
    alias: "Milepost"
```

### Custom Metadata Fields
```yaml
custom_fields:
  custom1:
    name: "RR"
    type: "TEXT"
    length: 6
    alias: "Railroad Code"
    expression: "config.project.rr_mark"
  custom2:
    name: "MP_Label"
    type: "TEXT"
    length: 12
    alias: "MP Label"
    expression: "field.MP_Pre + '-' + field.MP_Num.float(3)"
```

---

## ⚙️ How It Works

```text
1. Load field definitions from config.yaml
2. (If enabled) Locate each point along the centerline using LocateFeaturesAlongRoutes
3. Update `MP_Pre` and `MP_Num` based on route ID and M-value
4. Evaluate expressions to update each custom field
5. Report results to ArcGIS Pro using arcpy.AddMessage
```

---

## 📤 Outputs

- **Linear Reference Fields**:
  - `MP_Pre` → Prefix/line identifier
  - `MP_Num` → Milepost decimal
- **Custom Fields**:
  - Populated using expressions (e.g., `RR`, `MP_Label`, `Client`)

---

## 🧪 Python Usage

```python
from utils.update_linear_and_custom import update_linear_and_custom

update_linear_and_custom(
    oid_fc="C:/GIS/ProjectOID.gdb/OID",
    centerline_fc="C:/GIS/Centerline.gdb/Routes",
    route_id_field="RouteID",
    enable_linear_ref=True,
    config_file="config.yaml"
)
```

---

## ✅ Validation

Validation logic ensures:

- `linear_ref_fields` and `custom_fields` are properly structured
- Types are compatible (`TEXT`, `DOUBLE`, etc.)
- Field names are unique
- Required expressions resolve correctly via `resolve_expression()`

Validators: `validate_tool_update_linear_and_custom()` in `validate_config.py`

---

## 📝 Notes

- Must be run **after geometry and attributes have been added to OID**
- If `enable_linear_ref` is unchecked, only custom fields will be updated
- Expressions can reference `config.project.*` or any other part of the config
- You can define as many custom fields as needed for metadata, tagging, or filenames
