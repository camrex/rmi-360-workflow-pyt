# 🏷 Tool: Rename and Tag Images

## 🧰 Tool Name
**05 – Rename and Tag Images**

---

## 🧭 Purpose

This tool performs the **final prep step** for 360° imagery, responsible for:

1. **Renaming each image** based on config-defined filename structure and OID attributes  
2. **Updating `Name` and `ImagePath` fields** in the Oriented Imagery Dataset  
3. **Applying EXIF/XMP metadata** using ExifTool batch mode (e.g., GPS, Artist, Railroad, etc.)

It ensures that image files are cleanly named, properly described, and geotagged before cloud upload or sharing.

---

## 🔧 Parameters (ArcGIS Toolbox)

| Parameter | Required | Description |
|----------|----------|-------------|
| `Oriented Imagery Dataset (OID)` | ✅ | Feature class with imagery attributes and paths |
| `Delete Original Files After Rename?` | ⬜️ | If checked, removes the original images |
| `Config File` | ⬜️ | Path to `config.yaml` (defaults to project config if not specified) |

---

## 🧩 Tool Scripts & Roles

| Script | Function |
|--------|----------|
| `rename_and_tag_tool.py` | Tool entrypoint and orchestrator |
| `rename_images.py` | Renames and copies files based on `filename_settings` |
| `apply_exif_metadata.py` | Applies EXIF/XMP metadata using ExifTool batch commands |

---

## 🔁 Workflow Summary

```text
1. Rename Images
   - Generate filename using OID fields + config expressions
   - Copy (or move) file to target folder (e.g., /panos/final)
   - Update OID: Name and ImagePath

2. Apply Metadata
   - Use config-defined EXIF/XMP tags
   - Optionally correct GPS (for flagged GPS_OUTLIER images)
```

---

## 🧪 Example Usage (Python)

```python
from tools.rename_and_tag_tool import execute

execute(
    oid_fc="path/to/OID.gdb/Imagery",
    output_folder="",
    delete_originals=False,
    dry_run=False
)
```

---

## 🖇 Filename Structure

From `config.yaml → image_output.filename_settings`:

```yaml
format: "{project_slug}_{rr}_{mp_pre}{mp_num}_{capture_datetime}_RL{reel}_FR{frame}.jpg"

parts:
  project_slug: "config.project.slug"
  rr: "field.RR"
  mp_pre: "field.MP_Pre"
  mp_num: "field.MP_Num.float(3)"
  capture_datetime: "field.AcquisitionDate.date(%Y%m%dT%H%M%SZ)"
  reel: "field.Reel"
  frame: "field.Frame"
```

---

## 🏷 Metadata Tags

From `config.yaml → image_output.metadata_tags`:

```yaml
Artist: "config.project.company"
Copyright: "'© ' + now.year + ' ' + config.project.company"
Software: "config.camera.software"
Make: "config.camera.make"
Model: "config.camera.model"
SerialNumber: "config.camera.sn"
FirmwareVersion: "config.camera.firmware"
ImageDescription: "field.RR + ' MP ' + field.MP_Pre + '-' + field.MP_Num.float(3)"
XPComment: "config.project.number + ' ' + config.project.rr_name + ' - ' + config.project.description"
XPKeywords:
  - "config.project.company"
  - "360 Imagery"
  - "Panoramic"
  - "Oriented Imagery"
  - "Railroad"
  - "config.project.rr_name"
  - "config.project.rr_mark"
  - "config.camera.model"
  - "field.MP_Pre + '-' + field.MP_Num.float(3)"
  - "config.project.description"
  - "config.project.number"
```

---

## 🧠 Special Behaviors

- Filenames are checked for uniqueness — `_v1`, `_v2` suffixes are added if duplicates exist.
- `QCFlag == 'GPS_OUTLIER'` will trigger **GPSLatitude/Longitude overwrite** in metadata.
- ExifTool args and logs are written to:
  - `logs/exiftool_batch.args`
  - `logs/exiftool_log.txt`

---

## 📤 Outputs

| Output | Description |
|--------|-------------|
| Renamed Image Files | Saved to `/panos/final/` (or as defined in config) |
| Updated OID Fields | `ImagePath`, `Name` |
| EXIF/XMP Metadata | Embedded into each image using ExifTool |

---

## ✅ Validation

Validated via:

- `validate_tool_rename_images()` for filename generation
- `validate_tool_apply_exif_metadata()` for metadata tags and ExifTool path

Checks include:
- Filename placeholders match parts
- Expressions resolve to strings
- Required EXIF tags exist
- ExifTool path is valid

---

## 📝 Notes

- This is the final processing step before upload (`copy_to_aws`) or service generation
- Designed for batch‑safe execution (will not overwrite files silently)
- Can be run multiple times — images are renamed and tagged independently
- Best used after GPS correction and linear referencing are complete
