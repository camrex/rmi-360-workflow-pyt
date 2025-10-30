#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
s3_upload_helpers.py
====================

Common helper functions for S3 upload scripts.

Provides:
- Configuration loading and resolution
- AWS session management
- File integrity checking (MD5, SHA-256)
- S3 object existence verification
- Prefix normalization
- CSV log parsing
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Set, Tuple, Optional

try:
    import yaml
except ImportError:
    raise ImportError("PyYAML is required. Install with: pip install pyyaml")

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    raise ImportError("boto3 is required. Install with: pip install boto3")


def load_cfg(cfg_path: Path) -> dict:
    """Load and validate YAML configuration file."""
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config yaml must parse to a mapping")
    if "aws" not in data or not isinstance(data["aws"], dict):
        raise ValueError("config must include an 'aws' mapping")
    return data


def resolve_project_base(project_base_arg: Optional[str], cfg: dict, cfg_path: Path) -> Path:
    """
    Resolve project base directory for logs.

    Priority:
    1. --project-base argument
    2. project_base in config yaml
    3. Config file directory
    """
    if project_base_arg:
        return Path(project_base_arg).resolve()

    pb = cfg.get("project_base")
    if pb:
        return Path(pb).resolve()

    return cfg_path.parent


def resolve_session(auth_mode: Optional[str], service_name: str = "rmi_s3"):
    """
    Create boto3 session based on auth mode.

    Modes:
    - config (default): Use standard AWS credential chain
    - instance: Use EC2/ECS instance role
    - keyring: Use system keyring for credentials
    """
    mode = (auth_mode or "config").lower()

    if mode == "keyring":
        try:
            import keyring
        except ImportError:
            raise RuntimeError("auth_mode=keyring but 'keyring' is not installed. pip install keyring")

        ak = keyring.get_password(service_name, "AWS_ACCESS_KEY_ID")
        sk = keyring.get_password(service_name, "AWS_SECRET_ACCESS_KEY")

        if not ak or not sk:
            raise RuntimeError(
                f"Missing AWS credentials in keyring '{service_name}'. "
                "Run keyring.set_password('rmi_s3','AWS_ACCESS_KEY_ID',...) and SECRET_ACCESS_KEY."
            )
        return boto3.Session(aws_access_key_id=ak, aws_secret_access_key=sk)

    elif mode == "instance":
        return boto3.Session()

    # Default: use standard AWS credential chain
    return boto3.Session()


def resolve_max_concurrency(val) -> int:
    """
    Resolve max concurrency from config value.

    Supports:
    - Integer: direct value
    - "cpu*N": N times CPU count
    """
    if isinstance(val, int):
        return max(1, val)

    if isinstance(val, str) and val.lower().startswith("cpu*"):
        try:
            import multiprocessing as mp
            ncpu = mp.cpu_count()
            mult = int(val.split("*", 1)[1])
            return max(1, ncpu * mult)
        except (ValueError, IndexError):
            return 16

    try:
        return max(1, int(val))
    except (ValueError, TypeError):
        return 16


def normalize_s3_prefix(prefix: str) -> str:
    """
    Normalize S3 prefix to consistent format.

    Removes leading slash, ensures trailing slash.
    Example: "RMI25320/reels" -> "RMI25320/reels/"
    """
    if not prefix:
        return ""

    clean = prefix.strip().lstrip("/")

    if clean and not clean.endswith("/"):
        clean += "/"

    return clean


def md5_file(path: Path, blocksize: int = 8 * 1024 * 1024) -> str:
    """Fast streaming MD5 for small files (used when object is < multipart_threshold)."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(blocksize), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_file(path: Path, blocksize: int = 8 * 1024 * 1024) -> str:
    """Streaming SHA-256 for large files (more reliable than size-only)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(blocksize), b""):
            h.update(chunk)
    return h.hexdigest()


def s3_object_matches_local(
    s3,
    bucket: str,
    key: str,
    fpath: Path,
    multipart_threshold_bytes: int,
    skip_large_check: bool = False,
    verify_large: bool = False
) -> Tuple[bool, str]:
    """
    Check if S3 already has an identical object.

    Returns:
        (match, reason) tuple
        - match: True if file should be skipped (already uploaded)
        - reason: Description of why match succeeded/failed

    Verification strategy:
    - Small files (<threshold): MD5 comparison with ETag
    - Large files (≥threshold): SHA-256 (if available) > timestamp heuristics > size-only
    """
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("404", "NoSuchKey", "NotFound"):
            return (False, "not_found")
        return (False, f"head_error:{code or 'unknown'}")
    except Exception as e:
        return (False, f"head_exception:{type(e).__name__}")

    remote_size = head.get("ContentLength")
    local_size = fpath.stat().st_size

    if remote_size != local_size:
        return (False, "size_diff")

    etag = (head.get("ETag") or "").strip('"')

    # Small files: MD5 comparison
    if local_size < multipart_threshold_bytes and etag:
        try:
            local_md5 = md5_file(fpath)
            if local_md5 == etag:
                return (True, "etag_md5_match")
            else:
                return (False, "md5_diff")
        except (OSError, IOError):
            return (True, "size_match_small_no_md5")

    # Large files: skip if requested
    if skip_large_check:
        print(f"[INFO] Skipping size-only check for large file, will re-upload: {fpath.name}")
        return (False, "skip_large_check")

    # Large files: SHA-256 verification
    checksum_sha256 = head.get("ChecksumSHA256")
    if not checksum_sha256:
        metadata = head.get("Metadata", {})
        checksum_sha256 = metadata.get("sha256")

    if checksum_sha256:
        try:
            local_sha256 = sha256_file(fpath)
            if local_sha256 == checksum_sha256:
                return (True, "sha256_match")
            else:
                print(f"[INFO] SHA-256 mismatch for {fpath.name}, will re-upload")
                return (False, "sha256_diff")
        except (OSError, IOError) as e:
            print(f"[WARNING] Could not compute SHA-256 for {fpath.name}: {e}")

    # Verify-large mode: compute SHA-256 even if S3 doesn't have it
    elif verify_large and local_size >= multipart_threshold_bytes:
        try:
            sha256_file(fpath)  # Compute but can't compare
        except (OSError, IOError) as e:
            print(f"[WARNING] Could not compute SHA-256 for {fpath.name}: {e}")

    # Timestamp-based heuristic for large files
    last_modified = head.get("LastModified")
    if last_modified:
        import datetime
        local_mtime = datetime.datetime.fromtimestamp(fpath.stat().st_mtime, tz=datetime.timezone.utc)
        age_diff = abs((last_modified - local_mtime).total_seconds())

        if age_diff < 600:  # 10 minutes
            return (True, "size_and_timestamp_match")

        if age_diff > 3600:  # 1 hour
            print(f"[WARNING] Large file size match but timestamps differ by {age_diff/3600:.1f} hours: {fpath.name}")
            print(f"[WARNING] Local: {local_mtime}, S3: {last_modified}")
            print(f"[WARNING] Using size-only match - consider --force if concerned about integrity")

    return (True, "size_match_large")


def parse_uploaded_keys_from_log(log_csv: Path) -> Set[str]:
    """Parse CSV log to get already-uploaded S3 keys."""
    done: Set[str] = set()
    if not log_csv.exists():
        return done

    try:
        with open(log_csv, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                if (row.get("status") == "uploaded") and row.get("s3_key"):
                    done.add(row["s3_key"])
    except (OSError, IOError, csv.Error):
        pass

    return done


def atomic_write_text(path: Path, text: str) -> None:
    """Atomic file write using temp file + rename."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
