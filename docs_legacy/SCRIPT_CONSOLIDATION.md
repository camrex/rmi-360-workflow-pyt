# Upload Script Consolidation Summary

## Overview

The RMI 360 Workflow previously had two separate upload scripts with overlapping functionality:
- `upload_raw_reels_standalone.py` - Comprehensive reel upload with advanced resume features
- `upload_project_files.py` - Multi-type artifact upload with timestamp support

These have been **consolidated into a single unified script** that combines the best features of both.

## New Unified Script: `upload_to_s3.py`

### Key Features

✅ **All folder types in one script**
- reels, config, gis_data, logs, report

✅ **Robust resume mechanism**
- S3 HEAD checks with MD5 verification for small files
- Size-based matching for large/multipart uploads
- CSV logging as backup

✅ **Flexible selection**
- `--include` for specific folder types
- `--exclude` to skip certain types
- `--folder-type` for single-folder uploads

✅ **Timestamp support**
- `--timestamp` for auto-generated timestamps
- `--custom-timestamp` for specific versions
- Optional (no flag = direct to folder)

✅ **Live monitoring**
- `--status-json` for heartbeat status file
- `--status-interval` configurable
- Real-time progress tracking

✅ **Production-ready**
- Graceful interrupt handling (Ctrl+C)
- Dry-run mode
- Force re-upload option
- Detailed CSV logging

## Migration from Old Scripts

### Old Approach

**Upload reels:**
```bash
python scripts/upload_raw_reels_standalone.py \
  --config config.yaml \
  --folder D:/reels \
  --prefix RMI25320/reels/
```

**Upload config:**
```bash
python scripts/upload_project_files.py \
  --config config.yaml \
  --folder D:/config \
  --folder-type config \
  --project-key RMI25320
```

### New Unified Approach

**Upload reels:**
```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/reels \
  --project-key RMI25320 \
  --folder-type reels
```

**Upload config:**
```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/config \
  --project-key RMI25320 \
  --folder-type config \
  --timestamp
```

**Upload everything in one command:**
```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/Process360_Data/projects/RMI25320 \
  --project-key RMI25320 \
  --include reels config gis_data
```

## Download Script Update

The `download_project_files.py` script has been updated to **exclude reels by default**.

### Rationale

The orchestrator handles reel downloads based on the specific reels selected for processing. Manual reel downloads are rarely needed and can be large/expensive.

### Usage

**Default behavior (excludes reels):**
```bash
python scripts/download_project_files.py \
  --config config.yaml \
  --project-key RMI25320
# Downloads: config, gis_data
```

**Explicitly include reels (if needed):**
```bash
python scripts/download_project_files.py \
  --config config.yaml \
  --project-key RMI25320 \
  --include-reels
# Downloads: config, gis_data, reels
```

## File Cleanup

The following files should be removed as they are now obsolete:

- ❌ `scripts/upload_raw_reels_standalone.py` → Replaced by `upload_to_s3.py`
- ❌ `scripts/upload_project_files.py` → Replaced by `upload_to_s3.py`

**Note:** These files may still be present in the repository for backward compatibility during transition. Update any scripts or documentation that reference them.

## Common Use Cases

### 1. Upload Reels for New Project

```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/raw_reels/RMI25320 \
  --project-key RMI25320 \
  --folder-type reels
```

### 2. Upload Config/GIS Before Processing

```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/projects/RMI25320 \
  --project-key RMI25320 \
  --include config gis_data
```

### 3. Upload Artifacts After Processing (with timestamp)

```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/Process360_Data/projects/RMI25320 \
  --project-key RMI25320 \
  --include config logs report \
  --timestamp
```

### 4. Upload Everything Except Reels

```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/Process360_Data/projects/RMI25320 \
  --project-key RMI25320 \
  --exclude reels \
  --timestamp
```

### 5. Dry Run (preview what would be uploaded)

```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/Process360_Data/projects/RMI25320 \
  --project-key RMI25320 \
  --dry-run
```

## Resume Mechanism Comparison

### Old Scripts

**upload_raw_reels_standalone.py:**
- ✅ S3 HEAD checks
- ✅ MD5 verification (small files)
- ✅ Size matching (large files)
- ✅ CSV logging
- ❌ No timestamp support
- ❌ Reels only

**upload_project_files.py:**
- ❌ No S3 HEAD checks (CSV only)
- ❌ No MD5 verification
- ✅ CSV logging
- ✅ Timestamp support
- ✅ Multi-type (config, gis_data, logs, report)

### New Unified Script

**upload_to_s3.py:**
- ✅ S3 HEAD checks
- ✅ MD5 verification (small files)
- ✅ Size matching (large files)
- ✅ CSV logging
- ✅ Timestamp support
- ✅ All folder types (reels, config, gis_data, logs, report)
- ✅ Selective uploads (include/exclude)
- ✅ Live status JSON

## Configuration Integration

The unified script works seamlessly with the orchestrator's automatic artifact backup:

**config.yaml:**
```yaml
orchestrator:
  upload_artifacts_to_s3: true
  artifact_types:
    - config
    - logs
    - report
```

The orchestrator uses `utils/shared/backup_to_s3.py` which internally calls `upload_to_s3.py` functionality.

## Benefits of Consolidation

1. **Single Tool**: One script to learn and maintain
2. **Consistent Interface**: Same arguments across all folder types
3. **Best Features**: Combines robust resume with flexible selection
4. **Less Confusion**: No need to choose between multiple scripts
5. **Better Defaults**: Excludes reels from downloads by default
6. **Unified Logging**: Single CSV log for all uploads

## Breaking Changes

### Upload Scripts

❌ **Old:**
```bash
# Different scripts for different purposes
upload_raw_reels_standalone.py --prefix RMI25320/reels/
upload_project_files.py --folder-type config --timestamp
```

✅ **New:**
```bash
# Single script with consistent interface
upload_to_s3.py --folder-type reels --project-key RMI25320
upload_to_s3.py --folder-type config --project-key RMI25320 --timestamp
```

### Download Scripts

❌ **Old:**
```bash
# Downloaded everything by default (including reels)
download_project_files.py --folder-types config gis_data
```

✅ **New:**
```bash
# Excludes reels by default (orchestrator handles reels)
download_project_files.py  # Downloads: config, gis_data
download_project_files.py --include-reels  # Explicit flag needed for reels
```

## Documentation Updates

All documentation has been updated to reference the new consolidated scripts:

- ✅ **SCRIPTS_QUICK_REFERENCE.md** - Complete rewrite for `upload_to_s3.py`
- ✅ **ARTIFACT_BACKUP_GUIDE.md** - Updated manual upload examples
- ✅ **FOLDER_STRUCTURE_UPDATE.md** - Updated S3 upload examples
- ✅ **SCRIPT_CONSOLIDATION.md** - This document

## Testing Checklist

Before removing old scripts, verify:

- [ ] `upload_to_s3.py` successfully uploads reels
- [ ] `upload_to_s3.py` successfully uploads config with timestamp
- [ ] `upload_to_s3.py` successfully uploads multiple types with `--include`
- [ ] Resume works correctly (re-run same command skips uploaded files)
- [ ] MD5 verification works for small files
- [ ] Size-based skip works for large files
- [ ] `--dry-run` mode shows correct preview
- [ ] `download_project_files.py` excludes reels by default
- [ ] `download_project_files.py --include-reels` downloads reels
- [ ] Orchestrator automatic artifact backup still works

## Support

For issues or questions:

1. Check `SCRIPTS_QUICK_REFERENCE.md` for usage examples
2. Use `--dry-run` to preview uploads
3. Check CSV logs in `{project_dir}/logs/upload_log.csv`
4. Enable status JSON for live monitoring: `--status-json status.json`

## Version History

- **2025-10-30:** Script consolidation completed
  - Created `upload_to_s3.py` (unified upload)
  - Updated `download_project_files.py` (exclude reels by default)
  - Deprecated `upload_raw_reels_standalone.py`
  - Deprecated `upload_project_files.py`
