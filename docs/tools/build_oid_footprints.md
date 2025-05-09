# 🧭 Tool: Build OID Footprints

## 🧰 Tool Name
**08 – Build OID Footprints**

---

## 📌 Purpose

This tool creates **buffer-style multipoint footprints** for each image in an Oriented Imagery Dataset (OID) using ArcGIS Pro’s `Build Oriented Imagery Footprint` geoprocessing tool.

The output is a feature class (e.g., `OID_Footprint`) stored in the same geodatabase or dataset as the original OID. These footprints are used to:

- Visualize camera fields of view
- Generate OID services with visible geometry
- Support spatial queries in ArcGIS Pro and web apps

---

## 🔧 Parameters (ArcGIS Toolbox)

| Parameter | Required | Description |
|----------|----------|-------------|
| `Oriented Imagery Dataset` | ✅ | Input OID feature class |
| `Config File` | ⬜️ | Optional override path to `config.yaml` |

---

## 🧩 Script Components

| Script | Responsibility |
|--------|----------------|
| `build_oid_footprints_tool.py` | ArcGIS Toolbox interface |
| `build_oid_footprints.py` | Core logic using `arcpy.oi.BuildOrientedImageryFootprint` |
| `config.yaml` | Supplies spatial reference, naming logic, and optional transformation |
| `validate_config.py` | Verifies that the spatial reference is valid and resolvable |

---

## ⚙️ Behavior

The tool performs the following:

1. Loads `pcs_horizontal_wkid` from `config.spatial_ref`
2. Optionally uses `spatial_ref.transformation` for accurate projection
3. Creates the output footprint feature class named `OID_Footprint` (e.g., `Imagery_Footprint`)
4. Outputs in the same geodatabase or dataset as the input OID

---

## 📐 Spatial Reference Handling

From `config.yaml`:

```yaml
spatial_ref:
  pcs_horizontal_wkid: "config.project.local_proj_wkid"  # e.g., 6492
  transformation: null  # Optional; may be set for datum conversions
```

These values are resolved using expression evaluation and passed to `arcpy.env.outputCoordinateSystem`.

---

## 📤 Output

| Output | Description |
|--------|-------------|
| `OID_Footprint` | Feature class in same location as OID, using buffer footprint geometry |
| `arcpy.AddMessage` logs | Logged to ArcGIS Pro Messages tab or CLI output |

---

## ✅ Validation

Tool-level validator: `validate_tool_build_oid_footprints()` in `validate_config.py`:

- Ensures `spatial_ref` block exists
- Resolves `pcs_horizontal_wkid` to an integer
- Checks that WKID is positive
- Validates optional `transformation` (if provided) is a string

---

## 📝 Notes

- Uses `footprint_option = "BUFFER"` — suitable for panoramic 360 imagery
- OID must already contain fields such as `CameraHeading`, `HFOV`, and coordinates
- Best run after all geometry corrections and metadata tagging are complete
- Will overwrite existing footprint FC if one already exists with the same name
