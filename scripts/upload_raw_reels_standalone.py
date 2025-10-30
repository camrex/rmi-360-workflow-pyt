#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
upload_raw_reels.py
===================

Upload RAW Mosaic reels to S3 with **crash-safe resume**, **reel-level progress**,
and a **live status (JSON) heartbeat**.

----------------------------------------------------------------------
OVERVIEW
----------------------------------------------------------------------
This tool recursively uploads RAW reel assets (e.g., .mp4, .json, .csv, .gpx)
from a local folder to an S3 bucket/prefix specified in a small YAML config.
It is designed to be **resumable** even after crashes or partial runs.

Resume works via:
  1) **S3 HEAD**: skip files that are already present in S3
     - For objects < multipart_threshold (default 64 MB): compare local MD5 to S3 ETag
     - For larger/multipart objects: use **size equality** (fast & reliable in practice)
  2) **CSV log**: still honored; if a file was logged as "uploaded", it’s skipped

The script also:
  • Groups files by **reel** (first path segment after your S3 prefix)
  • Writes a **live status JSON** you can tail or ingest elsewhere
  • Emits clear **reel start/complete** banners and per-reel tallies
  • Supports **--force** to re-upload regardless of S3 status
  • Handles **Ctrl+C/SIGTERM** gracefully, flushing a final status snapshot

----------------------------------------------------------------------
REQUIREMENTS
----------------------------------------------------------------------
- Python 3.9+
- Third party:
  - boto3      (pip install boto3)
  - PyYAML     (pip install pyyaml)
  - keyring    (optional; only if auth_mode=keyring)

----------------------------------------------------------------------
CONFIG YAML (MINIMAL)
----------------------------------------------------------------------
Example: config.yaml

aws:
  region: us-east-1
  s3_bucket_raw: my-raw-bucket
  # Optional:
  # auth_mode: config      # default; use standard AWS chain (env vars, profile, etc.)
  # auth_mode: instance    # use EC2/ECS role
  # auth_mode: keyring     # pull AK/SK from system keyring service "rmi_s3"
  # max_workers: "cpu*8"   # default is cpu*8 (or int)

# Optional:
# project_base: "E:/rmi/projects/25320"  # where logs/ will be created; defaults to folder of this config

----------------------------------------------------------------------
USAGE EXAMPLES
----------------------------------------------------------------------
# Basic upload:
python upload_raw_reels.py \
  --config E:/rmi/projects/25320/config.yaml \
  --folder E:/reels/ \
  --prefix RMI25320/reels/

# Dry-run (show what would be uploaded and exit):
python upload_raw_reels.py \
  --config E:/rmi/projects/25320/config.yaml \
  --folder E:/reels/ \
  --prefix RMI25320/reels/ \
  --dry-run

# Live status heartbeat (JSON) written every ~2s (configurable):
python upload_raw_reels.py \
  --config E:/rmi/projects/25320/config.yaml \
  --folder E:/reels/ \
  --prefix RMI25320/reels/ \
  --status-json E:/reels/upload_status.json \
  --status-interval 1.0

# Force re-upload even if files appear to exist in S3:
python upload_raw_reels.py \
  --config E:/rmi/projects/25320/config.yaml \
  --folder E:/reels/ \
  --prefix RMI25320/reels/ \
  --force

# Use keyring (if config aws.auth_mode: keyring):
#   keyring.set_password('rmi_s3', 'AWS_ACCESS_KEY_ID', '<AKIA...>')
#   keyring.set_password('rmi_s3', 'AWS_SECRET_ACCESS_KEY', '<SECRET>')
python upload_raw_reels.py \
  --config E:/rmi/projects/25320/config.yaml \
  --folder E:/reels/ \
  --prefix RMI25320/reels/

----------------------------------------------------------------------
REEL DETECTION
----------------------------------------------------------------------
The "reel" name is derived from the **first path segment after your S3 prefix**.
Example:
  prefix = "RMI25320/reels/"
  key    = "RMI25320/reels/UTICA202.765_20250414T133800Z/FR000016.mp4"
  reel   = "UTICA202.765_20250414T133800Z"

----------------------------------------------------------------------
STATUS JSON (HEARTBEAT) — SCHEMA (example; truncated)
----------------------------------------------------------------------
{
  "started_at": 1730182741.12,
  "phase": "uploading" | "reel_start" | "reel_complete" | "init",
  "current_reel": "UTICA202.765_20250414T133800Z",
  "current_file": "E:/reels/.../FR000016.mp4",
  "current_file_bytes": 83886080,
  "current_file_size": 262144000,
  "totals": { "files": 420, "uploaded": 119, "skipped": 301, "failed": 0, "bytes_uploaded": 127842091008 },
  "reels": {
    "UTICA202.765_20250414T133800Z": {
      "planned_files": 42,
      "uploaded": 41,
      "skipped": 1,
      "failed": 0,
      "bytes_uploaded": 127842091008,
      "started_at": 1730182741.12,
      "completed_at": 1730183922.77
    }
  },
  "last_update": 1730183799.45
}

----------------------------------------------------------------------
LOGGING / OUTPUT ARTIFACTS
----------------------------------------------------------------------
- CSV log:    <project_base>/logs/upload_raw_log.csv
- Status JSON (--status-json): path you specify (atomic writes)
- Console:    Reel banners, totals, upload speed

----------------------------------------------------------------------
BEHAVIOR NOTES
----------------------------------------------------------------------
- Resuming:
  * On each file: S3 HEAD is authoritative (existence & equality). Then the CSV log is consulted.
  * For **small objects (<64 MB)**, local MD5 must equal S3 ETag to skip.
  * For **large/multipart objects**, ETag ≠ MD5; we skip on **size match**.
- Integrity options:
  * If you need **cryptographic verification** for large files, extend this script to:
      - write/upload SHA-256 sidecar files; or
      - use S3 checksum APIs with multipart (more involved).
- Encryption:
  * Server-Side Encryption is set to "AES256" by default for all uploads.
- Interrupts:
  * Ctrl+C or SIGTERM triggers a final status flush and exits with code 130.

----------------------------------------------------------------------
EXIT CODES
----------------------------------------------------------------------
0  = success
2  = configuration or input path error
130= interrupted (SIGINT/SIGTERM)

----------------------------------------------------------------------
TROUBLESHOOTING
----------------------------------------------------------------------
- "botocore.exceptions.NoCredentialsError": ensure your AWS creds are available
  (env vars, ~/.aws/credentials, instance role, or keyring with auth_mode=keyring).
- AccessDenied on HEAD: verify bucket, prefix, and IAM permissions.
- MD5 mismatch on small files: file changed locally—re-run, or use --force to overwrite.

"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import os
import signal
import sys
import threading
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
    from botocore.exceptions import ClientError
except Exception:
    print("boto3 is required. Install with: pip install boto3", file=sys.stderr)
    raise


RAW_EXTS = {".mp4", ".json", ".csv", ".gpx"}  # extend if needed


# -----------------------------
# Config + path helpers
# -----------------------------

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
    mode = (auth_mode or "config").lower()
    if mode == "keyring":
        try:
            import keyring  # type: ignore
        except Exception:
            raise RuntimeError("auth_mode=keyring but 'keyring' is not installed. pip install keyring")
        ak = keyring.get_password(service_name, "AWS_ACCESS_KEY_ID")
        sk = keyring.get_password(service_name, "AWS_SECRET_ACCESS_KEY")
        if not ak or not sk:
            raise RuntimeError(
                f"Missing AWS credentials in keyring '{service_name}'. "
                "Run keyring.set_password('rmi_s3','AWS_ACCESS_KEY_ID',...) and for SECRET_ACCESS_KEY as well."
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


# -----------------------------
# Integrity + resume helpers
# -----------------------------

def md5_file(path: Path, blocksize: int = 8 * 1024 * 1024) -> str:
    """Fast streaming MD5 for small files (used when object is < multipart_threshold)."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(blocksize), b""):
            h.update(chunk)
    return h.hexdigest()


def s3_object_matches_local(
    s3, bucket: str, key: str, fpath: Path, multipart_threshold_bytes: int
) -> Tuple[bool, str]:
    """
    Check if S3 already has an identical object.
    - If object missing: (False, 'not_found')
    - If size differs: (False, 'size_diff')
    - If below multipart threshold: compare MD5 with ETag, (True,'etag_md5_match') or (False,'md5_diff')
    - If above threshold: treat size equality as match, (True, 'size_match_large')
    """
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("404", "NoSuchKey", "NotFound"):
            return (False, "not_found")
        # For other errors (e.g., access denied), do not assume presence
        return (False, f"head_error:{code or 'unknown'}")

    remote_size = head.get("ContentLength")
    local_size = fpath.stat().st_size
    if remote_size != local_size:
        return (False, "size_diff")

    etag = (head.get("ETag") or "").strip('"')
    if local_size < multipart_threshold_bytes and etag:
        try:
            local_md5 = md5_file(fpath)
            if local_md5 == etag:
                return (True, "etag_md5_match")
            else:
                return (False, "md5_diff")
        except Exception:
            # If MD5 fails for any reason, fall back to size-only
            return (True, "size_match_small_no_md5")

    return (True, "size_match_large")


# -----------------------------
# Status / heartbeat
# -----------------------------

def atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def now_ts() -> float:
    return time.time()


class StatusTracker:
    """
    Thread-safe, throttled JSON status writer with per-reel and global stats.

    Methods:
      - set_totals(n)
      - start_reel(name, planned_files)
      - complete_reel(name)
      - start_file(reel, fpath, size)
      - file_progress_cb(reel) -> callback(bytes_amount)
      - file_done(reel, outcome, size)
      - note_skip(reel)
    """

    def __init__(self, status_path: Optional[Path], interval_sec: float = 2.0):
        self.status_path = status_path
        self.interval = max(0.2, float(interval_sec))
        self.lock = threading.Lock()
        self.last_flush = 0.0
        self.data = {
            "started_at": now_ts(),
            "phase": "init",
            "current_reel": None,
            "current_file": None,
            "current_file_bytes": 0,
            "current_file_size": 0,
            "totals": {"files": 0, "uploaded": 0, "skipped": 0, "failed": 0, "bytes_uploaded": 0},
            "reels": {},   # reel_name -> stats
            "last_update": now_ts(),
        }

    def set_totals(self, total_files: int):
        with self.lock:
            self.data["totals"]["files"] = int(total_files)
            self._flush_if_due()

    def start_reel(self, reel: str, planned_files: int):
        with self.lock:
            self.data["phase"] = "reel_start"
            self.data["current_reel"] = reel
            self.data["reels"].setdefault(reel, {
                "planned_files": planned_files,
                "uploaded": 0, "skipped": 0, "failed": 0,
                "bytes_uploaded": 0,
                "started_at": now_ts(),
                "completed_at": None
            })
            self._flush(force=True)

    def complete_reel(self, reel: str):
        with self.lock:
            r = self.data["reels"].get(reel)
            if r:
                r["completed_at"] = now_ts()
            self.data["phase"] = "reel_complete"
            self.data["current_file"] = None
            self.data["current_file_bytes"] = 0
            self.data["current_file_size"] = 0
            self._flush(force=True)

    def start_file(self, reel: str, fpath: Path, size: int):
        with self.lock:
            self.data["phase"] = "uploading"
            self.data["current_reel"] = reel
            self.data["current_file"] = str(fpath)
            self.data["current_file_bytes"] = 0
            self.data["current_file_size"] = int(size)
            self._flush_if_due()

    def file_progress_cb(self, reel: str):
        # boto3-compatible progress callback closure
        def _cb(bytes_amount: int):
            with self.lock:
                self.data["current_file_bytes"] += int(bytes_amount)
                self._flush_if_due()
        return _cb

    def file_done(self, reel: str, outcome: str, size: int):
        with self.lock:
            r = self.data["reels"].setdefault(reel, {
                "planned_files": 0,
                "uploaded": 0, "skipped": 0, "failed": 0,
                "bytes_uploaded": 0,
                "started_at": now_ts(), "completed_at": None
            })
            if outcome == "uploaded":
                r["uploaded"] += 1
                r["bytes_uploaded"] += int(size)
                self.data["totals"]["uploaded"] += 1
                self.data["totals"]["bytes_uploaded"] += int(size)
            elif outcome == "skipped":
                r["skipped"] += 1
                self.data["totals"]["skipped"] += 1
            else:
                r["failed"] += 1
                self.data["totals"]["failed"] += 1
            self.data["current_file"] = None
            self.data["current_file_bytes"] = 0
            self.data["current_file_size"] = 0
            self._flush_if_due()

    def note_skip(self, reel: str):
        with self.lock:
            r = self.data["reels"].setdefault(reel, {
                "planned_files": 0,
                "uploaded": 0, "skipped": 0, "failed": 0,
                "bytes_uploaded": 0,
                "started_at": now_ts(), "completed_at": None
            })
            r["skipped"] += 1
            self.data["totals"]["skipped"] += 1
            self._flush_if_due())

    def _flush_if_due(self):
        if not self.status_path:
            return
        now = now_ts()
        if (now - self.last_flush) >= self.interval:
            self._flush()

    def _flush(self, force: bool = False):
        if not self.status_path:
            return
        self.data["last_update"] = now_ts()
        atomic_write_text(self.status_path, json.dumps(self.data, ensure_ascii=False, indent=2))
        self.last_flush = now_ts()


# -----------------------------
# Reel helper
# -----------------------------

def reel_from_key(s3_key: str, prefix: str) -> str:
    """
    Derive reel name from an S3 key by taking the first path segment AFTER the given prefix.
    If flat, returns the filename segment.
    """
    prefix = (prefix or "").strip().lstrip("/")
    rest = s3_key
    if prefix and s3_key.startswith(prefix):
        rest = s3_key[len(prefix):].lstrip("/")
    return rest.split("/", 1)[0] if "/" in rest else rest


# -----------------------------
# Main
# -----------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description="Upload RAW Mosaic reels to S3 with resume, reel-level status, and live heartbeat."
    )
    p.add_argument("--config", required=True, help="Path to config.yaml (must contain aws block).")
    p.add_argument("--folder", required=True, help="Local folder containing reel subfolders and files.")
    p.add_argument("--prefix", required=True, help="S3 prefix under aws.s3_bucket_raw (e.g., RMI25320/reels/).")
    p.add_argument("--project-base", dest="project_base",
                   help="Base folder for logs; defaults to the folder containing the config file.")
    p.add_argument("--dry-run", action="store_true", help="List would-be uploads and exit.")
    p.add_argument("--force", action="store_true", help="Force re-upload even if S3 already has the object.")
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

    # Group tasks into reels (first path segment after prefix)
    prefix_trim = args.prefix.strip().lstrip("/")
    reels: dict[str, list[Tuple[Path, str]]] = {}
    for fpath, key in tasks:
        rname = reel_from_key(key, prefix_trim)
        reels.setdefault(rname, []).append((fpath, key))

    # Dry run before doing any AWS calls
    if args.dry_run:
        shown = 0
        for rname in sorted(reels.keys()):
            print(f"[DRY-RUN] Reel: {rname} (files={len(reels[rname])})")
            for fpath, key in reels[rname][:5]:
                print(f"  [DRY-RUN] would upload: {fpath}  ->  s3://{bucket}/{key}")
                shown += 1
                if shown >= 25:
                    break
            if shown >= 25:
                break
        total_files = sum(len(v) for v in reels.values())
        if total_files > shown:
            print(f"[DRY-RUN] ...and {total_files - shown} more")
        print("[DRY-RUN] Exiting without uploading.")
        return 0

    # AWS + transfer
    session = resolve_session(auth_mode)
    s3 = session.client("s3", region_name=region)

    max_workers = resolve_max_concurrency(aws.get("max_workers", "cpu*8"))
    tcfg = TransferConfig(
        multipart_threshold=64 * 1024 * 1024,   # 64 MB
        multipart_chunksize=64 * 1024 * 1024,   # 64 MB
        max_concurrency=max_workers,
        use_threads=True,
    )
    transfer = S3Transfer(s3, config=tcfg)

    # Status tracker
    status_path = Path(args.status_json).resolve() if args.status_json else None
    tracker = StatusTracker(status_path, args.status_interval)
    tracker.set_totals(len(tasks))

    # Ctrl+C / SIGTERM graceful exit
    def _graceful_exit(signum, frame):
        try:
            tracker._flush(force=True)
        finally:
            print("\n[INFO] Received signal, exiting gracefully.", file=sys.stderr)
            sys.exit(130)

    signal.signal(signal.SIGINT, _graceful_exit)
    signal.signal(signal.SIGTERM, _graceful_exit)

    # Resume via prior log (secondary to S3 HEAD)
    already = parse_uploaded_keys_from_log(log_csv)
    new_file = not log_csv.exists()
    fcsv = open(log_csv, "a", newline="", encoding="utf-8")
    writer = csv.writer(fcsv)
    if new_file:
        writer.writerow([
            "timestamp", "local_file", "s3_key", "status", "error",
            "size_bytes", "duration_sec", "content_type"
        ])

    uploaded = skipped = failed = 0
    total_size = 0
    start = time.time()

    print(f"[INFO] Uploading to s3://{bucket}/{args.prefix.strip().lstrip('/')} ({len(tasks)} objects)")

    # Process per-reel
    for reel_name, reel_tasks in sorted(reels.items()):
        print(f"\n[REEL] >>> Starting reel: {reel_name} (files={len(reel_tasks)})")
        tracker.start_reel(reel_name, planned_files=len(reel_tasks))

        for fpath, key in reel_tasks:
            size = fpath.stat().st_size
            ctype = guess_content_type(fpath)

            # S3 existence / identity check unless forced
            if not args.force:
                match, why = s3_object_matches_local(s3, bucket, key, fpath, tcfg.multipart_threshold)
                if match:
                    skipped += 1
                    writer.writerow([time.time(), str(fpath), key, "skipped", f"exists:{why}", 0, 0.0, ctype or ""])
                    tracker.note_skip(reel_name)
                    continue

            # Fall back to prior log indication (if present)
            if key in already and not args.force:
                skipped += 1
                writer.writerow([time.time(), str(fpath), key, "skipped", "from prior log", 0, 0.0, ctype or ""])
                tracker.note_skip(reel_name)
                continue

            extra = {"ServerSideEncryption": "AES256"}
            if ctype:
                extra["ContentType"] = ctype

            tracker.start_file(reel_name, fpath, size)
            t0 = time.time()
            status = "uploaded"
            err = ""
            try:
                transfer.upload_file(
                    str(fpath),
                    bucket,
                    key,
                    extra_args=extra,
                    callback=tracker.file_progress_cb(reel_name),
                )
                uploaded += 1
                total_size += size
            except Exception as e:
                status = "error"
                err = str(e)
                failed += 1
            dt = time.time() - t0
            writer.writerow([time.time(), str(fpath), key, status, err, size, round(dt, 3), ctype or ""])
            tracker.file_done(reel_name, status, size)

        tracker.complete_reel(reel_name)
        rstats = tracker.data["reels"][reel_name]
        print(f"[REEL] <<< Completed reel: {reel_name} | uploaded={rstats['uploaded']} skipped={rstats['skipped']} failed={rstats['failed']} bytes={rstats['bytes_uploaded']}")

    fcsv.close()
    elapsed = time.time() - start
    mb = total_size / (1024 * 1024) if elapsed >= 0 else 0.0
    avg = mb / elapsed if elapsed > 0 else 0.0

    print(f"\n[DONE] Uploaded={uploaded} Skipped={skipped} Failed={failed} "
          f"TotalMB={mb:.2f} AvgMBps={avg:.2f} Log={log_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
