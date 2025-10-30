# Folder Structure Update - Summary of Changes

## Date: October 30, 2025

## Overview
Updated the RMI 360 Workflow to support a new standardized folder structure on EC2 instances and expanded S3 bucket organization to include config and gis_data folders.

## New Folder Structure

### EC2 Instance
```
D:/Process360_Data/projects/{project_key}/
├── reels/          # Raw 360 video reels
├── config/         # Project-specific config files (NEW)
├── gis_data/       # GIS reference data (NEW)
├── backups/        # OID backup snapshots
├── logs/           # Processing logs
├── panos/          # Panoramic images
│   ├── original/
│   ├── enhance/
│   └── final/
└── report/         # HTML reports
```

### S3 Bucket (rmi-360-raw)
```
s3://rmi-360-raw/{project_key}/
├── reels/          # Raw video uploads (existing)
├── config/         # Configuration files (NEW)
└── gis_data/       # GIS reference data (NEW)
```

## Files Modified

### 1. tools/process_360_orchestrator.py
**Changes:**
- Changed from `scratch/{slug}` to `projects/{slug}` structure
- Updated `scratch_dir` variable to `project_dir`
- Updated path references in comments
- Path: `{local_root}/projects/{project_key}/`

**Lines modified:** ~765-782, ~832, ~837

### 2. utils/s3_utils.py
**New functionality:**
- Added `stage_project_files()` function to download config/gis_data from S3
- Added support for multiple folder types (config, gis_data)
- Added Dict import for type hints
- Updated `__all__` exports

**New function signature:**
```python
def stage_project_files(
    bucket: str,
    project_key: str,
    folder_types: Optional[List[str]],
    local_project_dir: Path,
    max_workers: int = 16,
    skip_if_exists: bool = True,
) -> Dict[str, Path]
```

### 3. scripts/upload_helpers.py
**New constants:**
- `CONFIG_EXTS = {".yaml", ".yml", ".json", ".txt"}`
- `GIS_DATA_EXTS = {".shp", ".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".xml", ".geojson", ".json", ".kml", ".kmz", ".gdb", ".gpkg"}`

**New function:**
- `upload_project_files()` - Generic upload function for config and gis_data

### 4. scripts/upload_project_files.py (NEW FILE)
**Purpose:**
- Command-line script to upload config or gis_data files to S3
- Supports dry-run mode
- CSV logging with resume capability

**Usage:**
```bash
python scripts/upload_project_files.py \
  --config config.yaml \
  --folder path/to/files \
  --folder-type [config|gis_data] \
  --project-key RMI25320 \
  [--dry-run]
```

### 5. configs/config.sample.yaml
**Changes:**
- Updated `runtime.local_root` documentation
- Changed default from placeholder to `D:/Process360_Data`
- Added detailed comments explaining folder structure
- Added S3 structure documentation

### 6. AWS_SETUP.md
**Changes:**
- Updated Step 8 (Smoke test) with new folder structure
- Added EC2 and S3 directory structure diagrams
- Updated testing steps to reflect new paths
- Added reference to FOLDER_STRUCTURE_UPDATE.md

### 7. FOLDER_STRUCTURE_UPDATE.md (NEW FILE)
**Purpose:**
- Comprehensive documentation of the new folder structure
- Migration guide for existing projects
- Usage examples for new upload/download functionality
- Benefits and backward compatibility notes

## Key Features

### 1. Unified Project Directory
- All project files in one location: `D:/Process360_Data/projects/{project_key}/`
- Persistent storage (no longer in temporary "scratch" directory)
- Better organization and easier maintenance

### 2. Config and GIS Data Support
- Upload config files to S3 for cloud-based project management
- Upload GIS reference data to S3
- Download (stage) config and GIS data from S3 to EC2

### 3. Upload Scripts
```bash
# Upload reels (existing)
python scripts/upload_raw_reels.py --config config.yaml --folder reels/ --prefix RMI25320/reels/

# Upload config (NEW)
python scripts/upload_project_files.py --config config.yaml --folder config/ --folder-type config --project-key RMI25320

# Upload GIS data (NEW)
python scripts/upload_project_files.py --config config.yaml --folder gis_data/ --folder-type gis_data --project-key RMI25320
```

### 4. Download Support
```python
from utils.s3_utils import stage_project_files

# Download config and gis_data
paths = stage_project_files(
    bucket='rmi-360-raw',
    project_key='RMI25320',
    folder_types=['config', 'gis_data'],
    local_project_dir=Path('D:/Process360_Data/projects/RMI25320')
)
```

## Backward Compatibility

- ✅ PathManager works with relative paths (no changes needed)
- ✅ Existing tools don't require modification
- ✅ Old `scratch/` references replaced with `projects/`
- ✅ Upload scripts maintain resume functionality
- ✅ No breaking changes to config schema (still version 1.2.0)

## Testing Checklist

Before deploying to production:

- [ ] Test config.yaml with new `runtime.local_root`
- [ ] Test upload_project_files.py with config folder
- [ ] Test upload_project_files.py with gis_data folder
- [ ] Test upload_raw_reels.py (ensure no regression)
- [ ] Test stage_project_files() function
- [ ] Run orchestrator in AWS mode with new paths
- [ ] Verify all output folders created correctly
- [ ] Check logs written to correct location
- [ ] Verify backups stored in correct folder
- [ ] Test with existing project (migration scenario)
- [ ] Test with new project (clean start scenario)

## Migration Notes

### For Existing EC2 Instances

1. Update `config.yaml`:
   ```yaml
   runtime:
     local_root: "D:/Process360_Data"
   ```

2. Move existing data (if any):
   ```powershell
   # If old data exists in scratch location
   Move-Item "D:/old_location/scratch/RMI25320" "D:/Process360_Data/projects/RMI25320"
   ```

3. Verify folder structure after first run

### For New Projects

- Just set `runtime.local_root` in config.yaml
- Toolbox creates all necessary directories automatically
- Upload config and gis_data to S3 (optional but recommended)

## Benefits

1. **Consistency:** All projects use same structure
2. **Persistence:** Files remain after processing
3. **Organization:** Clear separation by file type
4. **Scalability:** Multiple projects on one EC2 instance
5. **Cloud Integration:** Config and GIS data in S3
6. **Resumability:** Skip existing files on re-run

## Next Steps

1. Review and test all changes
2. Update EC2 AMI with new folder structure
3. Document in team wiki/knowledge base
4. Train users on new upload scripts
5. Monitor first few production runs

## Questions or Issues?

Contact: RMI Development Team
Reference: FOLDER_STRUCTURE_UPDATE.md for detailed documentation
