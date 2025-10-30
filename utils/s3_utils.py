# utils/s3_utils.py
from __future__ import annotations
from pathlib import Path
import concurrent.futures as cf
from typing import Iterable, List, Optional, Tuple, Dict
import boto3
import os

__all__ = [
    "normalize_prefix",
    "list_projects",
    "list_reels",
    "stage_reels",          # NEW (preferred)
    "stage_reels_prefix",   # legacy shim -> calls stage_reels
    "stage_project_files",  # NEW: stage config/gis_data files
]

def normalize_prefix(prefix: str) -> str:
    p = (prefix or "").strip().lstrip("/")
    if p and not p.endswith("/"):
        p += "/"
    return p

def _client():
    return boto3.client("s3")

def list_projects(bucket: str, s3=None) -> List[str]:
    s3 = s3 or _client()
    keys: List[str] = []
    token: Optional[str] = None
    while True:
        kwargs = dict(Bucket=bucket, Delimiter="/")
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for cp in resp.get("CommonPrefixes", []) or []:
            pref = (cp.get("Prefix") or "").rstrip("/")
            if pref:
                keys.append(pref)
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return sorted(set(keys))

def list_reels(bucket: str, project_key: str, s3=None) -> List[str]:
    s3 = s3 or _client()
    base = normalize_prefix(f"{project_key}/reels")
    names: List[str] = []
    token: Optional[str] = None
    while True:
        kwargs = dict(Bucket=bucket, Prefix=base, Delimiter="/")
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for cp in resp.get("CommonPrefixes", []) or []:
            p = cp.get("Prefix") or ""
            seg = p[:-1].split("/")[-1] if p.endswith("/") else p.split("/")[-1]
            if seg:
                names.append(seg)
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return sorted(set(names))

# -----------------------
# NEW: stage_reels
# -----------------------
def stage_reels(
    bucket: str,
    project_key: str,
    reels: Optional[List[str]],
    local_project_dir: Path,
    max_workers: int = 16,
    skip_if_exists: bool = True,
) -> Path:
    """
    Stage one or more reels under s3://{bucket}/{project_key}/reels/ to:
        {local_project_dir}/reels/{reel}/(files)

    If reels is None or empty, stages *all* reels under project_key/reels/.
    Skips files that already exist locally with matching size (and ETag if single-part).
    """
    s3 = _client()
    local_project_dir = Path(local_project_dir)
    local_reels_root = local_project_dir / "reels"
    local_reels_root.mkdir(parents=True, exist_ok=True)

    # Build the list of prefixes to pull
    if not reels:
        # discover all reels
        reels = list_reels(bucket, project_key, s3=s3)

    prefixes = [normalize_prefix(f"{project_key}/reels/{r}") for r in reels]

    # Collect S3 objects to download with their intended local path
    to_get: List[Tuple[str, Path, int, str]] = []  # (key, dst, size, etag)
    paginator = s3.get_paginator("list_objects_v2")

    for prefix in prefixes:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                # Preserve project structure from 'reels/' downward
                # key like: {project_key}/reels/{reel}/...  -> local: <project_dir>/reels/{reel}/...
                rel_after_project = key[len(normalize_prefix(project_key)):]  # e.g., 'reels/xxx/file'
                dst = local_project_dir / rel_after_project
                to_get.append((key, dst, int(obj.get("Size", 0)), (obj.get("ETag") or "").strip('"')))

    # Skip already-staged files (size match; if ETag length==32 treat as md5 and compare hash if you want)
    filtered: List[Tuple[str, Path, int, str]] = []
    for key, dst, size, etag in to_get:
        if not skip_if_exists or not dst.exists():
            filtered.append((key, dst, size, etag))
        else:
            try:
                if dst.stat().st_size != size:
                    filtered.append((key, dst, size, etag))
                # Optionally: add a fast MD5 check only when ETag looks like single-part (32 hex)
                # else: assume size match is sufficient
            except Exception:
                filtered.append((key, dst, size, etag))

    def _dl(k: str, p: Path):
        p.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(bucket, k, str(p))

    if filtered:
        with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
            list(ex.map(lambda tup: _dl(tup[0], tup[1]), filtered))

    return local_reels_root

# -----------------------
# Legacy shim
# -----------------------
def stage_reels_prefix(bucket: str, prefix: str, local_parent: Path, max_workers: int = 16) -> Path:
    """
    Back-compat wrapper. Prefix may be 'project/reels/' or 'project/reels/reel_xxx/'.
    Downloads under local_parent preserving structure from 'reels/' downward.
    """
    # Infer project_key and reel(s)
    norm = normalize_prefix(prefix)
    parts = norm.split("/")
    # Expect: [project_key, 'reels', <reel?>, ...]
    if len(parts) >= 2 and parts[1] == "reels":
        project_key = parts[0]
        reel = parts[2] if len(parts) >= 3 and parts[2] else None
        return stage_reels(
            bucket=bucket,
            project_key=project_key,
            reels=[reel] if reel else None,
            local_project_dir=Path(local_parent),
            max_workers=max_workers,
        )
    # Fallback: stage all under prefix (if non-standard); put under local_parent
    return stage_reels(bucket=bucket, project_key=parts[0], reels=None, local_project_dir=Path(local_parent), max_workers=max_workers)

# -----------------------
# NEW: stage_project_files
# -----------------------
def stage_project_files(
    bucket: str,
    project_key: str,
    folder_types: Optional[List[str]],
    local_project_dir: Path,
    max_workers: int = 16,
    skip_if_exists: bool = True,
) -> Dict[str, Path]:
    """
    Stage config and/or gis_data files from S3 to local project directory.

    Downloads files from s3://{bucket}/{project_key}/{folder_type}/ to:
        {local_project_dir}/{folder_type}/(files)

    Args:
        bucket: S3 bucket name
        project_key: Project identifier (e.g., 'RMI25320')
        folder_types: List of folder types to stage (e.g., ['config', 'gis_data']).
                     If None or empty, stages both config and gis_data.
        local_project_dir: Local base directory for the project
        max_workers: Number of concurrent download threads
        skip_if_exists: Skip files that already exist locally with matching size

    Returns:
        Dict mapping folder_type to local Path where files were staged

    Example:
        paths = stage_project_files(
            bucket='rmi-360-raw',
            project_key='RMI25320',
            folder_types=['config', 'gis_data'],
            local_project_dir=Path('D:/Process360_Data/projects/RMI25320')
        )
        # Returns: {'config': Path('D:/Process360_Data/projects/RMI25320/config'),
        #           'gis_data': Path('D:/Process360_Data/projects/RMI25320/gis_data')}
    """
    s3 = _client()
    local_project_dir = Path(local_project_dir)

    # Default to both config and gis_data if not specified
    if not folder_types:
        folder_types = ['config', 'gis_data']

    result_paths: Dict[str, Path] = {}

    for folder_type in folder_types:
        local_folder = local_project_dir / folder_type
        local_folder.mkdir(parents=True, exist_ok=True)

        # Build S3 prefix for this folder type
        prefix = normalize_prefix(f"{project_key}/{folder_type}")

        # Collect files to download
        to_get: List[Tuple[str, Path, int, str]] = []  # (key, dst, size, etag)
        paginator = s3.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                key = obj["Key"]
                if key.endswith("/"):
                    continue

                # Get relative path after project_key
                rel_after_project = key[len(normalize_prefix(project_key)):]  # e.g., 'config/file.yaml'
                dst = local_project_dir / rel_after_project
                to_get.append((key, dst, int(obj.get("Size", 0)), (obj.get("ETag") or "").strip('"')))

        # Filter based on skip_if_exists
        filtered: List[Tuple[str, Path, int, str]] = []
        for key, dst, size, etag in to_get:
            if not skip_if_exists or not dst.exists():
                filtered.append((key, dst, size, etag))
            else:
                try:
                    if dst.stat().st_size != size:
                        filtered.append((key, dst, size, etag))
                except Exception:
                    filtered.append((key, dst, size, etag))

        # Download files
        def _dl(k: str, p: Path):
            p.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, k, str(p))

        if filtered:
            with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
                list(ex.map(lambda tup: _dl(tup[0], tup[1]), filtered))

        result_paths[folder_type] = local_folder

    return result_paths
