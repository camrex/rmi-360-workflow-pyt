# =============================================================================
# ☁️ S3 Backup Utility (utils/shared/backup_to_s3.py)
# -----------------------------------------------------------------------------
# Purpose:             Backup project artifacts to S3 with timestamps for archival and reproducibility
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.2.0
# Author:              RMI Valuation, LLC
# Created:             2025-10-28
# Last Updated:        2025-10-30
#
# Description:
#   Utility for backing up processed project artifacts (config, logs, report, gis_data)
#   to S3 with timestamped organization. Supports backup and archival, version history
#   tracking, and workflow reproducibility by preserving configuration and logs.
#
# File Location:        /utils/shared/backup_to_s3.py
# Called By:            tools/process_360_orchestrator.py, standalone scripts
# Int. Dependencies:    utils/shared/s3_upload_helpers, utils/shared/aws_utils
# Ext. Dependencies:    boto3, pathlib, typing
#
# Features:
#   - Timestamped backup organization
#   - Selective artifact backup (config, logs, reports, GIS data)
#   - Version history tracking for reproducibility
# =============================================================================

from __future__ import annotations
from pathlib import Path
from typing import List, Tuple, Optional, Set, Dict
import os
import time
import csv
import mimetypes
from datetime import datetime

try:
    from boto3.s3.transfer import S3Transfer, TransferConfig
except ImportError:
    S3Transfer = None
    TransferConfig = None


# File extensions for different artifact types
CONFIG_EXTS = {".yaml", ".yml", ".json", ".txt"}
GIS_DATA_EXTS = {".shp", ".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".xml",
                 ".geojson", ".json", ".kml", ".kmz", ".gdb", ".gpkg"}
LOG_EXTS = {".txt", ".log", ".csv", ".args"}
REPORT_EXTS = {".html", ".json", ".png", ".jpg", ".jpeg", ".pdf"}


def _get_file_extensions(artifact_type: str) -> set:
    """Return the appropriate file extensions for the artifact type."""
    ext_map = {
        'config': CONFIG_EXTS,
        'gis_data': GIS_DATA_EXTS,
        'logs': LOG_EXTS,
        'report': REPORT_EXTS
    }
    return ext_map.get(artifact_type, set())


def _collect_files(folder: Path, allow_exts: set) -> List[Path]:
    """Collect all files in folder matching allowed extensions."""
    files: List[Path] = []
    if not folder.exists():
        return files

    for root, dirs, filenames in os.walk(str(folder)):
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext in allow_exts or not allow_exts:
                files.append(Path(root) / name)
    return files


def _content_type_for(path: Path) -> Optional[str]:
    """Guess MIME type for a file."""
    ctype, _ = mimetypes.guess_type(str(path))
    return ctype


def upload_project_artifacts(
    cfg,
    artifact_types: Optional[List[str]] = None,
    timestamp: Optional[str] = None,
    logger=None
) -> Dict[str, dict]:
    """
    Upload project artifacts to S3 with timestamp organization.

    Args:
        cfg: ConfigManager instance
        artifact_types: List of artifact types to upload (config, logs, report, gis_data).
                       If None, uploads all artifact types that exist.
        timestamp: Custom timestamp string (default: auto-generate YYYYMMDD_HHMM)
        logger: Optional logger instance

    Returns:
        Dict mapping artifact_type to upload stats

    Example:
        results = upload_project_artifacts(
            cfg=cfg,
            artifact_types=['config', 'logs', 'report'],
            timestamp='20251030_1430'
        )
    """
    if logger is None:
        logger = cfg.get_logger()

    # Default to all types if not specified
    if artifact_types is None:
        artifact_types = ['config', 'logs', 'report', 'gis_data']

    # Generate timestamp if not provided
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    # Get AWS config
    aws = cfg.get("aws", {})
    region = aws.get("region")
    bucket = aws.get("s3_bucket_raw")
    project_key = cfg.get("project.slug")

    if not bucket:
        logger.warning("aws.s3_bucket_raw not configured; skipping artifact upload")
        return {}
    if not region:
        logger.warning("aws.region not configured; skipping artifact upload")
        return {}
    if not project_key:
        logger.warning("project.slug not configured; skipping artifact upload")
        return {}

    # Get boto3 session
    from utils.shared.aws_utils import get_boto3_session

    session = get_boto3_session(cfg)
    s3 = session.client("s3", region_name=region)

    # Transfer config
    max_workers = cfg.get("aws.max_workers", 16)
    if isinstance(max_workers, str) and max_workers.lower().startswith("cpu*"):
        import multiprocessing as mp
        ncpu = mp.cpu_count()
        mult = int(max_workers.split("*", 1)[1])
        max_workers = max(1, ncpu * mult)
    else:
        max_workers = max(1, int(max_workers))

    tcfg = TransferConfig(
        multipart_threshold=64 * 1024 * 1024,
        multipart_chunksize=64 * 1024 * 1024,
        max_concurrency=max_workers,
        use_threads=True,
    )
    transfer = S3Transfer(s3, config=tcfg)

    paths = cfg.paths
    results = {}

    logger.custom(f"Uploading project artifacts to S3 (timestamp: {timestamp})", emoji="📤", indent=0)

    for artifact_type in artifact_types:
        # Get local folder and file extensions
        if artifact_type == 'config':
            # For config, upload the actual config file used
            config_path = Path(cfg.source_path) if cfg.source_path else None
            if not config_path or not config_path.exists():
                logger.warning(f"Config file not found; skipping {artifact_type} upload", indent=1)
                continue
            files = [config_path]
        elif artifact_type == 'logs':
            folder = paths.logs
            files = _collect_files(folder, _get_file_extensions(artifact_type))
        elif artifact_type == 'report':
            folder = paths.report
            files = _collect_files(folder, _get_file_extensions(artifact_type))
        elif artifact_type == 'gis_data':
            # Check if gis_data folder exists (user might not have any)
            gis_folder = cfg.paths.project_base / "gis_data"
            if not gis_folder.exists():
                logger.info(f"No gis_data folder found; skipping {artifact_type} upload", indent=1)
                continue
            files = _collect_files(gis_folder, _get_file_extensions(artifact_type))
        else:
            logger.warning(f"Unknown artifact type '{artifact_type}'; skipping", indent=1)
            continue

        if not files:
            logger.info(f"No {artifact_type} files to upload", indent=1)
            continue

        # Build S3 prefix with timestamp
        s3_prefix = f"{project_key}/{artifact_type}/{timestamp}"

        logger.info(f"Uploading {len(files)} {artifact_type} file(s) → s3://{bucket}/{s3_prefix}", indent=1)

        uploaded = failed = 0
        total_sz = 0
        start = time.time()

        for fpath in files:
            try:
                # Build S3 key preserving relative structure
                if artifact_type == 'config':
                    # For config, use just the filename
                    rel_path = fpath.name
                else:
                    # For others, preserve folder structure
                    if artifact_type == 'gis_data':
                        base = cfg.paths.project_base / "gis_data"
                    elif artifact_type == 'logs':
                        base = paths.logs
                    else:  # report
                        base = paths.report
                    rel_path = fpath.relative_to(base).as_posix()

                s3_key = f"{s3_prefix}/{rel_path}"
                size = fpath.stat().st_size
                ctype = _content_type_for(fpath)
                extra = {"ContentType": ctype, "ServerSideEncryption": "AES256"} if ctype else {"ServerSideEncryption": "AES256"}

                transfer.upload_file(str(fpath), bucket, s3_key, extra_args=extra)
                uploaded += 1
                total_sz += size

            except Exception as e:
                logger.warning(f"Failed to upload {fpath.name}: {e}", indent=2)
                failed += 1

        elapsed = time.time() - start
        stats = {
            "uploaded": uploaded,
            "failed": failed,
            "total_mb": round(total_sz / (1024 * 1024), 2),
            "elapsed_sec": round(elapsed, 1),
            "s3_prefix": s3_prefix
        }
        results[artifact_type] = stats

        logger.custom(
            f"{artifact_type}: {uploaded} uploaded, {failed} failed, {stats['total_mb']} MB",
            emoji="✅" if failed == 0 else "⚠️",
            indent=2
        )

    return results
