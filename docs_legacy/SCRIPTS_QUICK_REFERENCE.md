# Quick Reference: Upload and Download Scripts

## Upload Scripts

### Unified Upload Script (upload_to_s3.py)

Upload any combination of project files (reels, config, gis_data, logs, report) to S3 in one run.

```bash
python scripts/upload_to_s3.py \
  --config path/to/config.yaml \
  --folder path/to/project_folder \
  --project-key RMI25320 \
  [--include reels config gis_data] \
  [--exclude logs report] \
  [--timestamp] \
  [--dry-run] \
  [--force]
```

**Features:**
- Unified script for all folder types (reels, config, gis_data, logs, report)
- Resume support via S3 HEAD checks and CSV logging
- MD5 verification for small files (<64MB)
- Live status JSON heartbeat for monitoring
- Selective uploads via --include/--exclude
- Automatic timestamp subfolder organization
- Graceful interrupt handling (Ctrl+C)

**Examples:**

Upload reels only:
```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/Process360_Data/projects/RMI25320 \
  --project-key RMI25320 \
  --include reels
```

Upload config and gis_data with timestamp:
```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/Process360_Data/projects/RMI25320 \
  --project-key RMI25320 \
  --include config gis_data \
  --timestamp
# Uploads to: s3://rmi-360-raw/RMI25320/config/20251030_1430/...
```

Upload everything except reels:
```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/Process360_Data/projects/RMI25320 \
  --project-key RMI25320 \
  --exclude reels
```

Upload single folder type:
```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/Process360_Data/projects/RMI25320/config \
  --project-key RMI25320 \
  --folder-type config \
  --timestamp
```

With live status JSON:
```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/Process360_Data/projects/RMI25320 \
  --project-key RMI25320 \
  --include reels \
  --status-json status.json \
  --status-interval 2.0
```

Force re-upload (ignore resume):
```bash
python scripts/upload_to_s3.py \
  --config config.yaml \
  --folder D:/Process360_Data/projects/RMI25320 \
  --project-key RMI25320 \
  --include config logs report \
  --force
```

**Supported file types:**
- **reels**: `.mp4`, `.json`, `.csv`, `.gpx`
- **config**: `.yaml`, `.yml`, `.json`, `.txt`
- **gis_data**: `.shp`, `.shx`, `.dbf`, `.prj`, `.cpg`, `.sbn`, `.sbx`, `.xml`, `.geojson`, `.json`, `.kml`, `.kmz`, `.gdb`, `.gpkg`
- **logs**: `.txt`, `.log`, `.csv`, `.args`
- **report**: `.html`, `.json`, `.png`, `.jpg`, `.jpeg`, `.pdf`

## Download Scripts

### Download Project Files

Download config, GIS data, and optionally other artifacts from S3 to local project directory.

**Note**: Reels are excluded by default (orchestrator handles reel downloads). Use `--include-reels` to explicitly download reels.

```bash
python scripts/download_project_files.py \
  --config path/to/config.yaml \
  --project-key RMI25320 \
  [--bucket rmi-360-raw] \
  [--folder-types config gis_data] \
  [--include-reels] \
  [--local-dir D:/Process360_Data/projects/RMI25320] \
  [--max-workers 16] \
  [--force] \
  [--dry-run]
```

**Examples:**

Download both config and gis_data (default, excludes reels):
```bash
python scripts/download_project_files.py \
  --config config.yaml \
  --project-key RMI25320
```

Download only config files:
```bash
python scripts/download_project_files.py \
  --config config.yaml \
  --project-key RMI25320 \
  --folder-types config
```

Download including reels (normally orchestrator handles this):
```bash
python scripts/download_project_files.py \
  --config config.yaml \
  --project-key RMI25320 \
  --folder-types config gis_data \
  --include-reels
```

Download to custom location:
```bash
python scripts/download_project_files.py \
  --config config.yaml \
  --project-key RMI25320 \
  --local-dir C:/MyProjects/RMI25320
```

Force re-download (overwrite existing):
```bash
python scripts/download_project_files.py \
  --config config.yaml \
  --project-key RMI25320 \
  --force
```

## Automatic Artifact Upload (NEW)

The orchestrator can automatically upload project artifacts to S3 after workflow completion for backup and version control.

### Configuration

Add to your `config.yaml`:

```yaml
orchestrator:
  # Enable automatic artifact upload after processing
  upload_artifacts_to_s3: true

  # Artifact types to upload (config, logs, report, gis_data)
  artifact_types:
    - config
    - logs
    - report
    # - gis_data  # Uncomment if needed
```

### Behavior

When enabled, the orchestrator will:
1. Complete all processing steps
2. Generate the final report
3. Upload selected artifacts to S3 with timestamp:
   ```
   s3://rmi-360-raw/{project_key}/config/{YYYYMMDD_HHMM}/config.yaml
   s3://rmi-360-raw/{project_key}/logs/{YYYYMMDD_HHMM}/process_log.txt
   s3://rmi-360-raw/{project_key}/report/{YYYYMMDD_HHMM}/report.html
   ```

### Benefits

- **Version Control**: Multiple runs create timestamped versions
- **Reproducibility**: Know exactly which config was used for each run
- **Audit Trail**: Complete logs and reports for every processing run
- **Backup**: Artifacts safely stored in S3

## Common Options

### --dry-run
Preview what would be uploaded/downloaded without making changes.

```bash
python scripts/upload_project_files.py \
  --config config.yaml \
  --folder config/ \
  --folder-type config \
  --project-key RMI25320 \
  --dry-run
```

### --force (download only)
Re-download files even if they already exist locally.

```bash
python scripts/download_project_files.py \
  --config config.yaml \
  --project-key RMI25320 \
  --force
```

## Typical Workflow

### Setting Up a New Project on EC2

1. **Upload all project files (reels, config, gis_data) in one command:**
   ```bash
   python scripts/upload_to_s3.py \
     --config config.yaml \
     --folder D:/raw_captures/RMI25320 \
     --project-key RMI25320 \
     --include reels config gis_data
   ```

   Or upload separately:

   **a. Upload reels:**
   ```bash
   python scripts/upload_to_s3.py \
     --config config.yaml \
     --folder D:/raw_captures/RMI25320/reels \
     --project-key RMI25320 \
     --folder-type reels
   ```

   **b. Upload config files (optional):**
   ```bash
   python scripts/upload_to_s3.py \
     --config config.yaml \
     --folder D:/configs/RMI25320 \
     --project-key RMI25320 \
     --folder-type config
   ```

   **c. Upload GIS data (optional):**
   ```bash
   python scripts/upload_to_s3.py \
     --config config.yaml \
     --folder D:/gis/RMI25320 \
     --project-key RMI25320 \
     --folder-type gis_data
   ```

2. **On EC2, download config/GIS (optional, reels excluded by default):**
   ```bash
   python scripts/download_project_files.py \
     --config config.yaml \
     --project-key RMI25320
   ```

3. **Run the orchestrator:**
   - Reels are auto-downloaded from S3 based on selected reels
   - If `upload_artifacts_to_s3: true`, artifacts are auto-uploaded after completion

## Resume Support

The unified upload script (`upload_to_s3.py`) supports robust resume functionality:
- S3 HEAD checks to verify if files already exist
- MD5 verification for small files (<64MB)
- Size-based matching for large/multipart files
- CSV logging as backup resume mechanism
- Re-running the same upload will skip already-uploaded files
- Logs stored in `{project_dir}/logs/upload_log.csv`

## Error Handling

If an upload or download fails:

1. Check the log files in `{project_dir}/logs/`
2. Verify AWS credentials are configured
3. Check network connectivity
4. Verify S3 bucket permissions
5. Re-run the script (it will resume from where it left off)

## S3 Bucket Structure

After running these scripts and the orchestrator, your S3 bucket will have:

```
s3://rmi-360-raw/
└── RMI25320/
    ├── reels/
    │   ├── reel_0001/
    │   │   ├── video.mp4
    │   │   ├── metadata.json
    │   │   └── ...
    │   └── reel_0002/
    │       └── ...
    ├── config/
    │   ├── 20251030_1200/        # Uploaded manually or by orchestrator
    │   │   └── config.yaml
    │   └── 20251030_1430/        # Another run with different config
    │       └── config.yaml
    ├── gis_data/
    │   ├── 20251030_1200/        # Optional GIS reference data
    │   │   ├── reference.shp
    │   │   ├── reference.shx
    │   │   └── ...
    │   └── no_timestamp_folder/  # If uploaded with --no-timestamp
    │       └── ...
    ├── logs/
    │   └── 20251030_1430/        # Auto-uploaded by orchestrator
    │       ├── process_log.txt
    │       ├── exiftool_log.txt
    │       └── ...
    └── report/
        └── 20251030_1430/        # Auto-uploaded by orchestrator
            ├── report.html
            ├── report_data_RMI25320.json
            └── ...
```

**Timestamping Benefits:**
- Multiple runs create separate timestamped folders
- Easy to correlate artifacts from the same processing run
- Version history for configs, logs, and reports
- No file overwrites - all runs are preserved

## Local Directory Structure (EC2)

After downloading, your EC2 instance will have:

```
D:/Process360_Data/projects/RMI25320/
├── reels/          # Auto-downloaded by orchestrator
├── config/         # Downloaded by download_project_files.py
├── gis_data/       # Downloaded by download_project_files.py
├── backups/        # Created by workflow
├── logs/           # Created by workflow
├── panos/          # Created by workflow
└── report/         # Created by workflow
```

## Troubleshooting

### "Missing aws.s3_bucket_raw in config"
Add to your `config.yaml`:
```yaml
aws:
  s3_bucket_raw: "rmi-360-raw"
```

### "Missing runtime.local_root in configuration"
Add to your `config.yaml`:
```yaml
runtime:
  local_root: "D:/Process360_Data"
```

### Files not uploading
- Check file extensions match the allowed types
- Verify folder structure is correct
- Check AWS credentials and permissions

### Downloads failing
- Verify S3 bucket name and project key
- Check IAM role/user has S3 read permissions
- Ensure files exist in S3 at the expected paths
