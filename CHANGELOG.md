# 📦 CHANGELOG

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),  
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] – 2025-05-08
### 🎉 Initial Stable Release – RMI 360 Imaging Workflow Python Toolbox v1.0.0
#### 🚀 Major Highlights
- Modular ArcGIS Toolbox structure with Setup, Individual Tools, Reporting, and Orchestrator categories.
- New master workflow runner (`Process360Workflow`) supports end-to-end execution, step control, backups, and metrics.
- Centralized and deeply nested `config.yaml` with schema validation, field registry, and dynamic expression support.
- Field-level schema enforcement powered by `esri_oid_fields_registry.yaml`.

#### 📸 Imagery & Metadata Processing
- OpenCV-based image enhancement pipeline with CLAHE, white balance, sharpening, and EXIF preservation.
- EXIF/XMP metadata tagging via `apply_exif_metadata.py` driven by `metadata_tags` config block.
- Standardizes frame numbering (6-digit) via `pad_mosaic_frame_numbers.py`.

#### 🛰️ GPS, Schema, and Geometry
- Advanced GPS outlier detection with route-deviation logic and optional automatic correction.
- Z-offset and camera height logic computed from configurable lever-arm offsets.
- Schema template creation and OID feature class population fully driven by field registry.

#### ☁️ Cloud & Web Integration
- S3 upload pipeline rewritten with `TransferManager`, resumable uploads, real-time progress logs, and cancel file support.
- Lambda-based upload dashboard writes `status.html` with live metrics.
- Generates hosted OID service using AWS-based image paths and AGOL integration.

#### 📊 Reporting & Logging
- Full project report generation with charts, metrics, reel statistics, and export logs.
- JSON-based intermediate report structure enables reruns and backup-safe reporting.

#### 🛠 Developer Tools
- `expression_utils.py`: powerful syntax engine supporting field/config/constant expressions.
- `validate_config.py`: extensible tool-by-tool config validator with field and type checking.
- `progressor_utils.py`: shared progress manager for both CLI and ArcGIS Pro tools.

---
