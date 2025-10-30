# Folder Structure Update - December 2025

## Overview

The RMI 360 Workflow has been updated to support a new standardized folder structure for both EC2 instances and S3 storage. This document outlines the changes and provides migration guidance.

## New Folder Structure

### EC2 Instance Structure

All project files are now stored under a unified base directory:

```
D:/Process360_Data/projects/{project_key}/
├── reels/          # Raw 360 video reels from S3
├── config/         # Project-specific configuration files
├── gis_data/       # GIS reference data (shapefiles, geodatabases, etc.)
├── backups/        # OID feature class backup snapshots
├── logs/           # Processing logs and debug output
├── panos/          # Extracted panoramic images
│   ├── original/   # Original extracted frames
│   ├── enhance/    # Enhanced images
│   └── final/      # Renamed final images
└── report/         # HTML reports and metrics
```

### S3 Structure (rmi-360-raw bucket)

The S3 bucket structure has been expanded to support config and GIS data uploads:

```
s3://rmi-360-raw/{project_key}/
├── reels/          # Raw video uploads (existing)
├── config/         # Configuration files (NEW)
└── gis_data/       # GIS reference data (NEW)
```

## Key Changes

### 1. Unified Project Directory

**Before:**
- Projects used `{local_root}/scratch/{project_slug}/` for temporary processing
- Inconsistent handling of project files

**After:**
- All projects use `{local_root}/projects/{project_key}/`
- Consistent, persistent project directory structure
- Better organization and easier maintenance

### 2. Config Path Updates

Update your `config.yaml`:

```yaml
runtime:
  local_root: "D:/Process360_Data"   # Base path on EC2
```

The toolbox will automatically create the full project path:
`D:/Process360_Data/projects/{project_slug}/`

### 3. S3 Upload Support

New unified upload script allows uploading any combination of project files to S3:

#### Upload All Project Files

```bash
python scripts/upload_to_s3.py \
  --config path/to/config.yaml \
  --folder path/to/project_folder \
  --project-key RMI25320 \
  --include reels config gis_data
```

#### Upload Config Files

```bash
python scripts/upload_to_s3.py \
  --config path/to/config.yaml \
  --folder path/to/config_folder \
  --folder-type config \
  --project-key RMI25320
```

#### Upload GIS Data

```bash
python scripts/upload_to_s3.py \
  --config path/to/config.yaml \
  --folder path/to/gis_data_folder \
  --folder-type gis_data \
  --project-key RMI25320
```

#### Upload Reels

```bash
python scripts/upload_to_s3.py \
  --config path/to/config.yaml \
  --folder path/to/reels_folder \
  --folder-type reels \
  --project-key RMI25320
```

### 4. Download Support

The new `stage_project_files()` function in `s3_utils.py` allows downloading config and gis_data:

```python
from utils.s3_utils import stage_project_files
from pathlib import Path

# Download config and gis_data files
paths = stage_project_files(
    bucket='rmi-360-raw',
    project_key='RMI25320',
    folder_types=['config', 'gis_data'],  # or None for both
    local_project_dir=Path('D:/Process360_Data/projects/RMI25320'),
    max_workers=16,
    skip_if_exists=True
)

# Returns: {
#   'config': Path('D:/Process360_Data/projects/RMI25320/config'),
#   'gis_data': Path('D:/Process360_Data/projects/RMI25320/gis_data')
# }
```

## Modified Files

### Core Updates

1. **tools/process_360_orchestrator.py**
   - Changed from `scratch/{slug}` to `projects/{slug}`
   - Updated path references and documentation

2. **utils/s3_utils.py**
   - Added `stage_project_files()` function
   - Support for config and gis_data folder types
   - Enhanced `__all__` exports

3. **utils/manager/path_manager.py**
   - No changes needed - paths are relative to project_base
   - Works correctly with new structure

### New Files

1. **scripts/upload_to_s3.py**
   - Unified script for uploading all project file types
   - Supports reels, config, gis_data, logs, report
   - Resume support, MD5 verification, live status JSON
   - Selective uploads via --include/--exclude
   - Supports dry-run mode
   - CSV logging for resume capability

### Updated Scripts

1. **scripts/upload_helpers.py**
   - Added `CONFIG_EXTS` and `GIS_DATA_EXTS` constants
   - Added `upload_project_files()` function
   - Shared upload logic for all file types

2. **configs/config.sample.yaml**
   - Updated runtime section with documentation
   - Changed default from placeholder to `D:/Process360_Data`

## Migration Guide

### For Existing Projects

1. **Update config.yaml:**
   ```yaml
   runtime:
     local_root: "D:/Process360_Data"
   ```

2. **Move existing project data (if needed):**
   ```powershell
   # On EC2, if you have data in old scratch location
   Move-Item "D:/old_location/scratch/RMI25320" "D:/Process360_Data/projects/RMI25320"
   ```

3. **Upload config files to S3 (optional but recommended):**
   ```bash
   python scripts/upload_to_s3.py \
     --config config.yaml \
     --folder D:/Process360_Data/projects/RMI25320 \
     --project-key RMI25320 \
     --include config \
     --timestamp
   ```

### For New Projects

The new structure is automatically used when:
- Creating a new project with the orchestrator
- Specifying `runtime.local_root` in config.yaml
- The toolbox will create all necessary subdirectories

## Benefits

1. **Consistency:** Unified structure across all projects
2. **Persistence:** Project files remain in place after processing
3. **Organization:** Clear separation of file types
4. **Scalability:** Support for multiple projects on single EC2 instance
5. **Cloud Integration:** Easy sync with S3 for config and reference data
6. **Resumability:** Existing files are preserved between runs

## Backward Compatibility

- PathManager continues to work with relative paths
- Existing tools don't need modification
- Old `scratch/` references have been replaced with `projects/`
- Upload scripts maintain resume functionality

## Testing Checklist

- [ ] Verify config.yaml has correct `runtime.local_root`
- [ ] Test upload of config files to S3
- [ ] Test upload of gis_data to S3
- [ ] Test download (staging) of project files from S3
- [ ] Run orchestrator with AWS source mode
- [ ] Verify all output folders are created correctly
- [ ] Check logs are written to correct location
- [ ] Verify backups go to correct folder

## Support

For questions or issues with the new folder structure:
1. Check this document first
2. Review the config.sample.yaml for examples
3. Check tool logs in `{project_dir}/logs/`
4. Contact RMI development team

## Version History

- **2025-12-30:** Initial implementation of new folder structure
- **Schema Version:** 1.2.0 (unchanged)
