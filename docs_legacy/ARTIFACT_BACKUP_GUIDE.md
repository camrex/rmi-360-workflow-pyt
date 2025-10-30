# Artifact Backup to S3 - User Guide

## Overview

The RMI 360 Workflow now supports automatic backup of project artifacts (config, logs, reports, and GIS data) to S3. This feature provides:

- **Version Control**: Each processing run creates timestamped backups
- **Reproducibility**: Know exactly which config and logs were used for each run
- **Audit Trail**: Complete history of processing runs
- **Disaster Recovery**: All critical artifacts safely stored in S3

## Quick Start

### 1. Enable Automatic Backup

Add to your `config.yaml`:

```yaml
orchestrator:
  # Enable automatic artifact upload after processing completes
  upload_artifacts_to_s3: true

  # Choose which artifacts to upload
  artifact_types:
    - config        # The config.yaml used for this run
    - logs          # All log files (process, exiftool, etc.)
    - report        # HTML report and JSON data
    # - gis_data    # Uncomment to backup GIS reference data
```

### 2. Run Your Workflow

When the orchestrator completes, it will automatically upload the selected artifacts to S3:

```
s3://rmi-360-raw/{project_key}/config/{YYYYMMDD_HHMM}/config.yaml
s3://rmi-360-raw/{project_key}/logs/{YYYYMMDD_HHMM}/*.log
s3://rmi-360-raw/{project_key}/report/{YYYYMMDD_HHMM}/report.html
```

## Manual Upload

You can also manually upload artifacts using the unified `upload_to_s3.py` script:

```bash
# Upload logs from a completed run (with timestamp)
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/Process360_Data/projects/RMI25320 \
  --project-key RMI25320 \
  --include logs \
  --timestamp

# Upload multiple artifact types at once
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/Process360_Data/projects/RMI25320 \
  --project-key RMI25320 \
  --include config logs report \
  --timestamp

# Upload with custom timestamp
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/Process360_Data/projects/RMI25320 \
  --project-key RMI25320 \
  --include report \
  --custom-timestamp 20251030_1200

# Upload single folder type without timestamp
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/Process360_Data/projects/RMI25320/config \
  --project-key RMI25320 \
  --folder-type config
```

## S3 Structure with Timestamps

### Example Structure

```
s3://rmi-360-raw/RMI25320/
├── reels/
│   └── reel_0001/...
│
├── config/
│   ├── 20251030_0900/              # First run
│   │   └── config.yaml
│   ├── 20251030_1430/              # Second run (different settings)
│   │   └── config.yaml
│   └── 20251031_1015/              # Third run
│       └── config.yaml
│
├── logs/
│   ├── 20251030_0900/
│   │   ├── process_log.txt
│   │   ├── exiftool_log.txt
│   │   ├── enhance_log.csv
│   │   └── ...
│   ├── 20251030_1430/
│   │   └── ...
│   └── 20251031_1015/
│       └── ...
│
├── report/
│   ├── 20251030_0900/
│   │   ├── report.html
│   │   ├── report_data_RMI25320.json
│   │   └── assets/...
│   ├── 20251030_1430/
│   │   └── ...
│   └── 20251031_1015/
│       └── ...
│
└── gis_data/                       # Optional
    ├── 20251030_0900/
    │   ├── centerline.shp
    │   └── ...
    └── 20251030_1430/
        └── ...
```

### Benefits of Timestamping

1. **No Overwrites**: Each run is preserved
2. **Easy Correlation**: All artifacts from the same run share the same timestamp
3. **Version History**: Track how configs and settings evolved
4. **Reproducibility**: Re-run with exact same config if needed
5. **Debugging**: Access logs from any historical run

## Artifact Types

### config
- **What**: The `config.yaml` file used for the processing run
- **Why**: Reproduce exact processing parameters
- **Example files**: `config.yaml`, custom settings JSON

### logs
- **What**: All log files generated during processing
- **Why**: Troubleshooting, audit trail, performance metrics
- **Example files**:
  - `process_log.txt` - Main orchestrator log
  - `exiftool_log.txt` - ExifTool operations
  - `enhance_log.csv` - Image enhancement details
  - `mosaic_processor_output.log` - Mosaic Processor output

### report
- **What**: HTML reports, JSON data, and associated assets
- **Why**: Share results, historical comparison
- **Example files**:
  - `report.html` - Final HTML report
  - `report_data_RMI25320.json` - Structured report data
  - `assets/*.png` - Charts and images

### gis_data (optional)
- **What**: GIS reference data used during processing
- **Why**: Document exact spatial references used
- **Example files**: Shapefiles, geodatabases, KML files

## Configuration Options

### orchestrator.upload_artifacts_to_s3

**Type**: Boolean
**Default**: `false`
**Description**: Enable/disable automatic artifact upload after workflow completion

```yaml
orchestrator:
  upload_artifacts_to_s3: true  # Enable automatic upload
```

### orchestrator.artifact_types

**Type**: List of strings
**Default**: `['config', 'logs', 'report']`
**Choices**: `config`, `logs`, `report`, `gis_data`
**Description**: Which artifact types to upload

```yaml
orchestrator:
  artifact_types:
    - config
    - logs
    - report
    # - gis_data  # Uncomment if needed
```

## Use Cases

### 1. Standard Production Run

```yaml
orchestrator:
  upload_artifacts_to_s3: true
  artifact_types:
    - config
    - logs
    - report
```

**Result**: Config, logs, and report are uploaded after each run, creating a complete audit trail.

### 2. Experimental Run (No Upload)

```yaml
orchestrator:
  upload_artifacts_to_s3: false
```

**Result**: No artifacts uploaded (test runs, development work).

### 3. Complete Archival

```yaml
orchestrator:
  upload_artifacts_to_s3: true
  artifact_types:
    - config
    - logs
    - report
    - gis_data
```

**Result**: Everything uploaded for maximum reproducibility.

### 4. Logs Only

```yaml
orchestrator:
  upload_artifacts_to_s3: true
  artifact_types:
    - logs
```

**Result**: Only log files uploaded (troubleshooting focus).

## File Extensions

The upload process automatically filters files by extension:

| Artifact Type | Allowed Extensions |
|--------------|-------------------|
| **config** | `.yaml`, `.yml`, `.json`, `.txt` |
| **logs** | `.txt`, `.log`, `.csv`, `.args` |
| **report** | `.html`, `.json`, `.png`, `.jpg`, `.jpeg`, `.pdf` |
| **gis_data** | `.shp`, `.shx`, `.dbf`, `.prj`, `.cpg`, `.sbn`, `.sbx`, `.xml`, `.geojson`, `.json`, `.kml`, `.kmz`, `.gdb`, `.gpkg` |

## Workflow Integration

The artifact upload happens **after** all processing steps complete:

1. ✅ Run all pipeline steps (mosaic processor, add images, enhance, etc.)
2. ✅ Generate final HTML report
3. 📤 **Upload artifacts to S3** (if enabled)
4. 🎉 Workflow complete

If any step fails, artifacts are not uploaded (workflow didn't complete successfully).

## Download Artifacts

To download artifacts from a specific run:

```bash
# Download specific timestamp folder
aws s3 sync s3://rmi-360-raw/RMI25320/logs/20251030_1430/ ./downloaded_logs/

# Download all logs
aws s3 sync s3://rmi-360-raw/RMI25320/logs/ ./all_logs/

# Download specific file
aws s3 cp s3://rmi-360-raw/RMI25320/config/20251030_1430/config.yaml ./config.yaml
```

Or use the AWS console to browse and download files.

## Best Practices

### 1. Always Upload for Production

Enable artifact upload for all production runs:

```yaml
orchestrator:
  upload_artifacts_to_s3: true
```

### 2. Include Config and Logs

At minimum, always upload config and logs for reproducibility:

```yaml
artifact_types:
  - config
  - logs
```

### 3. Clean Up Old Artifacts

Periodically clean up S3 to manage storage costs:

```bash
# List all artifact timestamps
aws s3 ls s3://rmi-360-raw/RMI25320/logs/

# Delete old runs (e.g., older than 90 days)
# Use S3 lifecycle policies or manual deletion
```

### 4. Tag Important Runs

For critical runs, add a marker file:

```bash
# After a particularly important run
aws s3 cp - s3://rmi-360-raw/RMI25320/logs/20251030_1430/_IMPORTANT.txt <<< "Final production run - DO NOT DELETE"
```

### 5. Document Config Changes

If you modify config between runs, add a comment:

```yaml
# config.yaml
schema_version: 1.2.0

# CHANGE LOG:
# 2025-10-30 14:30 - Increased enhancement sigma from 1.0 to 1.5
# 2025-10-30 09:00 - Initial production config

project:
  slug: "RMI25320"
  ...
```

## Troubleshooting

### "Missing aws.s3_bucket_raw in config"

Add to your config:

```yaml
aws:
  s3_bucket_raw: "rmi-360-raw"
```

### "Failed to upload artifacts to S3"

Check:
1. AWS credentials are configured
2. IAM role/user has S3 write permissions
3. Bucket exists and is accessible
4. Network connectivity to AWS

### Artifacts Not Uploading

Verify:
1. `upload_artifacts_to_s3: true` in config
2. `artifact_types` list is not empty
3. Workflow completed successfully (no failures)
4. Files exist in local project folders

### Large GIS Data Upload Slow

GIS geodatabases can be very large. Consider:
1. Excluding `gis_data` from routine uploads
2. Upload GIS data once manually, then comment out in config
3. Use AWS CLI for large GIS data uploads

## Cost Considerations

### Storage Costs

S3 Standard storage pricing (as of 2025):
- First 50 TB: ~$0.023 per GB/month

Example cost calculation:
- Config: ~50 KB per run
- Logs: ~10 MB per run
- Report: ~5 MB per run
- **Total per run**: ~15 MB
- **100 runs**: ~1.5 GB = ~$0.03/month

GIS data can vary widely (1 MB to several GB).

### Transfer Costs

Upload to S3 is **free**.
Download from S3: ~$0.09 per GB (first 10 TB/month).

### Recommendations

1. Upload config/logs/report for all runs (minimal cost)
2. Upload GIS data selectively (only when it changes)
3. Set up S3 lifecycle policies to transition old artifacts to cheaper storage (Glacier) after 90 days
4. Delete test/development runs periodically

## Summary

Artifact backup to S3 provides:
- ✅ Complete audit trail
- ✅ Version control for configs
- ✅ Reproducibility
- ✅ Disaster recovery
- ✅ Easy sharing of results
- ✅ Minimal additional cost

Enable it for production runs and enjoy peace of mind knowing all your processing artifacts are safely backed up!
