# utils/s3_utils.py
from __future__ import annotations
from pathlib import Path
import concurrent.futures as cf
from typing import Iterable, List, Optional
import boto3

__all__ = [
    "normalize_prefix",
    "list_projects",
    "list_reels",
    "stage_reels_prefix",
]

def normalize_prefix(prefix: str) -> str:
    """
    Returns a normalized S3 key prefix like 'RMI25320/reels/' (no leading slash, trailing slash present).
    """
    if not prefix:
        return ""
    p = prefix.strip().lstrip("/")
    if p and not p.endswith("/"):
        p += "/"
    return p

def _client():
    return boto3.client("s3")

def list_projects(bucket: str, s3=None) -> List[str]:
    """
    Lists top-level 'folders' in the raw bucket (used for AWS project_key dropdown).
    """
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
    """
    Lists reel 'folders' under s3://{bucket}/{project_key}/reels/.
    Returns bare folder names like ['reel_0001_...','reel_0002_...'].
    """
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

def stage_reels_prefix(bucket: str, prefix: str, local_parent: Path, max_workers: int = 16) -> Path:
    """
    Downloads all objects under s3://{bucket}/{prefix} to local_parent, preserving folders.
    Returns local_parent (which will now contain the reels subfolders).
    """
    s3 = _client()
    prefix = normalize_prefix(prefix)

    paginator = s3.get_paginator("list_objects_v2")
    to_get: List[tuple[str, Path]] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []) or []:  # handles no Contents
            key = obj["Key"]
            if key.endswith("/"):
                continue
            dst = local_parent / key[len(prefix):]
            to_get.append((key, dst))

    def _dl(k: str, p: Path):
        p.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(bucket, k, str(p))

    if to_get:
        with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
            list(ex.map(lambda x: _dl(*x), to_get))

    return local_parent
