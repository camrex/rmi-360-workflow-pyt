# upload_to_s3.py - Refactoring Changes

## Overview
Updated `scripts/upload_to_s3.py` to use helper modules and support multi-folder-type uploads.

## File Size Reduction
- **Before**: 1,113 lines (after copying from upload_raw_reels_standalone_current.py)
- **After**: ~850 lines
- **Reduction**: ~260 lines (~23% smaller)

## Major Changes

### 1. **Imports Updated**
- Added imports from helper modules:
  - `from utils.shared.s3_upload_helpers import *` (11 functions)
  - `from utils.shared.s3_transfer_config import get_transfer_config, get_boto_config`
  - `from utils.shared.s3_status_tracker import StatusTracker`
- Added `datetime` for timestamp generation
- Added `Dict` type hint

### 2. **Removed Duplicate Code (~380 lines)**
Functions now imported from helpers instead of defined locally:
- `load_cfg()` - Config loading with YAML support
- `resolve_project_base()` - Project base path resolution
- `resolve_session()` - AWS session with config/instance/keyring support
- `resolve_max_concurrency()` - Worker count calculation
- `normalize_s3_prefix()` - S3 prefix normalization
- `md5_file()` - MD5 checksum calculation
- `sha256_file()` - SHA-256 checksum calculation
- `s3_object_matches_local()` - Multi-tier S3 verification
- `parse_uploaded_keys_from_log()` - Resume functionality
- `atomic_write_text()` - Safe file writes
- `now_ts()` - Timestamp helper
- `StatusTracker` class - Status tracking with JSON heartbeat

### 3. **New Multi-Folder-Type Support**

#### Added Constants
```python
FOLDER_TYPE_EXTENSIONS = {
    'reels': {'.mp4', '.json', '.csv', '.gpx'},
    'config': {'.yaml', '.yml', '.json', '.txt'},
    'gis_data': {'.shp', '.shx', '.dbf', '.prj', '.cpg', '.sbn', '.sbx', '.gdb', '.kml', '.kmz'},
    'logs': {'.txt', '.log', '.csv', '.args'},
    'report': {'.html', '.json', '.png', '.jpg', '.jpeg', '.pdf'}
}
```

#### New Functions
- `detect_folder_types(base_folder)` - Auto-detect folder types in project
- `collect_upload_tasks()` - Updated with `project_key`, `folder_type`, `timestamp` parameters
- `collect_multi_folder_tasks()` - Collect files for multiple folder types
- `reel_from_key()` - Updated to support `project_key` and `folder_type`

### 4. **Argument Parser Redesigned**

#### Old Arguments (Reel-Specific)
```bash
--config <path>
--folder <path>
--prefix <s3-prefix>  # e.g., "RMI25320/reels/"
```

#### New Arguments (Multi-Folder-Type)
```bash
# Required
--config <path>
--folder <path>
--project-key <key>  # e.g., "RMI25320"

# Folder type selection (mutually exclusive)
--folder-type {reels|config|gis_data|logs|report}  # Single type
--include {reels config gis_data logs report}      # Multiple types
--exclude {reels config gis_data logs report}      # Exclude types

# Timestamp options
--timestamp                    # Auto-generate YYYYMMDD_HHMM
--custom-timestamp <string>    # Custom timestamp

# Upload options (unchanged)
--dry-run
--force
--skip-large-check
--verify-large
--debug
--status-json <path>
--status-interval <seconds>
```

### 5. **S3 Key Structure**

#### Old Structure
```
<prefix>/reel_name/file.ext
Example: RMI25320/reels/REEL_001/video.mp4
```

#### New Structure
```
<project_key>/<folder_type>/[timestamp/]<subfolder>/file.ext

Examples:
- RMI25320/reels/REEL_001/video.mp4
- RMI25320/reels/20251030_1430/REEL_001/video.mp4
- RMI25320/config/config.yaml
- RMI25320/gis_data/study_area.shp
- RMI25320/logs/20251030_1430/process_log.txt
```

### 6. **Upload Logic Changes**

#### Task Collection
- **Old**: Single folder type (reels only), grouped by reel name
- **New**: Multiple folder types, grouped by:
  - Reels → grouped by reel name
  - Other types → single group per folder type

#### StatusTracker
- **Old**: Fixed `group_key="reels"`
- **New**: Dynamic `group_key`:
  - `"reels"` when `--folder-type reels`
  - `"folder_types"` for multi-type uploads

#### Progress Display
```
Old:
[REEL] >>> Starting reel: REEL_001 (files=145)
[REEL] <<< Completed reel: REEL_001 | uploaded=145 skipped=0 failed=0 bytes=8589934592

New:
[REELS] >>> Starting REEL_001 (files=145)
[REELS] <<< Completed REEL_001 | uploaded=145 skipped=0 failed=0 bytes=8589934592

[CONFIG] >>> Starting config (files=3)
[CONFIG] <<< Completed config | uploaded=3 skipped=0 failed=0 bytes=1024

[GIS_DATA] >>> Starting gis_data (files=25)
[GIS_DATA] <<< Completed gis_data | uploaded=25 skipped=0 failed=0 bytes=1048576
```

### 7. **Transfer Configuration**
- **Old**: Inline `get_transfer_config()` function (~70 lines)
- **New**: Imported from `s3_transfer_config.py`
  - Adaptive multipart settings based on file size
  - Small <512MB: 8MB parts, 8 workers
  - Medium 512MB-8GB: 64MB parts, 6 workers
  - Large >8GB: 128MB parts, 4 workers

### 8. **CSV Logging**
- **Old**: `upload_raw_log.csv`
- **New**: `upload_log.csv` (generic for all folder types)
- Header unchanged:
  ```
  timestamp, local_file, s3_key, status, error, size_bytes, duration_sec, content_type
  ```

## Usage Examples

### Upload Reels Only (Legacy Behavior)
```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder /data/RMI25320/reels \
  --project-key RMI25320 \
  --folder-type reels
```

### Upload Config and GIS Data
```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder /data/RMI25320 \
  --project-key RMI25320 \
  --include config gis_data
```

### Upload All Except Logs
```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder /data/RMI25320 \
  --project-key RMI25320 \
  --exclude logs
```

### Upload Logs with Timestamp
```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder /data/RMI25320/logs \
  --project-key RMI25320 \
  --folder-type logs \
  --timestamp
```

### Dry Run (All Auto-Detected Types)
```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder /data/RMI25320 \
  --project-key RMI25320 \
  --dry-run
```

## Backwards Compatibility
**Breaking Changes**:
- `--prefix` replaced with `--project-key`
- S3 structure changed from `<prefix>/<files>` to `<project_key>/<folder_type>/<files>`
- CSV log filename changed from `upload_raw_log.csv` to `upload_log.csv`

**Migration**:
- Update scripts/workflows that call `upload_to_s3.py`
- Use `--project-key` instead of `--prefix`
- Specify `--folder-type reels` for reel-only uploads

## Testing Checklist
- [ ] Upload reels only (`--folder-type reels`)
- [ ] Upload config files (`--folder-type config`)
- [ ] Upload multiple types (`--include reels config gis_data`)
- [ ] Auto-detect folder types (no folder selection args)
- [ ] Timestamp subfolder (`--timestamp`)
- [ ] Custom timestamp (`--custom-timestamp 20251030_1430`)
- [ ] Dry run shows correct grouping
- [ ] Resume from CSV log works
- [ ] StatusTracker JSON heartbeat works
- [ ] Large file retry logic works (>1GB)
- [ ] SHA-256 metadata stored for large files
- [ ] Force re-upload (`--force`)

## Related Files
- `utils/shared/s3_upload_helpers.py` - Common utilities
- `utils/shared/s3_transfer_config.py` - Transfer optimization
- `utils/shared/s3_status_tracker.py` - Status tracking
- `REFACTORING_SUMMARY.md` - Helper modules documentation
