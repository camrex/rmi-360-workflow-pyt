#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
upload_to_s3.py - Unified S3 Upload for RMI 360 Workflow
=========================================================

Uploads project files (reels, config, gis_data, logs, report) to S3 with:
• Crash-safe resume via S3 HEAD checks and CSV log
• Multi-folder-type support with flexible selection
• Live progress tracking (JSON heartbeat)
• Adaptive upload optimization for large files
• SHA-256 verification for data integrity

USAGE:
    # Upload reels only
    python upload_to_s3.py --config config.yaml --folder D:\reels --project-key RMI25320 --folder-type reels

    # Upload multiple types with timestamp
    python upload_to_s3.py --config config.yaml --folder D:\project --project-key RMI25320 --include config gis_data --timestamp

    # Dry run (auto-detect all types)
    python upload_to_s3.py --config config.yaml --folder D:\project --project-key RMI25320 --dry-run

FOLDER TYPES:
    reels     - .mp4, .json, .csv, .gpx (360 video files)
    config    - .yaml, .yml, .json, .txt
    gis_data  - shapefiles, geodatabases, KML, GeoJSON
    logs      - .txt, .log, .csv, .args
    report    - .html, .json, .png, .jpg, .pdf

RESUME STRATEGY:
    1. S3 HEAD check (primary): Skip files already in S3
       - Small files: MD5 hash comparison
       - Large files: SHA-256, timestamp heuristics, or size matching
    2. CSV log (secondary): Honor prior upload entries
    3. Use --force to override and re-upload all files

LARGE FILE OPTIMIZATION:
    Auto-adjusts settings based on file size:
    • <512MB: 8MB parts, full concurrency
    • 512MB-8GB: 64MB parts, reduced concurrency
    • >8GB: 128MB parts, minimal concurrency
    • ≥1GB: 3 retries with exponential backoff, 5min read timeout

OPTIONS:
    --folder-type {reels|config|gis_data|logs|report}  Single type
    --include TYPE [TYPE ...]                          Multiple types
    --exclude TYPE [TYPE ...]                          Exclude types
    --timestamp                                        Add YYYYMMDD_HHMM subfolder
    --verify-large                                     SHA-256 verification (slower)
    --skip-large-check                                 Always re-upload large files
    --force                                            Re-upload all files
    --debug                                            Detailed logging

MONITORING:
    CSV: <project_base>/logs/upload_log.csv (real-time, crash-safe)
    JSON: --status-json path (live heartbeat, ~2s updates)

    Monitor: Get-Content "logs\upload_log.csv" -Wait -Tail 10

For full documentation, see: UPLOAD_TO_S3_CHANGES.md
"""

import argparse
import csv
import mimetypes
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Dict, Optional

# Add repo root to path for imports
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Third-party deps: boto3, pyyaml
try:
    import yaml  # PyYAML
except ImportError:
    print("PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    raise

try:
    import boto3
    from boto3.s3.transfer import S3Transfer
    from botocore.exceptions import ClientError
except ImportError:
    print("boto3 is required. Install with: pip install boto3", file=sys.stderr)
    raise

# Import helper modules
from utils.shared.s3_upload_helpers import (
    load_cfg,
    resolve_project_base,
    resolve_session,
    resolve_max_concurrency,
    normalize_s3_prefix,
    s3_object_matches_local,
    parse_uploaded_keys_from_log
)
from utils.shared.s3_transfer_config import get_transfer_config, get_boto_config
from utils.shared.s3_status_tracker import StatusTracker


# File extension definitions by folder type
FOLDER_TYPE_EXTENSIONS = {
    'reels': {".mp4", ".json", ".csv", ".gpx"},
    'config': {".yaml", ".yml", ".json", ".txt"},
    'gis_data': {".shp", ".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".xml",
                 ".geojson", ".json", ".kml", ".kmz", ".gpkg"},
    'logs': {".txt", ".log", ".csv", ".args"},
    'report': {".html", ".json", ".png", ".jpg", ".jpeg", ".pdf"}
}

# Special directory types that should include ALL contents (e.g., .gdb geodatabases)
INCLUDE_ALL_CONTENTS_DIRS = {".gdb", ".gpkg"}  # File Geodatabases and GeoPackages


# -----------------------------
# Helper functions
# -----------------------------

def guess_content_type(path: Path) -> Optional[str]:
    """Guess MIME type from file extension."""
    ctype, _ = mimetypes.guess_type(str(path))
    return ctype


def detect_folder_types(base_folder: Path) -> List[str]:
    """
    Auto-detect folder types present in base_folder.
    Looks for subdirectories: reels, config, gis_data, logs, report
    """
    detected = []
    for folder_type in ['reels', 'config', 'gis_data', 'logs', 'report']:
        if (base_folder / folder_type).is_dir():
            detected.append(folder_type)
    return detected


def collect_upload_tasks(
    base_dir: Path,
    allow_exts: set,
    project_key: str,
    folder_type: str,
    timestamp: Optional[str] = None
) -> List[Tuple[Path, str]]:
    """
    Collect files to upload from base_dir with specified extensions.

    Args:
        base_dir: Local directory containing files
        allow_exts: Set of allowed file extensions (e.g., {".mp4", ".json"})
        project_key: Project identifier (e.g., "RMI25320")
        folder_type: Type of folder (reels, config, gis_data, logs, report)
        timestamp: Optional timestamp subfolder (e.g., "20251030_1430")

    Returns:
        List of (local_path, s3_key) tuples
    """
    tasks: List[Tuple[Path, str]] = []
    base = base_dir.resolve()
    base_str = str(base)

    for root, dirs, files in os.walk(base_str):
        root_path = Path(root)

        # Check if we're inside a special directory (e.g., .gdb)
        # If so, include ALL files regardless of extension
        inside_special_dir = False
        for special_ext in INCLUDE_ALL_CONTENTS_DIRS:
            # Check if any parent directory has this extension
            for parent in root_path.parents:
                if parent.suffix.lower() == special_ext:
                    inside_special_dir = True
                    break
            if inside_special_dir:
                break

        for name in files:
            ext = os.path.splitext(name)[1].lower()

            # Include file if:
            # 1. We're inside a special directory (.gdb, etc.), OR
            # 2. File extension is in the allowed list, OR
            # 3. No extension filter (allow_exts is empty)
            if inside_special_dir or ext in allow_exts or not allow_exts:
                full = Path(root) / name
                rel = os.path.relpath(str(full), base_str).replace("\\", "/")

                # Build S3 key: {project_key}/{folder_type}/[{timestamp}/]{rel_path}
                if timestamp:
                    key = f"{project_key}/{folder_type}/{timestamp}/{rel}"
                else:
                    key = f"{project_key}/{folder_type}/{rel}"

                tasks.append((full, key))

    return tasks


def collect_multi_folder_tasks(
    base_folder: Path,
    folder_types: List[str],
    project_key: str,
    timestamp: Optional[str] = None
) -> Dict[str, List[Tuple[Path, str]]]:
    """
    Collect files for multiple folder types.

    Returns:
        Dict mapping folder_type -> [(local_path, s3_key), ...]
    """
    all_tasks: Dict[str, List[Tuple[Path, str]]] = {}

    for folder_type in folder_types:
        local_folder = base_folder / folder_type if (base_folder / folder_type).is_dir() else base_folder
        if not local_folder.exists():
            continue

        allow_exts = FOLDER_TYPE_EXTENSIONS.get(folder_type, set())
        tasks = collect_upload_tasks(local_folder, allow_exts, project_key, folder_type, timestamp)

        if tasks:
            all_tasks[folder_type] = tasks

    return all_tasks


def reel_from_key(s3_key: str, project_key: str, folder_type: str = "reels") -> str:
    """
    Derive reel name from an S3 key by taking the first path segment AFTER the folder type.
    For reels: project_key/reels/REEL_NAME/file.mp4 -> REEL_NAME
    For other types: returns the folder type itself
    """
    if folder_type != "reels":
        return folder_type

    # Expected format: {project_key}/{folder_type}/{reel_name}/{files}
    prefix = f"{project_key}/{folder_type}/"

    if s3_key.startswith(prefix):
        rest = s3_key[len(prefix):]
        # Get the first path segment (reel name)
        return rest.split("/", 1)[0] if "/" in rest else rest

    # Fallback: try to extract something reasonable
    parts = s3_key.split("/")
    if len(parts) >= 3:
        return parts[2]  # Assume position 2 is reel name

    return folder_type


# -----------------------------
# Main
# -----------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description="Upload RMI 360 project files to S3 with resume and live status tracking."
    )
    p.add_argument("--config", required=True, help="Path to config.yaml (must contain aws block).")
    p.add_argument("--folder", required=True, help="Local folder containing files to upload.")
    p.add_argument("--project-key", required=True, help="Project key (e.g., RMI25320).")
    p.add_argument("--project-base", dest="project_base",
                   help="Base folder for logs; defaults to the folder containing the config file.")

    # Folder type selection (mutually exclusive groups)
    folder_group = p.add_mutually_exclusive_group()
    folder_group.add_argument("--folder-type", choices=['reels', 'config', 'gis_data', 'logs', 'report'],
                              help="Single folder type to upload.")
    folder_group.add_argument("--include", nargs='+', choices=['reels', 'config', 'gis_data', 'logs', 'report'],
                              help="Folder types to include.")
    folder_group.add_argument("--exclude", nargs='+', choices=['reels', 'config', 'gis_data', 'logs', 'report'],
                              help="Folder types to exclude.")

    # Timestamp options
    p.add_argument("--timestamp", action="store_true", help="Add timestamp subfolder (YYYYMMDD_HHMM).")
    p.add_argument("--custom-timestamp", help="Custom timestamp string (e.g., 20251030_1430).")

    # Upload options
    p.add_argument("--dry-run", action="store_true", help="List would-be uploads and exit.")
    p.add_argument("--force", action="store_true", help="Force re-upload even if S3 already has the object.")
    p.add_argument("--skip-large-check", action="store_true", help="Skip size-only matching for large files; always re-upload them.")
    p.add_argument("--verify-large", action="store_true", help="Use SHA-256 verification for large files (slower but more reliable).")
    p.add_argument("--debug", action="store_true", help="Enable debug output for troubleshooting.")

    # Monitoring
    p.add_argument("--status-json", help="Path to write live status JSON (heartbeat).")
    p.add_argument("--status-interval", type=float, default=2.0, help="Seconds between status writes (default 2.0).")

    args = p.parse_args()

    cfg_path = Path(args.config).resolve()
    local_folder = Path(args.folder).resolve()

    if not cfg_path.exists():
        print(f"[ERROR] Config not found: {cfg_path}", file=sys.stderr)
        return 2
    if not local_folder.exists():
        print(f"[ERROR] Local folder not found: {local_folder}", file=sys.stderr)
        return 2

    cfg = load_cfg(cfg_path)
    aws = cfg.get("aws", {})
    region = aws.get("region")
    bucket = aws.get("s3_bucket_raw")
    auth_mode = aws.get("auth_mode", "config")

    if not region or not bucket:
        print("[ERROR] aws.region and aws.s3_bucket_raw are required in config.", file=sys.stderr)
        return 2

    project_base = resolve_project_base(args.project_base, cfg, cfg_path)
    log_dir = (project_base / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_csv = log_dir / "upload_log.csv"

    # Determine folder types to process
    if args.folder_type:
        folder_types = [args.folder_type]
    elif args.include:
        folder_types = args.include
    elif args.exclude:
        all_types = detect_folder_types(local_folder) or ['reels', 'config', 'gis_data', 'logs', 'report']
        folder_types = [ft for ft in all_types if ft not in args.exclude]
    else:
        # Auto-detect
        folder_types = detect_folder_types(local_folder)
        if not folder_types:
            folder_types = ['reels']  # Default to reels if nothing detected

    # Determine timestamp
    timestamp = None
    if args.custom_timestamp:
        timestamp = args.custom_timestamp
    elif args.timestamp:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    print(f"[INFO] Starting S3 upload")
    print(f"[INFO] Config:       {cfg_path}")
    print(f"[INFO] Project base: {project_base}")
    print(f"[INFO] Local folder: {local_folder}")
    print(f"[INFO] S3 bucket:    {bucket}")
    print(f"[INFO] Project key:  {args.project_key}")
    print(f"[INFO] Folder types: {', '.join(folder_types)}")
    if timestamp:
        print(f"[INFO] Timestamp:    {timestamp}")
    print(f"[INFO] Auth mode:    {auth_mode}")

    # Collect files
    tasks = collect_multi_folder_tasks(local_folder, folder_types, args.project_key, timestamp)

    if not tasks:
        print("[WARNING] No files found to upload", file=sys.stderr)
        return 0

    total_files = sum(len(file_list) for file_list in tasks.values())
    print(f"[INFO] Discovered {total_files} files across {len(tasks)} folder type(s)")

    # Group tasks by folder type and reel (for reels folder type)
    groups: Dict[str, Dict[str, List[Tuple[Path, str]]]] = {}
    for folder_type, file_list in tasks.items():
        if folder_type == "reels":
            # Group by reel name
            reel_groups: Dict[str, List[Tuple[Path, str]]] = {}
            for fpath, key in file_list:
                rname = reel_from_key(key, args.project_key, folder_type)
                reel_groups.setdefault(rname, []).append((fpath, key))
            groups[folder_type] = reel_groups
        else:
            # Single group for non-reel folder types
            groups[folder_type] = {folder_type: file_list}

    # Dry run before doing any AWS calls
    if args.dry_run:
        print("\n[DRY-RUN] Would upload the following (sample files shown):")
        shown = 0
        for folder_type in sorted(groups.keys()):
            for group_name in sorted(groups[folder_type].keys()):
                file_list = groups[folder_type][group_name]
                print(f"[DRY-RUN] {folder_type}/{group_name} (files={len(file_list)})")
                for fpath, key in file_list[:5]:
                    print(f"  [DRY-RUN] would upload: {fpath}  ->  s3://{bucket}/{key}")
                    shown += 1
                    if shown >= 25:
                        break
                if shown >= 25:
                    break
        if total_files > shown:
            print(f"[DRY-RUN] ...and {total_files - shown} more")
        print("[DRY-RUN] Exiting without uploading.")
        return 0

    # AWS session and S3 client
    session = resolve_session(auth_mode)
    boto_cfg = get_boto_config()
    s3 = session.client("s3", region_name=region, config=boto_cfg)

    max_workers = resolve_max_concurrency(aws.get("max_workers", "cpu*4"))

    # Default transfer config (will be overridden per file based on size)
    tcfg = get_transfer_config(64 * 1024 * 1024, max_workers)  # Default for 64MB
    transfer = S3Transfer(s3, config=tcfg)

    # Determine group_key for StatusTracker based on folder types
    if len(folder_types) == 1 and folder_types[0] == 'reels':
        group_key = "reels"
    else:
        group_key = "folder_types"

    # Status tracker
    status_path = Path(args.status_json).resolve() if args.status_json else None
    tracker = StatusTracker(status_path, args.status_interval, group_key=group_key)

    # Set totals for each group
    for folder_type in groups:
        for group_name, file_list in groups[folder_type].items():
            tracker.set_totals({group_name: len(file_list)})

    # Ctrl+C / SIGTERM graceful exit
    def _graceful_exit(signum, frame):
        try:
            tracker._flush(force=True)
        finally:
            print("\n[INFO] Received signal, exiting gracefully.", file=sys.stderr)
            sys.exit(130)

    signal.signal(signal.SIGINT, _graceful_exit)
    # SIGTERM is not available on Windows
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, _graceful_exit)

    # Resume via prior log (secondary to S3 HEAD)
    already = parse_uploaded_keys_from_log(log_csv)

    # Check if file exists and has content before opening in append mode
    csv_exists = log_csv.exists()
    csv_has_content = csv_exists and log_csv.stat().st_size > 0

    print(f"[INFO] CSV log file: {log_csv}")
    print(f"[INFO] CSV exists: {csv_exists}, has content: {csv_has_content}")

    if args.debug:
        print(f"[DEBUG] Found {len(already)} previously uploaded keys from log")

    # Use context manager for proper file handling
    try:
        with open(log_csv, "a", newline="", encoding="utf-8", buffering=1) as fcsv:
            writer = csv.writer(fcsv)

            # Write header if file is new or empty
            if not csv_has_content:
                header = [
                    "timestamp", "local_file", "s3_key", "status", "error",
                    "size_bytes", "duration_sec", "content_type"
                ]
                writer.writerow(header)
                fcsv.flush()  # Force immediate write
                print(f"[INFO] CSV header written to new file")
                if args.debug:
                    print(f"[DEBUG] Header: {header}")

            # CSV is ready for writing
            if args.debug:
                print(f"[DEBUG] CSV writer initialized and ready")

            uploaded = skipped = failed = 0
            total_size = 0
            start = time.time()

            print(f"[INFO] Uploading to s3://{bucket}/ ({total_files} files)")

            # Process per folder type and group
            for folder_type in sorted(groups.keys()):
                for group_name, file_list in sorted(groups[folder_type].items()):
                    print(f"\n[{folder_type.upper()}] >>> Starting {group_name} (files={len(file_list)})")
                    tracker.start_group(group_name, planned_files=len(file_list))

                    for fpath, key in file_list:
                        size = fpath.stat().st_size
                        ctype = guess_content_type(fpath)

                        if args.debug:
                            print(f"[DEBUG] Checking: {fpath.name} -> {key}")

                        # S3 existence / identity check unless forced
                        if not args.force:
                            if args.debug:
                                print(f"[DEBUG] S3 HEAD check for: {key}")
                            match, why = s3_object_matches_local(s3, bucket, key, fpath,
                                                                tcfg.multipart_threshold,
                                                                args.skip_large_check,
                                                                args.verify_large)
                            if args.debug:
                                print(f"[DEBUG] S3 HEAD result: match={match}, reason={why}")
                            if match:
                                skipped += 1
                                skip_row = [time.time(), str(fpath), key, "skipped", f"exists:{why}", 0, 0.0, ctype or ""]
                                writer.writerow(skip_row)
                                fcsv.flush()  # Force immediate write
                                tracker.note_skip(group_name)
                                if args.debug:
                                    print(f"[DEBUG] CSV logged skip: {skip_row}")
                                    print(f"[DEBUG] Skipping (S3 exists): {fpath.name}")
                                continue

                        # Fall back to prior log indication (if present)
                        if key in already and not args.force:
                            skipped += 1
                            skip_row = [time.time(), str(fpath), key, "skipped", "from prior log", 0, 0.0, ctype or ""]
                            writer.writerow(skip_row)
                            fcsv.flush()  # Force immediate write
                            tracker.note_skip(group_name)
                            if args.debug:
                                print(f"[DEBUG] CSV logged skip from log: {skip_row}")
                                print(f"[DEBUG] Skipping (prior log): {fpath.name}")
                            continue

                        extra = {"ServerSideEncryption": "AES256"}
                        if ctype:
                            extra["ContentType"] = ctype

                        # For large files, add SHA-256 checksum as metadata for future verification
                        # Note: S3's native checksum API has limitations with multipart uploads via boto3
                        if size >= tcfg.multipart_threshold:
                            try:
                                from utils.shared.s3_upload_helpers import sha256_file as compute_sha256
                                local_sha256 = compute_sha256(fpath)
                                # Store SHA-256 in metadata instead of using ChecksumSHA256
                                if "Metadata" not in extra:
                                    extra["Metadata"] = {}
                                extra["Metadata"]["sha256"] = local_sha256
                                print(f"[INFO] Uploading {fpath.name} with SHA-256 in metadata")
                            except Exception as e:
                                print(f"[WARNING] Could not compute SHA-256 for {fpath.name}: {e}")
                                # Continue without checksum

                        if args.debug:
                            print(f"[DEBUG] Starting upload: {fpath.name} ({size} bytes)")
                        elif size >= tcfg.multipart_threshold:
                            print(f"[INFO] Uploading large file: {fpath.name} ({size:,} bytes)")

                        tracker.start_file(group_name, fpath, size)
                        t0 = time.time()
                        status = "uploaded"
                        err = ""

                    # Adaptive retry strategy for large files
                    max_retries = 3 if size >= 1024 * 1024 * 1024 else 1  # 3 retries for 1GB+ files
                    retry_count = 0

                    # Use size-optimized transfer config for this specific file
                    file_transfer_config = get_transfer_config(size)
                    file_transfer = S3Transfer(s3, config=file_transfer_config)

                    while retry_count < max_retries:
                        try:
                            if retry_count > 0:
                                print(f"[RETRY] Attempt {retry_count + 1}/{max_retries} for {fpath.name}")
                                # Exponential backoff: 30s, 60s, 90s
                                time.sleep(30 * retry_count)

                            file_transfer.upload_file(
                                str(fpath),
                                bucket,
                                key,
                                extra_args=extra,
                                callback=tracker.file_progress_cb(group_name),
                            )
                            uploaded += 1
                            total_size += size
                            if args.debug:
                                print(f"[DEBUG] Upload completed: {fpath.name}")
                            elif retry_count > 0:
                                print(f"[SUCCESS] Upload succeeded on retry {retry_count + 1}: {fpath.name}")
                            break  # Success, exit retry loop

                        except Exception as e:
                            retry_count += 1
                            err_str = str(e)

                            # Check if this is a retryable error
                            is_retryable = any(keyword in err_str.lower() for keyword in [
                                "ssl", "timeout", "connection", "eof", "protocol", "broken pipe"
                            ])

                            if is_retryable and retry_count < max_retries:
                                print(f"[WARNING] Retryable error for {fpath.name} (attempt {retry_count}/{max_retries}): {e}")
                                continue
                            else:
                                # Final failure
                                status = "error"
                                err = err_str
                                failed += 1
                                if retry_count >= max_retries:
                                    print(f"[ERROR] Upload failed after {max_retries} attempts for {fpath.name}: {e}")
                                else:
                                    print(f"[ERROR] Upload failed (non-retryable) for {fpath.name}: {e}")
                                break

                    dt = time.time() - t0
                    # Log to CSV with immediate flush
                    result_row = [time.time(), str(fpath), key, status, err, size, round(dt, 3), ctype or ""]
                    writer.writerow(result_row)
                    fcsv.flush()  # Force immediate write to disk
                    tracker.file_done(group_name, status, size)

                    if args.debug:
                        print(f"[DEBUG] CSV logged result: {result_row}")
                    elif status == "error":
                        print(f"[INFO] CSV logged error for: {fpath.name}")
                    elif status == "uploaded":
                        print(f"[INFO] CSV logged upload for: {fpath.name}")

                # Complete the group
                tracker.complete_group(group_name)
                gstats = tracker.data[group_key][group_name]
                print(f"[{folder_type.upper()}] <<< Completed {group_name} | uploaded={gstats['uploaded']} skipped={gstats['skipped']} failed={gstats['failed']} bytes={gstats['bytes_uploaded']}")

                # Ensure CSV is flushed after each group
                fcsv.flush()
                if args.debug:
                    print(f"[DEBUG] CSV flushed after {group_name}")

            elapsed = time.time() - start
            mb = total_size / (1024 * 1024) if elapsed >= 0 else 0.0
            avg = mb / elapsed if elapsed > 0 else 0.0

            print(f"\n[DONE] Uploaded={uploaded} Skipped={skipped} Failed={failed} "
                  f"TotalMB={mb:.2f} AvgMBps={avg:.2f} Log={log_csv}")

    except Exception as e:
        print(f"[ERROR] CSV file handling error: {e}", file=sys.stderr)
        print(f"[ERROR] CSV path: {log_csv}", file=sys.stderr)
        raise

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
