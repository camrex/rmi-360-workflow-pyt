# S3 Upload Script Refactoring Summary

## Overview

Refactored the upload scripts to reduce code duplication and file size by extracting common functionality into reusable helper modules.

## New Helper Modules Created

### 1. `utils/shared/s3_upload_helpers.py` (300 lines)

**Purpose**: Common S3 upload utilities

**Functions**:
- `load_cfg(cfg_path)` - Load and validate YAML config
- `resolve_project_base(arg, cfg, cfg_path)` - Determine project base directory
- `resolve_session(auth_mode, service_name)` - Create boto3 session (config/instance/keyring)
- `resolve_max_concurrency(val)` - Parse max workers ("cpu*4", int, etc.)
- `normalize_s3_prefix(prefix)` - Consistent prefix formatting
- `md5_file(path)` - Streaming MD5 checksum for small files
- `sha256_file(path)` - Streaming SHA-256 checksum for large files
- `s3_object_matches_local(s3, bucket, key, fpath, ...)` - Multi-tier file verification
- `parse_uploaded_keys_from_log(log_csv)` - Resume support via CSV
- `atomic_write_text(path, text)` - Atomic file writes

**Key Features**:
- Multi-tier resume verification (SHA-256 > timestamp > size)
- Supports keyring authentication
- CPU-based concurrency calculation

### 2. `utils/shared/s3_transfer_config.py` (90 lines)

**Purpose**: Adaptive S3 transfer configuration for large files

**Functions**:
- `get_transfer_config(file_size_bytes, max_workers)` - Size-optimized TransferConfig
- `get_boto_config()` - Enhanced boto3 client configuration

**Optimization Strategy**:
```python
< 512MB:    8MB parts,  8 workers  (speed)
512MB-8GB:  64MB parts, 6 workers  (balanced)
> 8GB:      128MB parts, 4 workers (stability)
```

**Boto3 Config Features**:
- Adaptive retry mode (up to 12 attempts)
- Extended timeouts (20s connect, 5min read)
- Increased connection pool (50 connections)

### 3. `utils/shared/s3_status_tracker.py` (180 lines)

**Purpose**: Thread-safe status tracking with JSON heartbeat

**Class**: `StatusTracker`

**Methods**:
- `set_totals(n)` - Set total file count
- `start_group(name, planned_files)` - Begin group (reel, folder_type, etc.)
- `complete_group(name)` - Mark group complete
- `start_file(group, fpath, size)` - Begin file upload
- `file_progress_cb(group)` - Get boto3 progress callback
- `file_done(group, outcome, size)` - Mark file complete
- `note_skip(group)` - Note skipped file

**Features**:
- Generic design (works for reels, folder_types, or any grouping)
- Configurable group key ("reels", "folder_types", etc.)
- Throttled JSON writes (configurable interval)
- Atomic file writes (temp file + rename)
- Thread-safe with locking

**JSON Schema**:
```json
{
  "started_at": 1730182741.12,
  "phase": "uploading",
  "current_<group>": "group_name",
  "current_file": "/path/to/file.mp4",
  "current_file_bytes": 83886080,
  "current_file_size": 262144000,
  "totals": {
    "files": 420,
    "uploaded": 119,
    "skipped": 301,
    "failed": 0,
    "bytes_uploaded": 127842091008
  },
  "<groups>": {
    "group_name": {
      "planned_files": 42,
      "uploaded": 41,
      "skipped": 1,
      "failed": 0,
      "bytes_uploaded": 127842091008,
      "started_at": 1730182741.12,
      "completed_at": 1730183922.77
    }
  },
  "last_update": 1730183799.45
}
```

## Benefits

### Code Reuse
- **Before**: Duplicate code in multiple upload scripts
- **After**: Single source of truth for common functionality
- **Impact**: Easier maintenance, consistent behavior

### File Size Reduction
- **Before**: `upload_raw_reels_standalone_current.py` = 1,077 lines
- **After**: Main script ~400-500 lines + helpers ~570 lines
- **Impact**: More readable main script, focused on business logic

### Testability
- **Before**: Hard to test individual functions
- **After**: Each helper module can be unit tested independently
- **Impact**: Better test coverage, easier debugging

### Flexibility
- **Generic StatusTracker**: Works for any grouping (reels, folder_types, projects, etc.)
- **Configurable transfer settings**: Easy to tune for different file sizes
- **Pluggable auth**: Support for config/instance/keyring modes

## Next Steps for upload_to_s3.py

The main script still needs these changes:

1. **Import helper modules** (top of file):
```python
from utils.shared.s3_upload_helpers import (
    load_cfg, resolve_project_base, resolve_session,
    resolve_max_concurrency, normalize_s3_prefix,
    s3_object_matches_local, parse_uploaded_keys_from_log
)
from utils.shared.s3_transfer_config import get_transfer_config, get_boto_config
from utils.shared.s3_status_tracker import StatusTracker
```

2. **Remove duplicate code**:
   - Delete `load_cfg`, `resolve_project_base`, `resolve_session`, etc.
   - Delete `md5_file`, `sha256_file`, `s3_object_matches_local`
   - Delete `StatusTracker` class
   - Delete `get_transfer_config` function
   - Keep only file collection and upload logic

3. **Add FOLDER_TYPE_EXTENSIONS** (already done):
```python
FOLDER_TYPE_EXTENSIONS = {
    'reels': {".mp4", ".json", ".csv", ".gpx"},
    'config': {".yaml", ".yml", ".json", ".txt"},
    'gis_data': {...},
    'logs': {...},
    'report': {...}
}
```

4. **Update `collect_upload_tasks()`**:
   - Add `folder_type` parameter
   - Add `project_key` parameter
   - Add `timestamp` parameter
   - Use `FOLDER_TYPE_EXTENSIONS[folder_type]` for filtering
   - Build S3 keys: `{project_key}/{folder_type}/[{timestamp}/]{rel_path}`

5. **Update `main()` argument parser**:
```python
parser.add_argument("--project-key", required=True)
parser.add_argument("--folder-type", choices=['reels', 'config', 'gis_data', 'logs', 'report'])
parser.add_argument("--include", nargs='+', choices=[...])
parser.add_argument("--exclude", nargs='+', choices=[...])
parser.add_argument("--timestamp", action='store_true')
parser.add_argument("--custom-timestamp", help="Custom timestamp (YYYYMMDD_HHMM)")
# Remove --prefix argument
```

6. **Update StatusTracker usage**:
```python
# For folder types:
tracker = StatusTracker(status_path, interval, group_key="folder_types")

# For reels (backward compat):
tracker = StatusTracker(status_path, interval, group_key="reels")
```

7. **Add folder type detection**:
```python
def detect_folder_types(base_folder):
    """Auto-detect folder types in project directory"""
    found = []
    for ft in ['reels', 'config', 'gis_data', 'logs', 'report']:
        if (base_folder / ft).is_dir():
            found.append(ft)
    return found
```

8. **Add multi-folder-type collection**:
```python
def collect_multi_type_tasks(base_folder, folder_types, project_key, timestamp=None):
    """Collect files for multiple folder types"""
    all_tasks = {}
    for folder_type in folder_types:
        tasks = collect_upload_tasks(
            base_folder / folder_type,
            FOLDER_TYPE_EXTENSIONS[folder_type],
            project_key,
            folder_type,
            timestamp
        )
        if tasks:
            all_tasks[folder_type] = tasks
    return all_tasks
```

## File Size Comparison

### Before Refactoring
```
upload_raw_reels_standalone_current.py:  1,077 lines
upload_project_files.py:                   330 lines
Total:                                   1,407 lines
```

### After Refactoring
```
upload_to_s3.py (estimated):             ~450 lines
utils/shared/s3_upload_helpers.py:        300 lines
utils/shared/s3_transfer_config.py:        90 lines
utils/shared/s3_status_tracker.py:        180 lines
Total:                                   1,020 lines

Reduction: ~27% fewer lines
Reusability: Helper modules can be used by other scripts
Maintainability: Much improved (single source of truth)
```

## Testing Checklist

Once `upload_to_s3.py` is updated:

- [ ] Import helper modules successfully
- [ ] Upload reels with `--include reels`
- [ ] Upload config with `--include config --timestamp`
- [ ] Upload multiple types with `--include config gis_data logs`
- [ ] Exclude reels with `--exclude reels`
- [ ] Resume works (S3 HEAD + CSV log)
- [ ] Status JSON updates correctly
- [ ] Large file optimization works (8GB+ files)
- [ ] SHA-256 verification for large files
- [ ] Graceful interrupt (Ctrl+C)
- [ ] Debug mode shows detailed logging

## Usage Examples (After Update)

```powershell
# Upload reels only
python upload_to_s3.py --config config.yaml --folder D:\reels \
  --project-key RMI25320 --include reels

# Upload artifacts with timestamp
python upload_to_s3.py --config config.yaml --folder D:\project \
  --project-key RMI25320 --include config logs report --timestamp

# Upload everything except reels
python upload_to_s3.py --config config.yaml --folder D:\project \
  --project-key RMI25320 --exclude reels --timestamp

# Large file upload with verification
python upload_to_s3.py --config config.yaml --folder D:\reels \
  --project-key RMI25320 --include reels --verify-large \
  --status-json status.json --debug
```

## Conclusion

✅ **Completed**: Created three well-organized helper modules
🔄 **In Progress**: Updating `upload_to_s3.py` to use helpers and add multi-type support
⏭️ **Next**: Complete main script refactoring and test all functionality

The refactoring significantly improves code organization while maintaining all the critical large-file handling features from the original `upload_raw_reels_standalone_current.py`.
