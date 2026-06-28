# =============================================================================
# 🔁 OID Storage Migration Helpers (utils/shared/oid_storage_migration.py)
# -----------------------------------------------------------------------------
# Purpose:             Reusable primitives for migrating a published OID between
#                      legacy (public S3 URL) and secured (virtual cache) delivery.
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             0.1.0 (scaffold)
# Author:              RMI Valuation, LLC
#
# Description:
#   Migration is three separable concerns:
#     1. Object location  -> sync_s3_objects()   (server-side bucket->bucket copy)
#     2. ImagePath form    -> rewrite_oid_image_paths()  (public URL <-> $virtualCacheDirectory)
#     3. Service publish   -> (re-run utils.generate_oid_service; not done here)
#   Plus two read-only reconciliation helpers used before/after a migration:
#     - audit_oid_vs_s3()          : OID rows vs bucket keys (orphans / missing)
#     - validate_imagepath_reachability() : sample rows and probe each ImagePath
#
#   The object KEY layout is identical across modes ({prefix}/{filename}), so a
#   migration is a key-for-key bucket copy plus an ImagePath rewrite. See
#   utils/shared/oid_storage_paths.py for the single source of truth on path form.
#
# File Location:        /utils/shared/oid_storage_migration.py
# Int. Dependencies:    utils/shared/oid_storage_paths, utils/shared/aws_utils
# Ext. Dependencies:    arcpy (cursors), boto3 (via aws_utils session)
#
# Notes:
#   - All MUTATING functions default to dry_run=True and report what they WOULD do.
#   - Secured-storage reachability remains unverified pending Esri Case 04187998;
#     the secured branch of validate_imagepath_reachability() is intentionally a
#     conservative key-existence check, not a true end-to-end serve check.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from utils.shared.oid_storage_paths import (
    build_oid_image_path_for_mode,
    build_oid_object_key,
    extract_filename_from_image_path,
    resolve_oid_key_prefix,
    resolve_oid_target_bucket,
    resolve_oid_target_region,
)

if TYPE_CHECKING:
    from utils.manager.config_manager import ConfigManager


# -----------------------------------------------------------------------------
# Result containers
# -----------------------------------------------------------------------------
@dataclass
class RewriteResult:
    total_rows: int = 0
    changed: int = 0
    unchanged: int = 0
    unparseable: int = 0
    dry_run: bool = True
    samples: List[Tuple[str, str]] = field(default_factory=list)  # (old, new) preview


@dataclass
class SyncResult:
    listed: int = 0
    copied: int = 0
    skipped_existing: int = 0
    failed: int = 0
    dry_run: bool = True
    failures: List[Tuple[str, str]] = field(default_factory=list)  # (key, error)


@dataclass
class AuditResult:
    oid_keys: int = 0
    bucket_keys: int = 0
    missing_in_bucket: List[str] = field(default_factory=list)  # in OID, not in bucket
    orphans_in_bucket: List[str] = field(default_factory=list)  # in bucket, not in OID


@dataclass
class ReachabilityResult:
    sampled: int = 0
    ok: int = 0
    failed: int = 0
    secured_mode: bool = False
    failures: List[Tuple[str, str]] = field(default_factory=list)  # (image_path, reason)


# -----------------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------------
def _s3_client(cfg: "ConfigManager", bucket: Optional[str] = None):
    """Validated boto3 S3 client for the given bucket (defaults to the resolved target bucket)."""
    from utils.shared.aws_utils import validate_s3_bucket_access

    session = validate_s3_bucket_access(cfg, bucket=bucket)
    return session.client("s3")


def _list_bucket_keys(s3, bucket: str, prefix: str) -> List[str]:
    """Return all object keys under prefix using a paginator."""
    keys: List[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    norm = (prefix or "").strip().strip("/")
    kwargs = {"Bucket": bucket}
    if norm:
        kwargs["Prefix"] = f"{norm}/"
    for page in paginator.paginate(**kwargs):
        for obj in page.get("Contents", []) or []:
            keys.append(obj["Key"])
    return keys


# -----------------------------------------------------------------------------
# Concern 2: ImagePath rewrite (in place, on a feature class)
# -----------------------------------------------------------------------------
def rewrite_oid_image_paths(
    cfg: "ConfigManager",
    oid_fc: str,
    target_secured: bool,
    logger,
    dry_run: bool = True,
) -> RewriteResult:
    """
    Rewrite every ImagePath in ``oid_fc`` into the target delivery form, recovering
    the filename from whatever form each row currently holds. Idempotent.

    NOTE: This mutates the feature class in place. Callers that want to keep the
    source pristine should operate on a copy (mirroring generate_oid_service's
    ``*_aws`` duplicate pattern).
    """
    import arcpy

    result = RewriteResult(dry_run=dry_run)
    mode_label = "secured ($virtualCacheDirectory)" if target_secured else "legacy public URL"
    logger.info(f"Rewriting ImagePaths -> {mode_label} {'(DRY RUN)' if dry_run else ''}", indent=2)

    with arcpy.da.UpdateCursor(oid_fc, ["ImagePath"]) as cursor:
        for row in cursor:
            result.total_rows += 1
            old_path = row[0]
            filename = extract_filename_from_image_path(old_path)
            if not filename:
                result.unparseable += 1
                logger.warning(f"Could not parse filename from ImagePath: {old_path!r}", indent=3)
                continue

            new_path = build_oid_image_path_for_mode(cfg, filename, secured=target_secured)
            if new_path == old_path:
                result.unchanged += 1
                continue

            result.changed += 1
            if len(result.samples) < 5:
                result.samples.append((old_path, new_path))

            if not dry_run:
                row[0] = new_path
                cursor.updateRow(row)

    logger.info(
        f"ImagePath rewrite: {result.changed} changed, {result.unchanged} unchanged, "
        f"{result.unparseable} unparseable of {result.total_rows} rows.",
        indent=2,
    )
    return result


# -----------------------------------------------------------------------------
# Concern 1: S3 object sync (server-side, key-for-key)
# -----------------------------------------------------------------------------
def sync_s3_objects(
    cfg: "ConfigManager",
    source_bucket: str,
    dest_bucket: str,
    logger,
    prefix: Optional[str] = None,
    skip_existing: bool = True,
    dry_run: bool = True,
) -> SyncResult:
    """
    Server-side copy every object under ``prefix`` from source_bucket to dest_bucket,
    preserving the key. Because the key layout is identical across delivery modes,
    this is a safe, no-reupload migration of the image bytes.

    When prefix is None, the OID key prefix is resolved from config (project slug
    by default) so a project's images move as a unit.
    """
    result = SyncResult(dry_run=dry_run)

    if prefix is None:
        prefix = resolve_oid_key_prefix(cfg)

    logger.info(
        f"Sync s3://{source_bucket}/{prefix} -> s3://{dest_bucket}/{prefix} "
        f"{'(DRY RUN)' if dry_run else ''}",
        indent=2,
    )

    src_s3 = _s3_client(cfg, bucket=source_bucket)
    keys = _list_bucket_keys(src_s3, source_bucket, prefix)
    result.listed = len(keys)
    logger.info(f"Found {result.listed} source objects under prefix.", indent=3)

    # Reuse the source client unless the destination needs its own preflight; for
    # cross-account buckets the caller should ensure the session can write to dest.
    dst_s3 = _s3_client(cfg, bucket=dest_bucket) if not dry_run else None

    for key in keys:
        try:
            if skip_existing and dst_s3 is not None:
                try:
                    dst_s3.head_object(Bucket=dest_bucket, Key=key)
                    result.skipped_existing += 1
                    continue
                except Exception:
                    pass  # not present -> proceed to copy

            if dry_run:
                result.copied += 1  # would-copy count
                continue

            dst_s3.copy_object(
                Bucket=dest_bucket,
                Key=key,
                CopySource={"Bucket": source_bucket, "Key": key},
            )
            result.copied += 1
        except Exception as ex:  # noqa: BLE001 - report per-key, keep going
            result.failed += 1
            result.failures.append((key, str(ex)))
            logger.warning(f"Copy failed for {key}: {ex}", indent=3)

    verb = "would copy" if dry_run else "copied"
    logger.info(
        f"Sync: {verb} {result.copied}, skipped {result.skipped_existing}, failed {result.failed}.",
        indent=2,
    )
    return result


# -----------------------------------------------------------------------------
# Read-only: reconcile OID rows against bucket contents
# -----------------------------------------------------------------------------
def audit_oid_vs_s3(
    cfg: "ConfigManager",
    oid_fc: str,
    logger,
    bucket: Optional[str] = None,
    secured_mode: Optional[bool] = None,
    max_report: int = 25,
) -> AuditResult:
    """
    Compare the keys implied by each OID ImagePath against the keys present in the
    bucket. Reports rows whose image is missing from the bucket and bucket objects
    with no corresponding OID row (orphans). Read-only.
    """
    import arcpy

    result = AuditResult()
    bucket = bucket or resolve_oid_target_bucket(cfg, secured_mode=secured_mode)
    prefix = resolve_oid_key_prefix(cfg, secured_mode=secured_mode)

    # Expected keys from OID rows.
    oid_key_set = set()
    with arcpy.da.SearchCursor(oid_fc, ["ImagePath"]) as cursor:
        for (image_path,) in cursor:
            filename = extract_filename_from_image_path(image_path)
            if not filename:
                continue
            oid_key_set.add(build_oid_object_key(cfg, filename, secured_mode=secured_mode))
    result.oid_keys = len(oid_key_set)

    # Actual keys from the bucket.
    s3 = _s3_client(cfg, bucket=bucket)
    bucket_key_set = set(_list_bucket_keys(s3, bucket, prefix))
    result.bucket_keys = len(bucket_key_set)

    result.missing_in_bucket = sorted(oid_key_set - bucket_key_set)[:max_report]
    result.orphans_in_bucket = sorted(bucket_key_set - oid_key_set)[:max_report]

    logger.info(
        f"Audit: {result.oid_keys} OID keys vs {result.bucket_keys} bucket keys; "
        f"{len(oid_key_set - bucket_key_set)} missing, {len(bucket_key_set - oid_key_set)} orphaned.",
        indent=2,
    )
    return result


# -----------------------------------------------------------------------------
# Read-only: probe that ImagePaths actually resolve
# -----------------------------------------------------------------------------
def validate_imagepath_reachability(
    cfg: "ConfigManager",
    oid_fc: str,
    logger,
    sample: int = 10,
    secured_mode: Optional[bool] = None,
) -> ReachabilityResult:
    """
    Sample up to ``sample`` rows and verify each ImagePath resolves.

    Legacy/public rows: HTTP HEAD the URL, expect 200.
    Secured rows: TODO(esri-04187998) a true end-to-end serve check is not yet
        possible. As a conservative proxy we confirm the underlying object key
        exists in aws.s3_bucket_panos_secured. This catches "bytes never landed in
        the secured bucket" but NOT "Enterprise cannot serve from the cloud store".
    """
    import arcpy
    from utils.shared.oid_storage_paths import is_secured_storage_enabled

    secured = is_secured_storage_enabled(cfg) if secured_mode is None else bool(secured_mode)
    result = ReachabilityResult(secured_mode=secured)

    paths: List[str] = []
    with arcpy.da.SearchCursor(oid_fc, ["ImagePath"]) as cursor:
        for (image_path,) in cursor:
            if image_path:
                paths.append(image_path)
            if len(paths) >= sample:
                break

    if secured:
        bucket = resolve_oid_target_bucket(cfg, secured_mode=True)
        s3 = _s3_client(cfg, bucket=bucket)

    for image_path in paths:
        result.sampled += 1
        try:
            if secured:
                filename = extract_filename_from_image_path(image_path)
                key = build_oid_object_key(cfg, filename, secured_mode=True)
                s3.head_object(Bucket=bucket, Key=key)  # raises if absent
                result.ok += 1
            else:
                ok, reason = _http_head_ok(image_path)
                if ok:
                    result.ok += 1
                else:
                    result.failed += 1
                    result.failures.append((image_path, reason))
        except Exception as ex:  # noqa: BLE001
            result.failed += 1
            result.failures.append((image_path, str(ex)))

    note = " (secured: key-existence proxy; see Esri Case 04187998)" if secured else ""
    logger.info(
        f"Reachability: {result.ok}/{result.sampled} OK, {result.failed} failed{note}.",
        indent=2,
    )
    return result


def _http_head_ok(url: str, timeout: float = 10.0) -> Tuple[bool, str]:
    """HEAD a public URL; return (ok, reason). Falls back to GET if HEAD is blocked."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", resp.getcode())
            return (200 <= code < 300), f"HTTP {code}"
    except urllib.error.HTTPError as ex:
        if ex.code == 405:  # method not allowed -> retry with GET
            try:
                with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as resp:
                    code = getattr(resp, "status", resp.getcode())
                    return (200 <= code < 300), f"HTTP {code} (GET)"
            except Exception as ex2:  # noqa: BLE001
                return False, str(ex2)
        return False, f"HTTP {ex.code}"
    except Exception as ex:  # noqa: BLE001
        return False, str(ex)
