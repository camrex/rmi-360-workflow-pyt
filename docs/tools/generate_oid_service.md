# 🌐 Tool: Generate OID Service

## 🧰 Tool Name
**10 – Generate OID Service**

---

## 🧭 Purpose

This tool publishes a **web-accessible Oriented Imagery Service** by:

1. Duplicating an existing OID feature class  
2. Rewriting the `ImagePath` field to use AWS-hosted URLs  
3. Publishing the modified OID as a **hosted item** to ArcGIS Online or Portal  

It supports public/private sharing, adds a summary and tags, and places the service in a specified folder.

---

## 🔧 Parameters (ArcGIS Toolbox)

| Parameter | Required | Description |
|----------|----------|-------------|
| `Oriented Imagery Dataset` | ✅ | Input OID feature class (must already contain populated attributes) |
| `Config File` | ⬜️ | Optional override path to `config.yaml` |

---

## 🧩 Script Components

| Script | Responsibility |
|--------|----------------|
| `generate_oid_service_tool.py` | ArcGIS Toolbox UI for parameter collection |
| `generate_oid_service.py` | Core logic: duplicates OID, rewrites paths, publishes via ArcPy |
| `validate_config.py` | Verifies required `aws` and `portal` blocks are present and valid |

---

## 🔁 Workflow Summary

```text
1. Load OID and config
2. Create a copy of the OID (e.g., OID_AWS)
3. Update each ImagePath to its AWS public URL
4. Publish using arcpy.oi.GenerateServiceFromOrientedImageryDataset()
```

Example ImagePath:
```text
https://rmi-orient-img-test.s3.us-east-2.amazonaws.com/RMI25100/Filename.jpg
```

---

## 🔧 AWS and Portal Config

From `config.yaml → aws` and `portal`:

```yaml
aws:
  s3_bucket: "rmi-orient-img-test"
  region: "us-east-2"
  s3_bucket_folder: "config.project.slug"

portal:
  project_folder: "config.project.number"
  share_with: "PRIVATE"
  add_footprint: "FOOTPRINT"
  portal_tags:
    - "config.project.number"
    - "Oriented Imagery"
  summary: "'Oriented Imagery for ' + config.project.number + ' ' + config.project.rr_name + ' - ' + config.project.description"
```

---

## 📤 Output

| Output | Description |
|--------|-------------|
| OID Feature Class | Copied and updated with public AWS URLs |
| Portal Item | Hosted oriented imagery item published using ArcGIS Pro credentials |
| Sharing | Controlled via `portal.share_with` (`PRIVATE`, `ORGANIZATION`, or `PUBLIC`) |

---

## ✅ Validation

Tool-level validator: `validate_tool_generate_oid_service()`:

- Checks:
  - `portal.project_folder`, `portal.share_with`, and `portal_tags` are defined
  - `aws.s3_bucket`, `region`, and `s3_bucket_folder` resolve correctly
  - Optional fields like `summary` are validated and resolved from config

---

## 📝 Notes

- This tool does **not upload images** – images must already be uploaded via `Copy to AWS`
- Publishing requires being signed in to ArcGIS Online or Enterprise Portal in ArcGIS Pro
- The duplicated OID (e.g., `OID_AWS`) is stored in the same GDB as the original
- Safe to re-run: existing hosted services will be replaced if the name matches
