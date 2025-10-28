# utils/s3_stage.py
from __future__ import annotations
from pathlib import Path
import concurrent.futures as cf
import boto3

def stage_reels_prefix(bucket: str, prefix: str, local_parent: Path, max_workers: int = 16) -> Path:
    """
    Downloads all objects under s3://{bucket}/{prefix} to local_parent, preserving folders.
    Returns the local path that should be used as Input Reels Folder in the toolbox.
    """
    s3 = boto3.client("s3")
    prefix = prefix.lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    paginator = s3.get_paginator("list_objects_v2")
    to_get = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []) or []:  # <-- handles no Contents
            key = obj["Key"]
            if key.endswith("/"):
                continue
            dst = local_parent / key[len(prefix):]
            to_get.append((key, dst))

    def _dl(k, p):
        p.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(bucket, k, str(p))

    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        list(ex.map(lambda x: _dl(*x), to_get))

    return local_parent  # the parent that now contains the reels subfolders
