# 📦 CHANGELOG

*All notable changes to this project will be documented in this file.*

> **📝 Maintenance Note**: Please update this CHANGELOG with significant changes, new features, bug fixes, and breaking changes. Follow the existing format with clear categories (Added, Changed, Fixed, Removed, etc.).

## [v1.3.0] - 2025-10-30 - Major Architecture Enhancement & AWS Integration
*Combined release including AWS/Local infrastructure (1.2.0) and Enhancement Removal (1.3.0)*

### 🎯 **BREAKING CHANGES**
> ⚠️ **Image Enhancement Removed**: Complete removal of OpenCV-based image enhancement functionality due to seam line artifacts in panoramic imagery.

#### Removed
- **Enhancement Pipeline**: Complete removal of post-stitch image enhancement functionality
  - Deleted: `tools/enhance_images_tool.py`, `utils/enhance_images.py`, `utils/validators/enhance_images_validator.py`
  - Deleted: `tests/test_enhance_images.py`, `docs_legacy/tools/enhance_images.md`
- **Configuration Section**: `image_enhancement` section completely removed from config schema
- **Workflow Step**: Reduced workflow from 16 to 15 steps (removed step 9: enhance_images)
- **Enhanced Folder Structure**: No longer creates or references `enhanced/` image folders

#### Changed - Enhancement Removal
- **Schema Version**: Updated to `1.3.0` to reflect breaking configuration changes
- **Workflow Pipeline**: Step numbers renumbered (enhance_images step 9 removed)
  - Steps 10-16 became steps 9-15
  - Updated step descriptions and orchestrator parameter handling
- **Path Management**: Removed `enhanced` property from PathManager
- **Disk Space Checking**: Updated to only check `original/` folder (no longer checks `enhanced/`)
- **Report Templates**: Removed enhanced image references from HTML report template
- **Test Infrastructure**: Consolidated test data structure (`test_data/` → `tests/test_data/`)

#### Fixed - Architecture Improvements
- **Circular Import Resolution**: Implemented proper `TYPE_CHECKING` pattern in ConfigManager
- **Import Dependencies**: Cleaned up circular dependencies between manager classes
- **Validator System**: Removed enhancement validator, updated validator registry
- **Configuration Management**: Enhanced type safety with forward reference handling

### 🚀 **AWS/Local Infrastructure Enhancements** *(Previously 1.2.0 features)*

#### Added - S3 Integration System
- **S3 Backup Utilities**: Comprehensive project artifact backup system
  - `utils/shared/backup_to_s3.py`: Timestamped backup organization for reproducibility
  - `utils/shared/s3_status_tracker.py`: Thread-safe status tracking with JSON heartbeat
  - `utils/shared/s3_transfer_config.py`: File size-optimized transfer configurations
  - `utils/shared/s3_upload_helpers.py`: AWS session management and integrity checking
- **S3 Scripts Collection**: Complete suite of upload/download utilities
  - `scripts/upload_to_s3.py`: Unified upload script with resume capability
  - `scripts/download_project_files.py`: S3-to-local project file staging
  - Enhanced with proper v1.2.0 header blocks and documentation
- **S3 Utils Modernization**: Complete rewrite of `utils/s3_utils.py`
  - Functions: `list_projects`, `list_reels`, `stage_reels`, `stage_project_files`
  - Parallel download support with enhanced error handling

#### Changed - Orchestrator Major Refactor
- **Process360Workflow Enhancement**: Comprehensive orchestrator improvements
  - **Parameter Reordering**: Logical flow (config → source_mode → project → workflow flags)
  - **Source Mode Support**: Dynamic Local/AWS mode with UI population via boto3
  - **Multiselect Reel Processing**: Process specific reels instead of all reels
  - **Automatic Path Resolution**: Smart input path derivation based on source mode
  - **Name-Based Parameters**: Refactored from index-based to name-based parameter handling
- **Configuration Updates**: Enhanced `config.sample.yaml` with AWS S3 integration settings
- **AWS Utilities**: Updated `utils/shared/aws_utils.py` with enhanced credential management

### 📋 **Version Management Strategy**
- **v1.3.0**: Files modified for enhancement removal (breaking changes)
- **v1.2.0**: Files added/modified for AWS infrastructure (October 2025 features)
- **Proper Headers**: All S3 utilities now have standardized header blocks

### 🧪 **Testing & Quality Improvements**
- **Test Infrastructure**: Updated all tests to match new LogManager interface
- **Test Data Consolidation**: Moved `test_data/` into `tests/test_data/` structure
- **Enhancement Test Removal**: Cleaned up all enhancement-related test files
- **Validation Updates**: Updated test expectations for 15-step workflow

### 📊 **Impact Summary**
- **35 files changed**: 461 insertions, 1,462 deletions (net code reduction)
- **Architecture Simplified**: Removed complex enhancement pipeline, improved maintainability
- **AWS Integration**: Complete S3-based workflow support for cloud operations
- **Breaking Changes**: Configuration schema incompatible with previous versions

### 🔄 **Migration Guide**
1. **Remove Enhancement Config**: Delete `image_enhancement:` section from config files
2. **Update Workflow References**: Adjust any custom scripts expecting 16 workflow steps
3. **Path Updates**: Remove references to `enhanced/` folder in custom implementations
4. **S3 Integration**: Review new AWS configuration options for cloud workflows

---

## [2025-10-30] - Documentation System Overhaul
### 📚 Major Documentation System Implementation
#### Added
- **Comprehensive Sphinx Documentation System**: Complete implementation of professional documentation using Sphinx with ReadTheDocs theme
  - Automated API documentation generation from Python docstrings using autodoc
  - Professional navigation, search functionality, and cross-references
  - Organized documentation structure: User Guide, Tools, Configuration, AWS Integration, API Reference, Developer Guide
- **GitHub Actions CI/CD Pipeline**: Automated documentation building and deployment to GitHub Pages
  - Builds documentation on every push to main branch
  - Deploys to `https://camrex.github.io/rmi-360-workflow-pyt/`
  - Uses latest GitHub Actions versions (fixed deprecation warnings)
- **Documentation Infrastructure**:
  - Cross-platform build system with `Makefile` and `make.bat` for local development
  - Comprehensive `conf.py` with theme customization, extensions, and intersphinx linking
  - Complete documentation structure with placeholder pages for future content migration
- **Enhanced README**: Updated with documentation badges, links to new Sphinx docs, and migration notes
- **Build Configuration**: Updated `.gitignore` to exclude Sphinx build artifacts and added Sphinx dependencies to `requirements.txt`

#### Changed
- **Documentation Workflow**: Transitioned from legacy Markdown docs to modern Sphinx-generated documentation
- **Project Structure**: Added `docs/` directory with complete RST-based documentation framework
- **Development Process**: Documentation now builds automatically and deploys to GitHub Pages on commits

#### Documentation Structure Added
- **User Guide**: Installation, configuration, quick start, and ArcGIS Pro setup guides
- **Tools Documentation**: Comprehensive tool reference with setup tools, individual tools, and orchestrator documentation
- **Configuration**: Complete configuration system documentation with project settings, AWS settings, and field registry
- **AWS Integration**: Setup guides, S3 uploads, and Lambda monitoring documentation
- **API Reference**: Auto-generated API documentation for tools, utilities, managers, and validators
- **Developer Guide**: Contributing guidelines, testing information, and architecture documentation

#### Technical Improvements
- **Professional Theme**: Implemented ReadTheDocs theme with custom styling and navigation
- **Cross-References**: Extensive internal linking between documentation sections
- **API Integration**: Automatic Python API documentation generation with Napoleon extension support
- **Search Functionality**: Full-text search across all documentation
- **Mobile Responsive**: Documentation works on desktop and mobile devices

#### Migration Notes
- Legacy documentation in `docs_legacy/` remains available during transition period
- New documentation system provides foundation for gradual content migration
- All existing `.md` files preserved for reference and continued use
- Build system supports both local development and automated CI/CD deployment

### 🚀 Major Infrastructure and S3 Integration Enhancements
#### Added
- **S3 Backup Utilities System**: Comprehensive project artifact backup system with thread-safe operations
  - `backup_to_s3.py`: Upload project artifacts (config, logs, reports, GIS data) with timestamp organization
  - `s3_status_tracker.py`: Thread-safe status tracking for S3 uploads with JSON heartbeat updates
  - `s3_transfer_config.py`: Optimized transfer configurations based on file size for reliable uploads
  - `s3_upload_helpers.py`: Common S3 helper functions including AWS session management and file integrity checking
- **Enhanced S3 Scripts**: New standalone and integrated upload scripts
  - `upload_raw_reels_standalone.py`: Standalone script for uploading RAW Mosaic reels to S3
  - `upload_raw_reels.py`: Integrated upload helper for reel processing workflows
  - `download_project_files.py`: Download project files (config, GIS data) from S3 to local directories
  - `upload_to_s3.py`: Unified upload script for all project file types with resume capability
- **S3 Utils Modernization**: Complete rewrite of S3 utilities (`s3_utils.py`) with enhanced functionality
  - Centralized S3 list/stage operations with parallel download support
  - Functions: `list_projects`, `list_reels`, `normalize_prefix`, `stage_reels_prefix`, `stage_project_files`
  - Improved error handling and AWS session management

#### Changed
- **Process360Workflow Orchestrator Major Refactor**: Enhanced workflow orchestrator with improved AWS integration
  - **Parameter Reordering**: Logical parameter flow (config_file → source_mode → project settings → workflow flags)
  - **Source Mode Support**: Dynamic Local/AWS mode handling with UI population via boto3 helpers
  - **Multiselect Reel Processing**: Added multiselect capability for processing specific reels
  - **Automatic Path Resolution**: Input reels folder path now derived automatically based on source mode
  - **Name-Based Parameter Mapping**: Refactored parameter handling to use names instead of index-based access
  - **Always Required Project Folder**: Project folder now always required for ConfigManager project_base resolution
- **Configuration Enhancements**: Updated `config.sample.yaml` with improved AWS S3 integration settings
- **Legacy File Replacement**: `utils/s3_stage.py` replaced by enhanced `utils/s3_utils.py`

#### Fixed
- **File Integrity Checking**: Implemented robust file integrity verification for S3 uploads
- **AWS Credential Management**: Enhanced AWS credential validation and session management
- **Upload Resume Capability**: Added resume functionality for interrupted S3 uploads
- **Progress Tracking**: Improved real-time status tracking for long-running S3 operations

#### Technical Improvements
- **Thread-Safe Operations**: S3 operations now use thread-safe status tracking and progress updates
- **Parallel Processing**: Enhanced S3 download/upload operations with configurable parallelism
- **Error Resilience**: Improved error handling and retry mechanisms for S3 operations
- **Status JSON Updates**: Real-time JSON status updates for monitoring upload/download progress
- **Shared Utilities Expansion**: Enhanced `utils/shared/` module with new infrastructure utilities
  - Updated `aws_utils.py`, `folder_stats.py` for better S3 and file system operations
  - New shared utilities for transfer configuration and status tracking

#### Documentation Updates
- **Comprehensive Legacy Documentation**: Added detailed documentation for new S3 features
  - `ARTIFACT_BACKUP_GUIDE.md`: Guide for backing up project artifacts to S3
  - `FOLDER_STRUCTURE_UPDATE.md`: Updated project folder structure documentation
  - `UPLOAD_TO_S3_CHANGES.md`: Detailed changes to S3 upload functionality
  - `SCRIPTS_QUICK_REFERENCE.md`: Quick reference for new upload/download scripts

---

## [2025-05-23]
### 🧰 RMI 360 Environment Checker and other quality-of-life changes
#### Added
- Added `rmi_360_env_checker.pyt` to the repository to check for required libraries in the ArcGIS Pro Python environment. This utility does not affect workflow toolbox versioning.
- Added ArcGIS Pro license matrix (`docs_legacy/ARCGISPRO_LICENSE_REQUIREMENTS.md`) summarizing which ArcPy functions/classes require Basic, Standard, or Advanced licenses.
- Added note to README indicating that a Standard license or above is required for Oriented Imagery tools.

#### Removals/Deprecations
- Removed `humanize` package requirement. Replaced with a native Python function in `folder_stats.py` for human-readable file size formatting. The Toolbox now runs in the base ArcGIS Pro Python environment without extra dependencies.

---

## [v1.1.1] - 2025-05-22
### 🛠️ Bug Fix Update
#### Added
- Added `OrientationAccuracy` as a standard field in `esri_oid_fields_registry.yaml` (per ArcGIS Pro 3.5 OID attribute updates).
- Added `verify_aws_credentials()` function to `aws_utils.py` for AWS credential verification.
- Added additional validation to fail early if proper AWS credentials are not provided.

#### Fixed
- Fixed indentation of `project.local_proj_wkid`. It needs to be a child of `project`. This caused failure in validation.
- Fixed a regression in configuration management where the project root directory path key was changed from `__project_root__` to `__project_base__`. This update restores the correct key (`__project_root__`) for full compatibility with workflow tools and logging.
- Updated the sample configuration so `geocoding.exiftool_geodb` now defaults to `default`, avoiding errors when the specialized `geolocation500` GeoDB is not present in templates. This improves out-of-the-box compatibility for new projects.
- Resolved bugs in `build_oid_schema.py` affecting OID generation and schema consistency.
- Fixed AWS credential verification in `copy_to_aws.py` to match the logic in `deploy_lambda_monitor.py`, which is now handled from `aws_utils.py`.This ensures that invalid or placeholder credentials are detected before any operations are attempted, improving reliability and error reporting.
- Fixed a bug in `generate_oid_service.py` where the OID was not duplicated with AWS urls.

> **⚠️ Note: ⚠️**
> Version **v1.1.0** contained critical bugs that may render the workflow unusable.
> Please use version **v1.1.1** or later, which resolves these issues.

> **⚠️ Unit Tests Note:** Many unit tests may currently be broken due to some bug fixes in this release.

---

## [v1.1.0] - 2025-05-20
### 🚀 Public Release - RMI 360 Imaging Workflow Python Toolbox v1.1.0 (Major Refactor: Managers, Modularization, and Enhancements)
#### Added
- Manager Classes: Introduced ConfigManager, LogManager, PathManager, and ProgressorManager for centralized configuration, logging, path resolution, and progress tracking.
- Modular Validators: Added tool-specific validator modules under utils/validators/ for robust, modular config validation.
- Shared Utilities: New/refactored shared utilities for ArcPy, AWS, disk space, expression resolution, folder stats, metrics, report data, exceptions, and schema validation.
- Comprehensive Tests: Extensive new and updated unit/integration tests for all major modules, managers, validators, and utilities.
- Legacy Documentation: Added detailed legacy docs for all tools, utilities, and managers.
- Orchestrator Enhancements: Fine-grained control over optional steps, with improved configuration options, documentation, and error handling.
- Metadata Enhancements: Expanded metadata handling with new fields for richer context and propagation across workflow steps.

#### Changed
- Centralized Configuration & Logging: All tools and utilities now use ConfigManager and LogManager for consistent config access and structured logging.
- Unified Path Handling: All path resolution is now managed by PathManager for cross-platform consistency.
- Progress Tracking: Progress reporting is standardized via ProgressorManager.
- Refactored APIs: All major workflow functions and tools now accept manager objects instead of raw config dicts/files.
- Parameter Handling: Tools now require a project folder parameter and use config managers for all settings.
- Documentation Structure: Docs reorganized; legacy docs added, old docs/tools removed or moved.

#### Removed
- Legacy Utilities: Deleted or replaced modules: config_loader.py, executable_utils.py, pad_mosaic_frame_numbers.py, path_resolver.py, path_utils.py, schema_paths.py, validate_config.py.
- Old Documentation: Removed or replaced old docs/tools in docs/ and dev_docs/.

#### Fixed
- Static Analysis: Improved import/export patterns for better static analysis and namespace clarity.
- Error Handling: Unified and improved error handling and logging across all modules.

#### Docs
- Legacy Docs: Added/updated documentation for all tools, utilities, and managers under docs_legacy/.
- README: Updated to reflect new structure, features, and usage notes.

#### Tests
- Expanded Coverage: Added or updated tests for all managers, utilities, validators, and workflow modules.
- Test Data: Added comprehensive sample/test config and placeholder files.

#### Breaking Changes
- Manager APIs: All tools and utilities now require manager objects (ConfigManager, etc.) instead of raw config dicts/files.
- Logging Configuration: Logging is now handled exclusively via LogManager; old logging utilities are removed.
- Import Patterns: Utilities and shared modules now use explicit imports and modular APIs.
- Config Schema: Configuration files must be updated to match the new schema and structure.

#### Migration Notes
- Update all tool invocations to use the new manager-based APIs.
- Review and update configuration files to match the new schema (see sample/test configs).
- Review updated documentation for usage examples and migration guidance.
- Remove any dependencies on deleted legacy utility modules.

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
