# =============================================================================
# ☁️ AWS S3 Upload Utility (utils/copy_to_aws.py)
# -----------------------------------------------------------------------------
# Purpose:             Uploads JPEG images from a local directory to AWS S3 using TransferManager
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.3.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-14
# Last Updated:        2025-10-30
#
# Description:
#   Recursively uploads renamed images from a local directory to a configured
#   S3 bucket path using boto3's TransferManager. Supports concurrency scaling, retry logic,
#   resumable logging, ETA progress tracking, and graceful cancellation via file or ArcGIS trigger.
#
# File Location:        /utils/copy_to_aws.py
# Validator:            /utils/validators/copy_to_aws_validator.py
# Called By:            tools/copy_to_aws_tool.py, orchestrator pipeline
# Int. Dependencies:    utils/manager/config_manager, utils/shared/aws_utils
# Ext. Dependencies:    boto3, botocore, threading, multiprocessing, csv, time, os, pathlib, datetime, typing
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/copy_to_aws.md
#   (Ensure these docs are current; update if needed.)
#
# Notes:
#   - Uses TransferManager with configurable concurrency and retry limits
#   - Respects cancel_copy.txt trigger for manual interruption support
# =============================================================================

__all__ = ["copy_to_aws"]

import os
import time
import csv
import threading
import multiprocessing
from datetime import datetime, timezone
from typing import Optional, Any
from boto3.s3.transfer import create_transfer_manager, TransferConfig
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError
from pathlib import Path

from utils.manager.config_manager import ConfigManager
from utils.shared.aws_utils import get_boto3_session
from utils.shared.oid_storage_paths import (
    is_secured_storage_enabled,
    build_oid_object_key,
    resolve_oid_key_prefix,
    resolve_oid_target_bucket,
)


def collect_upload_tasks(local_dir, include_extensions, cfg: ConfigManager, secured_mode: bool = False):
    """
    Recursively collects all files with given extensions and returns (local_path, s3_key) tuples.
    """
    tasks = []
    for file_path in local_dir.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in include_extensions:
            continue
        # Use a single OID key builder so upload keys and ImagePath targets stay aligned.
        s3_key = build_oid_object_key(cfg, file_path.name, secured_mode=secured_mode)
        tasks.append((str(file_path), s3_key))
    return tasks


def collect_upload_tasks_from_manifest(manifest_path, include_extensions, cfg: ConfigManager, secured_mode: bool = False):
    """Collect upload tasks from a manifest CSV with local_path or filename columns."""
    manifest_path = Path(manifest_path)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Delivery subset manifest not found: {manifest_path}")

    tasks = []
    seen = set()
    with open(manifest_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            local_path = row.get("local_path") or row.get("image_path")
            filename = row.get("filename")

            if local_path:
                local_file = Path(local_path)
            elif filename:
                local_file = Path(cfg.paths.renamed) / filename
            else:
                continue

            if not local_file.is_file():
                continue
            if local_file.suffix.lower() not in include_extensions:
                continue

            s3_key = build_oid_object_key(cfg, local_file.name, secured_mode=secured_mode)
            dedupe_key = (str(local_file), s3_key)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            tasks.append((str(local_file), s3_key))

    return tasks

def parse_uploaded_keys_from_log(log_file, logger):
    uploaded_keys = set()
    if os.path.exists(log_file):
        try:
            with open(log_file, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("status") == "uploaded":
                        uploaded_keys.add(row.get("s3_key"))
            logger.custom(f"Resuming from previous log, skipping {len(uploaded_keys)} previously uploaded files.", emoji="ℹ🔄", indent=1)
        except Exception as e:
            logger.warning(f"Could not read previous log for resume: {e}", indent=1)
    return uploaded_keys

def calculate_summary(log_rows, total, start_time):
    uploaded = sum(1 for row in log_rows if row[3] == "uploaded")
    skipped = sum(1 for row in log_rows if row[3] == "skipped")
    failed = sum(1 for row in log_rows if row[3] == "error")
    skipped_from_log = sum(1 for row in log_rows if row[3] == "skipped" and row[4] == "from prior log")
    elapsed_time = round(time.time() - start_time, 2)
    total_size_bytes = sum(row[5] for row in log_rows if isinstance(row[5], int))
    avg_time_per_image = round(elapsed_time / total, 3) if total else 0
    avg_speed = round((total_size_bytes / 1024 / 1024) / elapsed_time, 2) if elapsed_time else 0
    total_size_mb = round(total_size_bytes / (1024 * 1024), 2)
    return {
        "uploaded": uploaded,
        "skipped": skipped,
        "skipped_from_log": skipped_from_log,
        "failed": failed,
        "elapsed_time": elapsed_time,
        "total_size_bytes": total_size_bytes,
        "avg_time_per_image": avg_time_per_image,
        "avg_speed": avg_speed,
        "total_size_mb": total_size_mb
    }

def write_summary_file(summary_file, stats):
    with open(summary_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Total Files", stats['uploaded'] + stats['skipped'] + stats['failed']])
        writer.writerow(["Uploaded", stats['uploaded']])
        writer.writerow(["Skipped", stats['skipped']])
        writer.writerow(["Skipped (from prior log)", stats['skipped_from_log']])
        writer.writerow(["Failed", stats['failed']])
        writer.writerow(["Elapsed Time (sec)", stats['elapsed_time']])
        writer.writerow(["Average Time/Image (sec)", stats['avg_time_per_image']])
        writer.writerow(["Total Size (MB)", stats['total_size_mb']])
        writer.writerow(["Average Speed (MB/sec)", stats['avg_speed']])

def should_cancel(messages, allow_cancel_file_trigger, cancel_txt):
    if hasattr(messages, "isCanceled") and messages.isCanceled():
        return True
    elif allow_cancel_file_trigger and Path(cancel_txt).exists():
        return True
    return False


def verify_s3_target_access(s3_client, bucket: str, bucket_folder: str, logger) -> None:
    """Verify that the target bucket is reachable before queueing uploads."""
    try:
        logger.info(f"Verifying S3 bucket access: s3://{bucket}/{bucket_folder}", indent=1)
        s3_client.head_bucket(Bucket=bucket)
        logger.custom("S3 bucket access verified.", indent=2, emoji="🪣")
    except (ClientError, NoCredentialsError, Exception) as exc:
        logger.error(f"Unable to access target S3 bucket '{bucket}': {exc}", indent=2)
        raise


def resolve_s3_client(session, bucket: str, use_accel: bool, logger):
    """Create an S3 client, falling back when Transfer Acceleration is not enabled on the bucket."""
    base_client = session.client("s3")

    if not use_accel:
        logger.info("S3 Transfer Acceleration endpoint disabled", indent=2)
        return base_client, False

    try:
        accel_status = base_client.get_bucket_accelerate_configuration(Bucket=bucket).get("Status")
    except (ClientError, NoCredentialsError, Exception) as exc:
        logger.warning(f"Could not verify S3 Transfer Acceleration for bucket '{bucket}': {exc}. Falling back to standard endpoint.", indent=2)
        return base_client, False

    if accel_status == "Enabled":
        logger.custom("Using S3 Transfer Acceleration endpoint", indent=2, emoji="🚀")
        s3_cfg = Config(s3={"use_accelerate_endpoint": True})
        return session.client("s3", config=s3_cfg), True

    logger.warning(f"S3 Transfer Acceleration is not enabled for bucket '{bucket}'. Falling back to standard endpoint.", indent=2)
    return base_client, False

def copy_to_aws(
        cfg: ConfigManager,
        report_data: Optional[dict] = None,
        local_dir: Optional[str] = None,
    manifest_path: Optional[str] = None,
        skip_existing: Optional[bool] = None,
        messages: Optional[Any] = None
):
    """
    Uploads files from a local directory to an AWS S3 bucket folder with concurrency, resumable progress, and detailed
    logging.

    Recursively scans the specified local directory, optionally filtering files by extension, and uploads them to the
    given S3 bucket and folder using boto3's TransferManager. Supports skipping files already uploaded (based on a CSV
    log), resuming interrupted uploads, and concurrent transfers with configurable concurrency. Progress and per-file
    status are logged to CSV files, and a summary report is generated upon completion. Uploads can be canceled via
    ArcGIS Pro events or a trigger file. Updates the provided config dictionary with upload status.

    Args:
        cfg:
        report_data:
        local_dir: Path to the local directory containing files to upload.
        skip_existing: If True, skips files already uploaded as recorded in the log.
        messages:
    """
    logger = cfg.get_logger()
    cfg.validate(tool="copy_to_aws")

    logger.custom("Upload process cannot be interrupted once started. Use resume mode to safely restart if "
                "needed.", indent=1, emoji="⚠️")

    # AWS Setup
    secured_mode = is_secured_storage_enabled(cfg)
    bucket = resolve_oid_target_bucket(cfg, secured_mode=secured_mode)
    bucket_folder = resolve_oid_key_prefix(cfg, secured_mode=secured_mode)
    batch_size = cfg.get("aws.upload_batch_size", 25)
    max_workers_raw = cfg.get("aws.max_workers", 8)
    retries = cfg.get("aws.retries", 3)
    use_accel = cfg.get("aws.use_acceleration", False)

    include_extensions = [".jpg", ".jpeg"]
    if local_dir is None:
        local_dir_str = str(cfg.paths.renamed)
    else:
        local_dir_str = local_dir
    local_dir_path = Path(local_dir_str)

    if skip_existing is None:
        skip_existing = cfg.get("aws.skip_existing", True)

    allow_cancel_file_trigger = cfg.get("aws.allow_cancel_file_trigger", True)
    cancel_txt = Path(cfg.paths.project_base / "cancel_copy.txt")

    log_file = cfg.paths.get_log_file_path("aws_upload_log", cfg)
    summary_file = cfg.paths.get_log_file_path("aws_upload_summary", cfg)

    logger.info("Preparing AWS Upload...", indent=1)
    logger.info(f"Delivery mode: {'secured virtual cache' if secured_mode else 'legacy public URL'}", indent=2)

    # Concurrency resolution
    cpu_count = multiprocessing.cpu_count() or 4
    worker_limit = cpu_count * 8  # Safety Limit
    if isinstance(max_workers_raw, int):
        max_concurrency = max_workers_raw
        logger.custom(f"Using Max Workers = {max_concurrency} (from int config)", indent=2, emoji="🧵")
    elif isinstance(max_workers_raw, str) and max_workers_raw.startswith("cpu"):
        try:
            factor = int(max_workers_raw.split("*")[1]) if "*" in max_workers_raw else 1
            max_concurrency = min(cpu_count * factor, worker_limit)
            logger.custom(f"Using Max Workers = {max_concurrency} (cpu_count={cpu_count} × factor={factor})", indent=2, emoji="🧵")
        except Exception as e:
            max_concurrency = cpu_count
            logger.warning(f"Failed to parse max_workers='{max_workers_raw}': {e}. Defaulting to {cpu_count}.", indent=2)
    else:
        max_concurrency = cpu_count
        logger.warning(f"Invalid max_workers value: {max_workers_raw}. Using default {cpu_count}.", indent=2)

    # COLLECT ALL TASKS
    if manifest_path:
        logger.info(f"Using delivery subset manifest: {manifest_path}", indent=2)
        all_tasks = collect_upload_tasks_from_manifest(manifest_path, include_extensions, cfg, secured_mode=secured_mode)
    else:
        all_tasks = collect_upload_tasks(local_dir_path, include_extensions, cfg, secured_mode=secured_mode)
    if not all_tasks:
        logger.warning("No matching files found to upload.", indent=2)
        return {}

    # Load credentials from keyring or config and verify AWS credentials
    try:
        logger.info("Retrieving AWS credentials...", indent=1)
        session = get_boto3_session(cfg)
    except Exception as e:
        # Error already logged upstream; return a consistent error payload.
        return {
            "uploaded": 0,
            "skipped": 0,
            "skipped_from_log": 0,
            "failed": 0,
            "cancelled": False,
            "log_file": str(log_file),
            "summary_file": str(summary_file),
            "status": "error",
            "message": str(e),
        }

    s3, using_acceleration = resolve_s3_client(session, bucket, use_accel, logger)

    try:
        verify_s3_target_access(s3, bucket, bucket_folder, logger)
    except Exception:
        return {
            "uploaded": 0,
            "skipped": 0,
            "skipped_from_log": 0,
            "failed": 0,
            "cancelled": False,
            "log_file": str(log_file),
            "summary_file": str(summary_file),
            "status": "error"
        }

    if using_acceleration:
        logger.custom("Uploads will use the accelerated endpoint.", indent=2, emoji="🚀")

    logger.info("Starting AWS Upload...", indent=1)
    # Create TransferManager with custom configuration
    transfer_config = TransferConfig(
        multipart_threshold=16 * 1024 * 1024,
        multipart_chunksize=8 * 1024 * 1024,
        max_concurrency=max_concurrency,
        num_download_attempts=retries,
        use_threads=True
    )
    manager = create_transfer_manager(client=s3, config=transfer_config)

    log_rows = []

    # GET UPLOADED TASKS FROM LOG (FOR RESUME)
    uploaded_keys = parse_uploaded_keys_from_log(log_file, logger)

    # CHECK REMAINING TASK ON RESUME
    upload_tasks = []
    for file_path, s3_key in all_tasks:
        if skip_existing and s3_key in uploaded_keys:
            timestamp = datetime.now(timezone.utc).isoformat()
            size = os.path.getsize(file_path)
            log_rows.append((timestamp, file_path, s3_key, "skipped", "from prior log", size, 0.0))
        else:
            upload_tasks.append((file_path, s3_key))

    total = len(upload_tasks)
    if total == 0:
        logger.custom("No files to upload (all skipped or already uploaded).", indent=1, emoji="❗")
        return {
            "uploaded": 0,
            "skipped": 0,
            "skipped_from_log": len(uploaded_keys),
            "failed": 0,
            "cancelled": False,
            "log_file": str(log_file),
            "summary_file": str(summary_file),
            "status": "completed"
        }

    start_time = time.time()
    completed = {"processed": 0, "uploaded": 0, "failed": 0}
    lock = threading.Lock()
    cancel_event = threading.Event()

    # Write log header
    with open(log_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "local_file", "s3_key", "status", "error", "size_bytes", "duration_sec"])

    def upload_one(f_path, s3_tgt_key):
        """
        Uploads a single file to the specified S3 key and logs the result.

        Attempts to upload the file using the transfer manager, recording the status, error (if any), file size, and
        duration. Appends the upload result to the log and updates the completed count in a thread-safe manner.
        """
        upload_start = None
        try:
            future = manager.upload(f_path, bucket, s3_tgt_key, extra_args={"ContentType": "image/jpeg"})
            upload_start = time.perf_counter()
            future.result()
            upload_end = time.perf_counter()
            status, error = "uploaded", ""
        except Exception as exc:
            upload_end = time.perf_counter()
            if upload_start is None:
                upload_start = upload_end  # duration = 0
            status, error = "error", str(exc)
        duration = round(upload_end - upload_start, 2)
        file_size = os.path.getsize(f_path) if os.path.exists(f_path) else 0
        timestamp_str = datetime.now(timezone.utc).isoformat()

        with lock:
            completed["processed"] += 1
            if status == "uploaded":
                completed["uploaded"] += 1
            elif status == "error":
                completed["failed"] += 1
            log_rows.append((timestamp_str, f_path, s3_tgt_key, status, error, file_size, duration))
            with open(log_file, "a", newline="", encoding="utf-8") as csv_file:
                csv_writer = csv.writer(csv_file)
                csv_writer.writerow([timestamp_str, f_path, s3_tgt_key, status, error, file_size, duration])

    with cfg.get_progressor(total=total, label="Uploading images to S3") as progressor:
        last = 0

        try:
            for i in range(0, len(upload_tasks), batch_size):
                batch = upload_tasks[i:i + batch_size]
                threads = []

                for local_path, s3_key in batch:
                    if cancel_event.is_set():
                        break
                    t = threading.Thread(target=upload_one, args=(local_path, s3_key))
                    threads.append(t)
                    t.start()

                for t in threads:
                    t.join()

                # Check for cancel triggers
                if should_cancel(messages, allow_cancel_file_trigger, cancel_txt):
                    cancel_event.set()
                    logger.custom("Upload canceled by trigger.", emoji="🛑", indent=2)

                if cancel_event.is_set():
                    progressor.update(completed["processed"], "🛑 Upload canceled — finishing current batch.")
                    if report_data is not None:
                        upload_status = "canceled" if cancel_event.is_set() else "completed"
                        current_status = report_data.setdefault("upload", {}).get("status")

                        # If previously canceled, and now completed, mark as completed_after_cancel
                        if upload_status == "completed" and current_status == "canceled":
                            upload_status = "completed_after_cancel"

                        report_data["upload"]["status"] = upload_status

                    break

                with lock:
                    current = completed["processed"]
                    uploaded = completed["uploaded"]
                    failed = completed["failed"]

                if current > last:
                    elapsed = time.time() - start_time
                    eta = (elapsed / current) * (total - current) if current > 0 else 0
                    eta_min, eta_sec = divmod(int(eta), 60)
                    eta_hr, eta_min = divmod(eta_min, 60)
                    label = (
                        f"Processing {current}/{total} images... "
                        f"Uploaded: {uploaded}, Failed: {failed}, ETA: {eta_hr}:{eta_min:02d}:{eta_sec:02d}"
                    )
                    progressor.update(current, label)
                    logger.custom(label, indent=3, emoji="☁️")
                    last = current
        finally:
            manager.shutdown()

    # Write Summary File (aws_upload_summary)
    summary_stats = calculate_summary(log_rows, total, start_time)
    write_summary_file(summary_file, summary_stats)

    logger.success(f"Upload complete: {summary_stats['uploaded']} uploaded, {summary_stats['skipped']} skipped, {summary_stats['failed']} failed.", indent=1)
    if summary_stats['failed'] and not summary_stats['uploaded']:
        logger.warning("No files were uploaded successfully. Check AWS credentials, bucket name, region, and IAM permissions.", indent=1)
    logger.custom(f"Log written to: {log_file}", indent=1, emoji="📄")
    logger.custom(f"Upload summary written to: {summary_file}", indent=1, emoji="📊")

    # Update report_data if passed
    if report_data is not None:
        report_data.setdefault("upload", {}).update({
            "status": "cancelled" if cancel_event.is_set() else "completed",
            "count": summary_stats['uploaded'],
            "expected_total": total,
            "end_time": datetime.now(timezone.utc).isoformat(),
            "percent_complete": summary_stats['uploaded'] / total * 100 if total else 0
        })

    return {
        "uploaded": summary_stats['uploaded'],
        "skipped": summary_stats['skipped'],
        "skipped_from_log": summary_stats['skipped_from_log'],
        "failed": summary_stats['failed'],
        "cancelled": cancel_event.is_set(),
        "log_file": str(log_file),
        "summary_file": str(summary_file),
        "status": "cancelled" if cancel_event.is_set() else "completed"
    }