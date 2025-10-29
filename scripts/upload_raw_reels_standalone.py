#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations
import argparse
import csv
import mimetypes
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple, Set, Optional

# Third-party deps: boto3, pyyaml
try:
    import yaml  # PyYAML
except Exception:
    print("PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    raise

try:
    import boto3
    from boto3.s3.transfer import S3Transfer, TransferConfig
except Exception:
    print("boto3 is required. Install with: pip install boto3", file=sys.stderr)
    raise


RAW_EXTS = {".mp4", ".json", ".csv", ".gpx"}  # extend if needed


def load_cfg(cfg_path: Path) -> dict:
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config yaml must parse to a mapping")
    if "aws" not in data or not isinstance(data["aws"], dict):
        raise ValueError("config must include an 'aws' mapping")
    return data


def resolve_project_base(args: argparse.Namespace, cfg: dict) -> Path:
    # 1) --project-base flag
    if args.project_base:
        return Path(args.project_base).resolve()
    # 2) project_base in yaml
    pb = cfg.get("project_base")
    if pb:
        return Path(pb).resolve()
    # 3) default to the config file folder
    return Path(args.config).resolve().parent


def resolve_session(auth_mode: Optional[str], service_name: str | None = "rmi_s3"):
    import boto3
    import keyring
    mode = (auth_mode or "config").lower()

    if mode == "keyring":
        ak = keyring.get_password(service_name, "AWS_ACCESS_KEY_ID")
        sk = keyring.get_password(service_name, "AWS_SECRET_ACCESS_KEY")
        if not ak or not sk:
            raise RuntimeError(
                f"Missing AWS credentials in keyring '{service_name}'. "
                "Run keyring.set_password('rmi_s3', 'AWS_ACCESS_KEY_ID', ...) first."
            )
        return boto3.Session(aws_access_key_id=ak, aws_secret_access_key=sk)

    elif mode == "instance":
        # use EC2 instance role
        return boto3.Session()

    # fallback to default AWS credential chain
    return boto3.Session()


def resolve_max_concurrency(val) -> int:
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


def guess_content_type(path: Path) -> Optional[str]:
    ctype, _ = mimetypes.guess_type(str(path))
    return ctype


def collect_upload_tasks(base_dir: Path, allow_exts: set[str], s3_prefix: str) -> List[Tuple[Path, str]]:
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


def parse_uploaded_keys_from_log(log_csv: Path) -> Set[str]:
    done: Set[str] = set()
    if not log_csv.exists():
        return done
    try:
        with open(log_csv, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                if (row.get("status") == "uploaded") and row.get("s3_key"):
                    done.add(row["s3_key"])
    except Exception:
        pass
    return done


def main() -> int:
    p = argparse.ArgumentParser(description="Upload RAW Mosaic reels to s3://<aws.s3_bucket_raw>/<prefix>")
    p.add_argument("--config", required=True, help="Path to light config.yaml (only 'aws' block is required).")
    p.add_argument("--folder", required=True, help="Local folder containing reels or a single reel folder.")
    p.add_argument("--prefix", required=True, help="S3 prefix under aws.s3_bucket_raw (e.g., RMI25320/reels/).")
    p.add_argument("--project-base", dest="project_base", help="Base folder for logs; defaults to config folder.")
    p.add_argument("--dry-run", action="store_true", help="List would-be uploads and exit.")
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

    project_base = resolve_project_base(args, cfg)
    log_dir = (project_base / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_csv = log_dir / "upload_raw_log.csv"

    print(f"[INFO] Starting RAW upload helper")
    print(f"[INFO] Config:       {cfg_path}")
    print(f"[INFO] Project base: {project_base}")
    print(f"[INFO] Local folder: {local_folder}")
    print(f"[INFO] S3 bucket:    {bucket}")
    print(f"[INFO] S3 prefix:    {args.prefix}")
    print(f"[INFO] Auth mode:    {auth_mode}")

    tasks = collect_upload_tasks(local_folder, RAW_EXTS, args.prefix)
    print(f"[INFO] Discovered {len(tasks)} files to consider for upload (exts={sorted(RAW_EXTS)})")

    if args.dry_run:
        for fpath, key in tasks[:20]:
            print(f"[DRY-RUN] would upload: {fpath}  ->  s3://{bucket}/{key}")
        if len(tasks) > 20:
            print(f"[DRY-RUN] ...and {len(tasks)-20} more")
        print("[DRY-RUN] Exiting without uploading.")
        return 0

    session = resolve_session(auth_mode)
    s3 = session.client("s3", region_name=region)

    max_workers = resolve_max_concurrency(aws.get("max_workers", "cpu*8"))
    tcfg = TransferConfig(
        multipart_threshold=64 * 1024 * 1024,
        multipart_chunksize=64 * 1024 * 1024,
        max_concurrency=max_workers,
        use_threads=True,
    )
    transfer = S3Transfer(s3, config=tcfg)

    # resume support
    already = parse_uploaded_keys_from_log(log_csv)
    new_file = not log_csv.exists()
    fcsv = open(log_csv, "a", newline="", encoding="utf-8")
    writer = csv.writer(fcsv)
    if new_file:
        writer.writerow(["timestamp", "local_file", "s3_key", "status", "error", "size_bytes", "duration_sec", "content_type"])

    total = len(tasks)
    uploaded = skipped = failed = 0
    total_size = 0
    start = time.time()

    print(f"[INFO] Uploading to s3://{bucket}/{args.prefix.strip().lstrip('/')} ({total} objects)")

    for fpath, key in tasks:
        if key in already:
            skipped += 1
            writer.writerow([time.time(), str(fpath), key, "skipped", "from prior log", 0, 0.0, ""])
            continue

        size = fpath.stat().st_size
        ctype = guess_content_type(fpath)

        # Build ExtraArgs with required encryption if your bucket enforces it.
        extra = {}
        if ctype:
            extra["ContentType"] = ctype

        # Always set SSE for raw (safe default). If you prefer to control it via config, see “Optional: config-driven” below.
        extra["ServerSideEncryption"] = "AES256"
        
        t0 = time.time()
        status = "uploaded"
        err = ""
        try:
            if extra:
                transfer.upload_file(str(fpath), bucket, key, extra_args=extra)
            else:
                transfer.upload_file(str(fpath), bucket, key)
            uploaded += 1
            total_size += size
        except Exception as e:
            status = "error"
            err = str(e)
            failed += 1
        dt = time.time() - t0
        writer.writerow([time.time(), str(fpath), key, status, err, size, round(dt, 3), ctype or ""])

    fcsv.close()
    elapsed = time.time() - start
    mb = total_size / (1024 * 1024) if elapsed >= 0 else 0.0
    avg = mb / elapsed if elapsed > 0 else 0.0

    print(f"[DONE] Uploaded={uploaded} Skipped={skipped} Failed={failed} "
          f"TotalMB={mb:.2f} AvgMBps={avg:.2f} Log={log_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
