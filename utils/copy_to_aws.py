# =============================================================================
# ☁️ AWS S3 Upload Utility (utils/copy_to_aws.py)
# -----------------------------------------------------------------------------
# Purpose:             Uploads JPEG images from a local directory to AWS S3 using TransferManager
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Recursively uploads enhanced or renamed images from a local directory to a configured
#   S3 bucket path using boto3's TransferManager. Supports concurrency scaling, retry logic,
#   resumable logging, ETA progress tracking, and graceful cancellation via file or ArcGIS trigger.
#
# File Location:        /utils/copy_to_aws.py
# Called By:            tools/copy_to_aws_tool.py, orchestrator pipeline
# Int. Dependencies:    config_loader, arcpy_utils, aws_utils, path_utils, expression_utils, progressor_utils
# Ext. Dependencies:    boto3, botocore, threading, multiprocessing, csv, time, os, pathlib
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/copy_to_aws.md
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
from typing import Optional, List
from boto3.session import Session
from boto3.s3.transfer import create_transfer_manager, TransferConfig
from botocore.config import Config
from pathlib import Path

from utils.config_loader import resolve_config
from utils.arcpy_utils import log_message
from utils.path_utils import get_log_path
from utils.expression_utils import resolve_expression
from utils.progressor_utils import Progressor
from utils.aws_utils import get_aws_credentials


def upload_directory_with_transfer_manager(
    local_dir: str,
    bucket: str,
    s3_bucket_folder: str,
    include_extensions: Optional[List[str]] = None,
    skip_existing: bool = True,
    max_concurrency: int = 8,
    retries: int = 3,
    config: Optional[dict] = None,
    messages: Optional[List[str]] = None,
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
        local_dir: Path to the local directory containing files to upload.
        bucket: Name of the AWS S3 bucket.
        s3_bucket_folder: Destination folder path within the S3 bucket.
        include_extensions: List of file extensions to include (e.g., [".jpg", ".jpeg"]). If None, all files are
        included.
        skip_existing: If True, skips files already uploaded as recorded in the log.
        max_concurrency: Maximum number of concurrent upload threads, or a string like "cpu*2" for auto-scaling.
        retries: Number of retry attempts for failed uploads.
        config: Optional configuration dictionary with AWS credentials and upload options.
        messages: Optional message collector or logger for status updates.
    """
    log_message("⚠️ Upload process cannot be interrupted once started. Use resume mode to safely restart if "
                "needed.", messages, config=config)

    access_key, secret_key = get_aws_credentials(config)
    region = config.get("aws", {}).get("region", "us-east-2")

    # Auto-scale concurrency from config like 'cpu*2'
    if isinstance(max_concurrency, str) and "cpu" in max_concurrency.lower():
        parts = max_concurrency.lower().split("*")
        cpu_count = multiprocessing.cpu_count()
        multiplier = float(parts[1]) if len(parts) > 1 else 1
        max_concurrency = max(1, int(cpu_count * multiplier))
        log_message(f"🔧 Auto-scaled max concurrency: {max_concurrency} threads (CPU × {multiplier})", messages,
                    config=config)

    session = Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region
    )
    use_accel = config.get("aws", {}).get("use_acceleration", False)
    s3_cfg = Config(s3={"use_accelerate_endpoint": True}) if use_accel else None
    s3 = session.client("s3", config=s3_cfg) if s3_cfg else session.client("s3")

    if use_accel:
        log_message("🚀 Using S3 Transfer Acceleration endpoint", messages, config=config)

    transfer_config = TransferConfig(
        multipart_threshold=16 * 1024 * 1024,
        multipart_chunksize=8 * 1024 * 1024,
        max_concurrency=max_concurrency,
        num_download_attempts=retries,
        use_threads=True
    )
    manager = create_transfer_manager(client=s3, config=transfer_config)

    log_entries = []
    if messages is None:
        messages = []

    log_file = get_log_path("aws_upload_log", config)

    all_tasks = []
    for root, _, files in os.walk(local_dir):
        for file in files:
            if include_extensions and not file.lower().endswith(tuple(include_extensions)):
                continue
            local_path = os.path.join(root, file)
            relative_key = os.path.relpath(local_path, local_dir).replace("\\", "/")
            s3_key = os.path.join(s3_bucket_folder, relative_key).replace("\\", "/")
            all_tasks.append((local_path, s3_key))

    uploaded_keys = set()
    if os.path.exists(log_file):
        try:
            with open(log_file, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("status") == "uploaded":
                        uploaded_keys.add(row.get("s3_key"))
            log_message(f"ℹ️ Resuming from previous log, skipping {len(uploaded_keys)} previously uploaded files.",
                        messages, config=config)
        except Exception as e:
            log_message(f"[WARNING] Could not read previous log for resume: {e}", messages, level="warning",
                        config=config)

    upload_tasks = []
    for local_path, s3_key in all_tasks:
        if skip_existing and s3_key in uploaded_keys:
            timestamp = datetime.now(timezone.utc).isoformat()
            size = os.path.getsize(local_path)
            log_entries.append((timestamp, local_path, s3_key, "skipped", "from prior log", size, 0.0))
        else:
            upload_tasks.append((local_path, s3_key))

    total = len(upload_tasks)
    if total == 0:
        log_message("✅ No files to upload (all skipped or already uploaded).", messages, config=config)
        return

    start_time = time.time()
    completed = {"count": 0}
    lock = threading.Lock()
    cancel_event = threading.Event()

    # Configurable cancel behavior
    upload_batch_size = config.get("aws", {}).get("upload_batch_size", 25)
    allow_cancel_file_trigger = config.get("aws", {}).get("allow_cancel_file_trigger", True)

    # Write log header
    with open(log_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "local_file", "s3_key", "status", "error", "size_bytes", "duration_sec"])

    def upload_one(file_path, s3_tgt_key):
        """
        Uploads a single file to the specified S3 key and logs the result.
        
        Attempts to upload the file using the transfer manager, recording the status, error (if any), file size, and
        duration. Appends the upload result to the log and updates the completed count in a thread-safe manner.
        """
        upload_start = None
        try:
            future = manager.upload(file_path, bucket, s3_tgt_key, extra_args={"ContentType": "image/jpeg"})
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
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        timestamp_str = datetime.now(timezone.utc).isoformat()

        with lock:
            completed["count"] += 1
            log_entries.append((timestamp_str, file_path, s3_tgt_key, status, error, file_size, duration))
            with open(log_file, "a", newline="", encoding="utf-8") as csv_file:
                csv_writer = csv.writer(csv_file)
                csv_writer.writerow([timestamp_str, file_path, s3_tgt_key, status, error, file_size, duration])

    with Progressor(total=total, label="Uploading images to AWS...", messages=messages) as progress:
        last = 0

        for i in range(0, len(upload_tasks), upload_batch_size):
            batch = upload_tasks[i:i + upload_batch_size]
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
            if hasattr(messages, "isCanceled") and messages.isCanceled():
                cancel_event.set()
                log_message("🛑 ArcGIS Pro cancel detected.", messages, config=config)
            elif allow_cancel_file_trigger and Path("cancel_copy.txt").exists():
                cancel_event.set()
                log_message("🛑 cancel_copy.txt file detected. Canceling upload.", messages, config=config)

            if cancel_event.is_set():
                progress.update(completed["count"], "🛑 Upload canceled — finishing current batch.")
                if config is not None:
                    upload_status = "canceled" if cancel_event.is_set() else "completed"
                    current_status = config.setdefault("report_data", {}).setdefault("upload", {}).get("status")

                    # If previously canceled, and now completed, mark as completed_after_cancel
                    if upload_status == "completed" and current_status == "canceled":
                        upload_status = "completed_after_cancel"

                    config["report_data"]["upload"]["status"] = upload_status

                break

            with lock:
                current = completed["count"]

            if current > last:
                elapsed = time.time() - start_time
                eta = (elapsed / current) * (total - current) if current > 0 else 0
                eta_min, eta_sec = divmod(int(eta), 60)
                eta_hr, eta_min = divmod(eta_min, 60)
                label = f"Uploading {current}/{total} images... ETA: {eta_hr}:{eta_min:02d}:{eta_sec:02d}"
                progress.update(current, label)
                last = current

    uploaded = sum(1 for row in log_entries if row[3] == "uploaded")
    skipped = sum(1 for row in log_entries if row[3] == "skipped")
    failed = sum(1 for row in log_entries if row[3] == "error")
    skipped_from_log = sum(1 for row in log_entries if row[3] == "skipped" and row[4] == "from prior log")

    summary_file = log_file.replace(".csv", "_summary.csv")
    elapsed_time = round(time.time() - start_time, 2)
    total_size_bytes = sum(row[5] for row in log_entries if isinstance(row[5], int))
    avg_time_per_image = round(elapsed_time / total, 3) if total else 0
    avg_speed = round((total_size_bytes / 1024 / 1024) / elapsed_time, 2) if elapsed_time else 0
    total_size_mb = round(total_size_bytes / (1024 * 1024), 2)

    with open(summary_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Total Files", len(log_entries)])
        writer.writerow(["Uploaded", uploaded])
        writer.writerow(["Skipped", skipped])
        writer.writerow(["Skipped (from prior log)", skipped_from_log])
        writer.writerow(["Failed", failed])
        writer.writerow(["Elapsed Time (sec)", elapsed_time])
        writer.writerow(["Average Time/Image (sec)", avg_time_per_image])
        writer.writerow(["Total Size (MB)", total_size_mb])
        writer.writerow(["Average Speed (MB/sec)", avg_speed])

    log_message(f"✅ Upload complete: {uploaded} uploaded, {skipped} skipped, {failed} failed.", messages, config=config)
    log_message(f"📄 Log written to: {log_file}", messages, config=config)
    log_message(f"📊 Upload summary written to: {summary_file}", messages, config=config)

    # ✅ Set upload status as completed if it wasn't canceled
    if not cancel_event.is_set() and config is not None:
        config.setdefault("report_data", {}).setdefault("upload", {})["status"] = "completed"


def copy_to_aws(
    local_dir: Optional[str] = None,
    skip_existing: Optional[bool] = None,
    config: Optional[dict] = None,
    config_file: Optional[str] = None,
    project_folder: Optional[str] = None,
    messages: Optional[list] = None
):
    """
    Initiates the upload of a local directory of JPEG images to an AWS S3 bucket using concurrent transfers.
    
    Resolves configuration from parameters, config files, or project folders to determine the local directory, AWS
    bucket, and destination folder. Validates required AWS configuration and starts the upload process with progress
    tracking, resumable uploads, and optional skipping of previously uploaded files.
    """
    log_message("🚀 Using NEW threaded copy_to_aws with safe progressor integration.", messages, config=config)

    config = resolve_config(
        config=config,
        config_file=config_file,
        project_folder=project_folder,
        messages=messages,
        tool_name="copy_to_aws"
    )

    if not local_dir:
        folders = config.get("image_output", {}).get("folders", {})
        parent = folders.get("parent", "panos")
        renamed = folders.get("renamed", "final")
        local_dir = os.path.join(config.get("__project_root__", ""), parent, renamed)

    aws_cfg = config.get("aws", {})
    bucket = aws_cfg.get("s3_bucket")
    bucket_folder_expr = aws_cfg.get("s3_bucket_folder")

    if not all([local_dir, bucket, bucket_folder_expr]):
        log_message("Missing one or more required AWS keys in config.yaml.", messages, level="error", config=config)
        return

    s3_bucket_folder = resolve_expression(bucket_folder_expr, config)

    upload_directory_with_transfer_manager(
        local_dir=local_dir,
        bucket=bucket,
        s3_bucket_folder=s3_bucket_folder,
        include_extensions=[".jpg", ".jpeg"],
        skip_existing=skip_existing if skip_existing is not None else aws_cfg.get("skip_existing", True),
        max_concurrency=aws_cfg.get("max_workers", 8),
        retries=aws_cfg.get("retries", 3),
        config=config,
        messages=messages,
    )
