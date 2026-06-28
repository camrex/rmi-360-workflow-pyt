
# 🧰 RMI 360 Imaging Workflow Python Toolbox

![Version](https://img.shields.io/badge/version-v1.3.0-blue) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) ![ArcGIS Pro](https://img.shields.io/badge/ArcGIS_Pro-3.4|3.5-green) [![Documentation](https://img.shields.io/badge/docs-sphinx-blue)](https://camrex.github.io/rmi-360-workflow-pyt/)

A modular workflow built with ArcGIS Python Toolbox for processing and deploying 360° corridor imagery.

Optimized for Mosaic 51 cameras, with planned support for Insta360. Includes tools for OID creation, AWS publishing, and detailed reporting.

> **❗ ArcGIS Pro Note:** When adding the Toolbox to ArcGIS Pro, you may see a warning icon (❗) upon loading. If this occurs, simply remove the Toolbox and add it again to resolve the issue.

New: The `rmi_360_env_checker.pyt` toolbox is now included to check for all required Python libraries in your ArcGIS Pro environment before running the main tools.

New: **Corridor Thinning (pre-thin)** — the optional `rmi_360_corridor_thinning.pyt` toolbox prefilters panorama points to a manifest so the OID is built for kept images only (instead of thinning after upload). Set `thinning_mode: pre` to drive Add Images To OID from the exported manifest; the post-thin `Filter Distance Spacing` step auto-skips. The default `thinning_mode: post` is unchanged. See [docs/corridor_thinning.md](docs/corridor_thinning.md).

New: **OID Maintenance** — the `rmi_360_oid_maintenance.pyt` toolbox handles out-of-band upkeep of an already-published OID: rewrite ImagePaths, sync image objects between the unsecured and secured S3 buckets, migrate storage (orchestrated), validate ImagePath reachability, and audit OID vs S3. All mutating tools default to **Dry Run**. See [docs_legacy/tools/oid_maintenance.md](docs_legacy/tools/oid_maintenance.md).

New: **Config Editor** — a standalone, comment-preserving editor for `config.yaml` under [config_editor/](config_editor/). The form is generated from `config.sample.yaml` itself, supports org profiles, migrates older configs forward (clean break to schema **1.4.0**), and includes live **Check AWS** auth/bucket validation and **Set AWS Keyring**. It runs in its own isolated virtual environment, separate from the ArcGIS Pro Python.

*Tested using ArcGIS Pro 3.4.3 and 3.5.4.* Be sure to check that your ArcGIS Pro Python Environment has the dependencies in requirements.txt

> ℹ️ The “Oriented Imagery” tools require **Standard or Advanced** licenses. All other functions are available with **Basic** or higher.
> **⚠️ Unit Tests Note:** Many unit tests may currently be broken due to some bug fixes in this release.

---

## 📦 Overview

- 🎞️ Processes captured imagery using Mosaic Processor (with support for MistikaVR or MosaicStitcher)
- 🧭 ArcGIS Oriented Imagery Dataset (OID) creation and enrichment
- 🏷️ EXIF metadata tagging
- 🛣️ Linear referencing support for image positioning
- 🧩 Custom attributing based on config-driven logic
- 🌍 Geocoding of image locations using spatial reference datasets
- 🗂️ File renaming and organization
- ☁️ AWS S3 upload with resumable transfer logic
- 📈 Lambda-based progress monitoring and status dashboard
- 📊 HTML & JSON reporting of process steps and status

> **⚠️ Image Enhancement Removed:** Post-stitch image enhancement has been removed due to technical limitations that caused visible seam lines in panoramic imagery. Enhancement should occur before or during the stitching process for optimal results.

---

## 🧩 Key Features

| Feature                | Description                                                                 |
|------------------------|-----------------------------------------------------------------------------|
| Toolbox Structure      | Built as an ArcGIS `.pyt` Toolbox + modular tool wrappers & utilities       |
| Config-Driven          | YAML-based config with expression resolution and field registries           |
| AWS Integration        | Upload to S3 with TransferManager + Lambda schedule tracking                |
| Resumable Transfers    | Upload interruption protection + log recovery                               |
| HTML & JSON Reporting  | Auto-generated step summaries and final status reports                      |
| Image Metadata Support | Auto tag EXIF metadata + rename by GPS, time, reel, frame, etc.             |

Secured storage status: publishing now passes virtual_cache_directory when aws.secured_delivery.enabled is true.
End-to-end secured-storage serving on Enterprise 12.0 is still blocked by Esri Case #04187998.
Legacy public-URL mode remains the supported path until the Esri issue is resolved.

---

## 📁 Repository Structure

```text
rmi-360-workflow-pyt/
├── rmi_360_workflow.pyt                # Main ArcGIS Python Toolbox
├── rmi_360_env_checker.pyt             # Environment / dependency checker toolbox
├── rmi_360_corridor_thinning.pyt       # Corridor pre-thinning toolbox
├── rmi_360_oid_maintenance.pyt         # OID maintenance + storage migration toolbox
├── config_editor/                      # Standalone config.yaml editor (own venv)
├── configs/
│   ├── config.sample.yaml              # Config template (schema source of truth)
│   └── esri_oid_fields_registry.yaml   # ESRI OID field definitions
├── tools/                              # ArcGIS tool wrappers (workflow, corridor_*, oid_*)
├── utils/                              # Reusable logic
│   ├── corridor/                       # Corridor thinning core (arcpy-free units/identity)
│   ├── manager/                        # Managers (ConfigManager, LogManager, PathManager, ProgressorManager)
│   ├── shared/                         # Shared utilities (oid_storage_paths, oid_storage_migration, ...)
│   └── validators/                     # Validators
├── aws_lambdas/                        # Lambda upload status functions
├── templates/                          # HTML report templates
├── docs/                               # Updated documentation set  (TODO: implement using sphinx)
├── docs_legacy/                        # Full documentation set (tool guides, schema changelog)
└── dev_docs/                           # Future development documentation
```

---

## ✅ Quick Start (Dev Mode)

```bash
git clone https://github.com/camrex/rmi-360-workflow-pyt.git
cd rmi-360-workflow-pyt

# Copy and edit config
cp configs/config.sample.yaml configs/config.yaml
```

---

## 🧭 ArcGIS Pro Environment Setup

1. Open **ArcGIS Pro** and load a project (.aprx).
2. **Verify Python Environment:**
   In the Catalog pane, right-click **Toolboxes** → **Add Toolbox**, and add `rmi_360_env_checker.pyt`.
   Run the **Check Required Python Packages** tool to ensure all required libraries are installed.
   *If any libraries are missing, install them using the Python Command Prompt or the ArcGIS Pro Package Manager before proceeding.*

3. **Add the Workflow Toolbox:**
   Again in the Catalog pane, right-click **Toolboxes** → **Add Toolbox**, and add `rmi_360_workflow.pyt`.

4. **Access the Toolbox Tools:**
   Tools are grouped under:
   - **Setup**
   - **Individual Tools**
   - **Orchestrator**

5. Use individual tools or run the full pipeline with `ProcessMosaic360Workflow`.

---

## 🎞 Mosaic Processor Usage Notes

- The `RunMosaicProcessorTool` wraps the Mosaic CLI (requires Mosaic Processor + MistikaVR).
- It executes two passes:
  - Image rendering and reel fixing
  - GPX integration to embed GPS
- Requires `.grp` calibration file (provided by Mosaic) and raw `.mp4` input folders.

---

## 📖 Documentation

**📚 [Complete Documentation](https://camrex.github.io/rmi-360-workflow-pyt/)** - Comprehensive Sphinx-generated documentation including:

- 🚀 **User Guide**: Installation, configuration, and quick start
- 🛠️ **Tools Documentation**: Detailed tool guides and usage
- ⚙️ **Configuration**: Complete configuration reference
- ☁️ **AWS Integration**: Setup guides and best practices
- 📋 **API Reference**: Full Python API documentation
- 👨‍💻 **Developer Guide**: Contributing and architecture

### Legacy Documentation

> **Note:** The documentation below is being migrated to the new Sphinx system.
> For the most up-to-date information, please refer to the [Complete Documentation](https://camrex.github.io/rmi-360-workflow-pyt/) above.

- 📘 [Toolbox Overview](docs_legacy/TOOL_OVERVIEW.md)
- 🔧 [Tool Guides](docs_legacy/TOOL_GUIDES.md)
- ⚙️ [Configuration Guide](docs_legacy/CONFIG_GUIDE.md)
- 🧰 [Shared Utilities](docs_legacy/UTILITIES.md)
- ☁️ [AWS Setup Guide](docs_legacy/AWS_SETUP_GUIDE.md)
- 📋 [Schema Changelog](docs_legacy/SCHEMA_CHANGELOG.md)
- 📄 [TODO (Developer Tasks)](./TODO.md)
- 📝 [Changelog](./CHANGELOG.md)
- 🛣 [Roadmap](docs_legacy/ROADMAP.md)

### Building Documentation Locally

```bash
# Install documentation dependencies
pip install sphinx sphinx_rtd_theme

# Build documentation
cd docs
make html

# View documentation
# Open docs/_build/html/index.html in your browser
```

---

## 📝 License

Licensed under the [MIT License](./LICENSE).
© 2025 RMI Valuation.

This project integrates with external proprietary software (e.g., ArcGIS Pro, Mosaic Processor, MistikaVR).
Use of those tools is governed by their respective licenses and is not covered by this repository's license.
