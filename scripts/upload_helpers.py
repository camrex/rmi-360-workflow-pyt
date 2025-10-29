#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Lightweight helpers for uploading RAW Mosaic reels to S3.

- No ArcGIS/arcpy imports
- Reuses ConfigManager + get_boto3_session for creds
- CSV-based resume support (skips already uploaded objects from prior runs)
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Tuple, Any, Optional, Set
import os
import time
import csv
import mimetypes

from boto3.s3.transfer import S3Transfer, TransferConfig

# Allowed extensions for RAW ingest (expand as needed)
RAW_EXTS = {".mp4", ".json", ".csv", ".gpx"}

def _resolve_max_concurrency(cfg) -> int:
    """Interpret aws.max_workers as int or 'cpu*X'."""
    val = cfg.get("aws.max_workers", 16)
    if isinstance(val, int):
        return max(1, val)
    if isinstance(val, str) and val.lower().startswith("cpu*"):
        try:
            import multiprocessing as mp
            ncpu = mp.cpu_count()
            mult = int(val.split("*", 1)[1])
            return max(1, ncpu * mult)
        except Exception:
            return 16
    try:
        return max(1, int(val))
    except Exception:
        return 16

def _content_type_for(path: Path) -> Optional[str]:
    ctype, _ = mimetypes.guess_type(str(path))
    return ctype

def collect_upload_tasks(base_dir: Path, allow_exts: set[str], s3_prefix: str) -> List[Tuple[Path, str]]:
    """
    Walk base_dir and return [(local_path, s3_key), ...] for allowed extensions.
    Preserves relative folder structure under s3_prefix.
    """
    tasks: List[Tuple[Path, str]] = []
    base = base_dir.resolve()
    base_str = str(base)
    s3_prefix = s3_prefix.strip().lstrip("/")
    for root, _, files in os.walk(base_str):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext in allow_exts:
                full = Path(root) / name
                rel = os.path.relpath(str(full), base_str).replace("\\", "/")
                key = f"{s3_prefix}/{rel}" if s3_prefix else rel
                tasks.append((full, key))
    return tasks

def _parse_uploaded_keys_from_log(log_csv: Path, logger) -> Set[str]:
    """
    Return set of s3 keys already marked 'uploaded' in prior runs (resume).
    """
    done: Set[str] = set()
    if not log_csv.exists():
        return done
    try:
        with open(log_csv, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                if row.get("status") == "uploaded":
                    key = row.get("s3_key")
                    if key:
                        done.add(key)
    except Exception as e:
        logger.warning(f"Could not read prior upload log '{log_csv}': {e}")
    if done:
        logger.custom(f"Resuming: {len(done)} objects already uploaded (from log).", emoji="⏩", indent=1)
    return done

def upload_raw_reels(cfg, local_reels_folder: Path, s3_prefix: str, messages: Any = None) -> dict:
    """
    Upload RAW Mosaic reels from a local folder to s3://{aws.s3_bucket_raw}/{s3_prefix}.
    Uses instance role on EC2 (auth_mode=instance) or desktop creds (keyring/config).
    Returns stats dict.
    """
    logger = cfg.get_logger(messages)
    aws = cfg.get("aws", {})
    region = aws.get("region")
    bucket = aws.get("s3_bucket_raw")
    if not bucket:
        raise ValueError("Missing aws.s3_bucket_raw in config.")
    if not region:
        raise ValueError("Missing aws.region in config.")

    # Boto3 session from your shared util (no static keys on EC2)
    from utils.shared.aws_utils import get_boto3_session
    session = get_boto3_session(cfg)
    s3 = session.client("s3", region_name=region)

    # Transfer config (tune chunk size, concurrency)
    max_conc = _resolve_max_concurrency(cfg)
    tcfg = TransferConfig(
        multipart_threshold=64 * 1024 * 1024,
        multipart_chunksize=64 * 1024 * 1024,
        max_concurrency=max_conc,
        use_threads=True,
    )
    transfer = S3Transfer(s3, config=tcfg)

    # Logs directory (no arcpy: build a safe default)
    project_root = Path(cfg.get("__project_root__", cfg.get("__project_base__", "."))).resolve()
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_csv = log_dir / "upload_raw_log.csv"

    # Tasks + resume set
    tasks = collect_upload_tasks(Path(local_reels_folder), RAW_EXTS, s3_prefix)
    logger.info(f"Discovered {len(tasks)} candidate files before resume-skip.", indent=0)
    prior = _parse_uploaded_keys_from_log(log_csv, logger)

    # Prepare CSV writer
    new_file = not log_csv.exists()
    fcsv = open(log_csv, "a", newline="", encoding="utf-8")
    writer = csv.writer(fcsv)
    if new_file:
        writer.writerow(["timestamp", "local_file", "s3_key", "status", "error", "size_bytes", "duration_sec", "content_type"])

    logger.info(f"Uploading RAW reels → s3://{bucket}/{s3_prefix.strip().lstrip('/')} ({len(tasks)} objects)", indent=0)

    start = time.time()
    uploaded = skipped = failed = 0
    total_sz = 0

    for fpath, key in tasks:
        if key in prior:
            skipped += 1
            writer.writerow([time.time(), str(fpath), key, "skipped", "from prior log", 0, 0.0, ""])
            continue

        size = fpath.stat().st_size
        ctype = _content_type_for(fpath)
        extra = {"ContentType": ctype} if ctype else None
        t0 = time.time()
        status = "uploaded"
        err = ""
        try:
            if extra:
                transfer.upload_file(str(fpath), bucket, key, extra_args=extra)
            else:
                transfer.upload_file(str(fpath), bucket, key)
            uploaded += 1
            total_sz += size
        except Exception as e:
            status = "error"
            err = str(e)
            failed += 1
        dt = time.time() - t0
        writer.writerow([time.time(), str(fpath), key, status, err, size, round(dt, 3), ctype or ""])

    fcsv.close()
    elapsed = time.time() - start
    stats = {
        "total": len(tasks),
        "uploaded": uploaded,
        "skipped": skipped,
        "failed": failed,
        "elapsed_sec": round(elapsed, 1),
        "total_mb": round(total_sz / (1024 * 1024), 2),
        "avg_mb_s": round((total_sz / (1024 * 1024)) / elapsed, 2) if elapsed > 0 else 0.0,
        "log_file": str(log_csv),
    }
    logger.custom(
        f"RAW Upload complete: {uploaded} up, {skipped} skipped, {failed} failed, "
        f"{stats['total_mb']} MB in {stats['elapsed_sec']}s (avg {stats['avg_mb_s']} MB/s)",
        emoji="✅", indent=0
    )
    return stats
