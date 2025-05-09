# 🛠️ Tool: Add Images to Oriented Imagery Dataset (OID)

## 🧰 Tool Name
**03 – Add Images to OID**

---

## 🧭 Purpose

This tool:
- Adds renamed images to an existing Oriented Imagery Dataset (OID) using `arcpy.oi.AddImagesToOrientedImageryDataset`
- Automatically extracts and calculates the following key attributes:
  - `Reel` and `Frame` from filenames
  - Orientation metadata like `CameraPitch`, `CameraRoll`, `NearDistance`, `FarDistance`
  - Adjusted geometry (`Z`) using camera offset values from `config.yaml`
  - `CameraOrientation` string in ESRI Type 1 format
- Assigns a repeating `GroupIndex` used for display filtering in ArcGIS Pro

This tool is **required** before running metadata tagging or uploading to AWS.

---

## 🔧 Toolbox Parameters

| Parameter | Required | Description |
|----------|----------|-------------|
| `Project Folder` | ✅ | Folder for the current Mosaic 360 project (used to resolve relative paths) |
| `Oriented Imagery Dataset` | ✅ | Target OID feature class (must exist and use schema) |
| `Adjust Z (Apply Offset)` | ⬜️ | Toggles camera height/Z offset correction using values in `config.yaml` |
| `Config File` | ✅ | Full path to `config.yaml` |

---

## 🧩 Scripts & Logic

| Script | Purpose |
|--------|---------|
| `add_images_to_oid_tool.py` | ArcGIS Toolbox wrapper, handles parameter inputs |
| `add_images_to_oid_fc.py` | Runs `AddImagesToOrientedImageryDataset` and validates input |
| `assign_group_index.py` | Assigns 1–4 group index based on `AcquisitionDate` |
| `calculate_oid_attributes.py` | Computes and populates Z, SRS, CameraHeight, Reel, Frame, Orientation |

---

## 📥 Inputs

- **Images** in `panos/original` (folder is resolved from config)
- **OID feature class** created via schema template
- **Filename format** and spatial reference definitions from `config.yaml`

---

## 📤 Outputs

Each image feature in the OID will have:

- **Linked file path** and `Name`
- **X, Y, Z geometry** with adjusted Z (optional)
- **CameraPitch** (default: 90), **CameraRoll** (default: 0)
- **NearDistance** (default: 2), **FarDistance** (default: 50)
- **CameraHeight**, **CameraOrientation** (Type 1 string)
- **Reel** and **Frame** (from filename or `reel_info.json`)
- **GroupIndex** (1–4), used for display filtering

---

## 🧮 Z and Height Calculation

Controlled by:
```yaml
camera_offset:
  z:
    gps_base_height: -7.5
    mount_height: 51.0
    lens_height: 16.5
  camera_height:
    rail_height: 18.5
    vehicle_height: 198.0
    mount_height: 51.0
    lens_height: 16.5
```

Z = geometry Z + offset (if enabled)  
CameraHeight = sum from rail to lens

---

## 🧪 Example Usage (Python)

```python
from utils.add_images_to_oid_fc import add_images_to_oid
from utils.assign_group_index import assign_group_index
from utils.calculate_oid_attributes import enrich_oid_attributes

add_images_to_oid(
    project_folder="D:/Projects/RMI25100",
    oid_fc_path="D:/GIS/RMI25100.gdb/OID",
    config_file="D:/Projects/RMI25100/config.yaml"
)

assign_group_index("D:/GIS/RMI25100.gdb/OID", config_file="D:/Projects/RMI25100/config.yaml")
enrich_oid_attributes("D:/GIS/RMI25100.gdb/OID", config_file="D:/Projects/RMI25100/config.yaml")
```

---

## 🔎 Config Sections Used

- `image_output.folders.original` – source image folder
- `oid_schema_template` – defines fields like `Reel`, `Frame`, `GroupIndex`
- `camera_offset` – used for Z and height calculations
- `spatial_ref` – defines horizontal and vertical WKIDs
- `esri_oid_fields_registry.yaml` – provides defaults like `HFOV`, `VFOV`

---

## ✅ Validation

From `validate_config.py`, the following validators are used:
- `validate_tool_add_images_to_oid`
- `validate_tool_assign_group_index`
- `validate_tool_calculate_oid_attributes`

These validate:
- Required fields in registry (e.g., `CameraPitch`, `CameraOrientation`)
- Properly configured `grp_idx_fields`, `mosaic_fields`, `linear_ref_fields`
- Resolvable WKIDs, Z offsets, and default values

---

## 📝 Notes

- Must be run **after** `Create OID` but **before** metadata tagging
- Ensures consistent filenames and GPS values for later tools
- Use `GroupIndex` to control display density in ArcGIS Pro:
  - 5m spacing → show all
  - 10m spacing → `GroupIndex IN (1,3)` or `(2,4)`
  - 20m spacing → `GroupIndex = 1` (or 2, 3, or 4)
