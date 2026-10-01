# =============================================================================
# 🧪 Deploy Secured Test Set (utils/deploy_secured_test_set.py)
# -----------------------------------------------------------------------------
# Purpose:             Stage a SMALL test subset of an existing OID into a target
#                      S3 bucket/region (e.g. us-east-1) and publish a secured
#                      Oriented Imagery service, to validate secured-storage in the
#                      same region as the ArcGIS Enterprise deployment.
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             0.1.0
# Author:              RMI Valuation, LLC
#
# Description:
#   Reuses the storage primitives (oid_storage_paths / oid_storage_migration /
#   generate_oid_service). Two-pass by design, because the cloud-store
#   REGISTRATION is an ArcGIS Enterprise admin step this tool cannot perform:
#     Pass 1 (publish=False): ensure bucket -> subset OID -> cross-region sync of
#       only the subset's keys -> rewrite test OID to secured paths -> emit the
#       values to register a cloud store.
#     Pass 2 (publish=True, cloud_store_name=...): publish the test OID bound to
#       the registered cloud store via GenerateServiceFromOrientedImageryDataset.
#
#   DRY RUN by default — reports what it WOULD do (incl. bucket create, copies,
#   path rewrite, publish) without mutating AWS or the OID.
#
# Int. Dependencies:   utils/shared/aws_utils, utils/shared/oid_storage_paths,
#                      utils/generate_oid_service
# Ext. Dependencies:   arcpy, boto3 (via aws_utils session)
# =============================================================================

from __future__ import annotations

import os
from typing import Dict, List, Optional

import arcpy

from utils.manager.config_manager import ConfigManager
from utils.shared.aws_utils import get_boto3_session
from utils.shared.oid_storage_paths import (
    SECURED_IMAGE_PATH_PREFIX,
    extract_filename_from_image_path,
    resolve_oid_key_prefix,
    resolve_oid_target_bucket,
)

__all__ = ["deploy_secured_test_set"]


def _extract_object_key(image_path) -> Optional[str]:
    """Full S3 object key (``{prefix}/{filename}``) embedded in a secured or
    public-URL ImagePath, or None for a local path. Using the source key verbatim
    means the sync works regardless of the configured prefix (important for older
    project configs whose resolved prefix may not match the published objects)."""
    if not isinstance(image_path, str):
        return None
    text = image_path.strip()
    if text.startswith(SECURED_IMAGE_PATH_PREFIX):
        return text[len(SECURED_IMAGE_PATH_PREFIX):].strip().strip("/") or None
    if text.lower().startswith(("http://", "https://")):
        after_scheme = text.split("://", 1)[1]
        slash = after_scheme.find("/")
        if slash == -1:
            return None
        return after_scheme[slash + 1:].split("?", 1)[0].strip("/") or None
    return None  # local path -> no S3 key


def _detect_source_bucket(cfg: ConfigManager, source_oid_fc: str, logger) -> Optional[str]:
    """Infer where the source images live from the OID's ImagePath FORM. Secured
    ($virtualCacheDirectory) and public-URL paths are bucket-agnostic in shape, so
    we map the detected MODE to the configured secured/unsecured bucket. A local
    path means the images aren't in S3 (nothing to sync)."""
    first = None
    with arcpy.da.SearchCursor(source_oid_fc, ["ImagePath"]) as cur:
        for (ip,) in cur:
            if ip:
                first = str(ip)
                break

    # Resolve against BOTH schemas: new (aws.s3_bucket_panos_*) and older 1.3.x
    # (secured_storage.s3_bucket / aws.s3_bucket).
    if first and first.startswith(SECURED_IMAGE_PATH_PREFIX):
        bucket = resolve_oid_target_bucket(cfg, secured_mode=True) or cfg.get("secured_storage.s3_bucket")
        logger.info(f"Detected SECURED source OID → source bucket: {bucket}", indent=2)
        return bucket
    if first and first.lower().startswith(("http://", "https://")):
        bucket = resolve_oid_target_bucket(cfg, secured_mode=False) or cfg.get("aws.s3_bucket")
        logger.info(f"Detected public-URL source OID → source bucket: {bucket}", indent=2)
        return bucket

    logger.warning(
        "Source OID ImagePaths look LOCAL (not an S3/secured form) — the images may "
        "not be in S3 yet, so the cross-region sync will find nothing. Pass "
        "source_bucket explicitly if they are in a bucket.",
        indent=2,
    )
    return (resolve_oid_target_bucket(cfg, secured_mode=False)
            or cfg.get("aws.s3_bucket_panos_unsecured") or cfg.get("aws.s3_bucket"))


def _ensure_bucket(s3, bucket: str, region: str, logger, dry_run: bool) -> str:
    """Create ``bucket`` in ``region`` if absent. us-east-1 must NOT pass a
    LocationConstraint (an AWS quirk); every other region must."""
    try:
        s3.head_bucket(Bucket=bucket)
        logger.info(f"Test bucket already exists: {bucket}", indent=2)
        return "exists"
    except Exception as e:
        # Only a genuine "not found" means create. A 403 (exists but owned by
        # another account / no permission) or a network error must not fall
        # through to create_bucket.
        code = str(getattr(e, "response", {}).get("Error", {}).get("Code", ""))
        if code not in ("404", "NoSuchBucket", "NotFound"):
            msg = f"Cannot access test bucket '{bucket}' ({code or type(e).__name__}): {e}"
            if dry_run:
                logger.warning(f"[DRY RUN] {msg}", indent=2)
                return "inaccessible"
            raise RuntimeError(msg) from e
    if dry_run:
        logger.info(f"[DRY RUN] Would create bucket '{bucket}' in {region}.", indent=2)
        return "would_create"
    if region == "us-east-1":
        s3.create_bucket(Bucket=bucket)
    else:
        s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": region})
    logger.success(f"Created bucket '{bucket}' in {region}.", indent=2)
    return "created"


def _subset_oid(source_oid_fc: str, test_oid_fc: str, test_count: int, selection: str,
                logger, dry_run: bool):
    """Pick ``test_count`` rows ("first" or evenly "spaced") and, unless dry-run,
    build ``test_oid_fc`` as a copy reduced to those rows. Returns
    (built_oid_or_None, items) where items is a list of (filename, src_key)."""
    rows: List = []
    with arcpy.da.SearchCursor(source_oid_fc, ["OID@", "ImagePath"]) as cur:
        for oid, ip in cur:
            fn = extract_filename_from_image_path(ip)
            if fn:
                rows.append((oid, fn, _extract_object_key(ip)))
    total = len(rows)
    if total == 0:
        raise RuntimeError("Source OID has no usable ImagePath rows.")

    if test_count >= total:
        kept = rows
    elif selection == "first":
        kept = rows[:test_count]
    else:  # evenly spaced
        stride = max(1, total // test_count)
        kept = rows[::stride][:test_count]

    keep_oids = {r[0] for r in kept}
    items = [(r[1], r[2]) for r in kept]  # (filename, src_key)
    logger.info(f"Test set: {len(kept)} of {total} rows ({selection}).", indent=2)

    if dry_run:
        logger.info(f"[DRY RUN] Would build test OID: {test_oid_fc}", indent=2)
        return None, items

    if arcpy.Exists(test_oid_fc):
        arcpy.management.Delete(test_oid_fc)
    arcpy.management.Copy(source_oid_fc, test_oid_fc)
    with arcpy.da.UpdateCursor(test_oid_fc, ["OID@"]) as cur:
        for row in cur:
            if row[0] not in keep_oids:
                cur.deleteRow()
    logger.success(f"Built test OID ({len(kept)} rows): {test_oid_fc}", indent=2)
    return test_oid_fc, items


def _sync_keys(session, source_bucket: str, dest_bucket: str, dest_region: str,
               key_prefix: str, items: List, logger, dry_run: bool,
               skip_existing: bool = True) -> Dict:
    """Server-side copy only the subset's objects from ``source_bucket`` to
    ``dest_bucket``, preserving each object's KEY. Uses the key embedded in the
    source ImagePath when available (robust to prefix), else ``{prefix}/{filename}``.
    Cross-region is handled by S3."""
    dst = session.client("s3", region_name=dest_region)
    copied = skipped = failed = nokey = 0
    failures: List = []
    for filename, src_key in items:
        key = src_key or (f"{key_prefix}/{filename}" if key_prefix else filename)
        if not key:
            nokey += 1
            continue
        try:
            if skip_existing and not dry_run:
                try:
                    dst.head_object(Bucket=dest_bucket, Key=key)
                    skipped += 1
                    continue
                except Exception:
                    pass  # absent -> copy
            if dry_run:
                copied += 1
                continue
            dst.copy_object(Bucket=dest_bucket, Key=key,
                            CopySource={"Bucket": source_bucket, "Key": key})
            copied += 1
        except Exception as ex:  # noqa: BLE001 - report per-key, keep going
            failed += 1
            failures.append((key, str(ex)))
            logger.warning(f"Copy failed for {key}: {ex}", indent=3)
    verb = "would copy" if dry_run else "copied"
    logger.info(f"Sync: {verb} {copied}, skipped {skipped}, failed {failed}, no-key {nokey} (of {len(items)}).", indent=2)
    if nokey:
        logger.warning(f"{nokey} row(s) had no resolvable S3 key (local ImagePath?) and were not synced.", indent=3)
    return {"copied": copied, "skipped": skipped, "failed": failed, "no_key": nokey, "failures": failures}


def _rewrite_secured(test_oid_fc: str, key_prefix: str, logger) -> int:
    """Rewrite the test OID's ImagePaths to secured ($virtualCacheDirectory) form
    using the same prefix as the synced keys. Region/bucket-agnostic — the binding
    happens at publish via the registered cloud store."""
    changed = 0
    sample = None
    with arcpy.da.UpdateCursor(test_oid_fc, ["ImagePath"]) as cur:
        for row in cur:
            key = _extract_object_key(row[0])
            if key is None:  # local path -> fall back to prefix/filename
                fn = extract_filename_from_image_path(row[0])
                if not fn:
                    continue
                key = f"{key_prefix}/{fn}" if key_prefix else fn
            new = f"{SECURED_IMAGE_PATH_PREFIX}{key}"
            if new != row[0]:
                row[0] = new
                cur.updateRow(row)
                changed += 1
                sample = sample or new
    logger.info(f"Rewrote {changed} ImagePath(s) to secured form. e.g. {sample or '(none)'}", indent=2)
    return changed


def _publish(cfg: ConfigManager, test_oid_fc: str, cloud_store_name: str,
             share_with: Optional[str], logger, dry_run: bool) -> Optional[str]:
    """Publish the test OID bound to the registered cloud store. Mirrors
    generate_oid_service's publish call, but with the test cloud store."""
    from utils.generate_oid_service import assemble_service_metadata, ensure_portal_folder

    oid_name = os.path.splitext(os.path.basename(test_oid_fc))[0]
    service_name, portal_folder, share_default, add_footprint, tags_str, summary = assemble_service_metadata(cfg, oid_name)
    share = share_with or share_default

    if dry_run:
        logger.info(f"[DRY RUN] Would publish '{service_name}' bound to cloud store '{cloud_store_name}'.", indent=2)
        return service_name

    try:
        from arcgis.gis import GIS
        gis = GIS("pro")
        ensure_portal_folder(gis, portal_folder, logger)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Portal folder check failed: {e}", indent=2)

    arcpy.oi.GenerateServiceFromOrientedImageryDataset(
        in_oriented_imagery_dataset=test_oid_fc,
        service_name=service_name,
        portal_folder=portal_folder,
        share_with=share,
        add_footprint=add_footprint,
        attach_images="NO_ATTACH",
        tags=tags_str,
        summary=summary,
        virtual_cache_directory=cloud_store_name,
    )
    logger.success(f"Published secured test service '{service_name}' (cloud store: {cloud_store_name}).", indent=2)
    return service_name


def deploy_secured_test_set(
    cfg: ConfigManager,
    source_oid_fc: str,
    *,
    test_bucket: str,
    test_region: str = "us-east-1",
    key_prefix: Optional[str] = None,
    test_count: int = 100,
    selection: str = "spaced",          # "spaced" | "first"
    source_bucket: Optional[str] = None,
    create_bucket: bool = True,
    cloud_store_name: Optional[str] = None,
    publish: bool = False,
    share_with: Optional[str] = None,
    dry_run: bool = True,
) -> Dict:
    """Stage a small secured test set of ``source_oid_fc`` into ``test_bucket``/
    ``test_region`` and (optionally) publish it.

    Two-pass: run with publish=False to stage + get cloud-store registration
    values; register the cloud store in Enterprise; re-run with publish=True and
    cloud_store_name set. DRY RUN by default — flip dry_run=False to execute.
    """
    logger = cfg.get_logger()
    mode = "DRY RUN" if dry_run else "LIVE"
    logger.custom(f"Deploy Secured Test Set → {test_region} ({mode})", emoji="🧪", indent=1)

    if not test_bucket:
        raise ValueError("test_bucket is required.")
    if test_count < 1:
        raise ValueError(f"test_count must be at least 1 (got {test_count}).")
    key_prefix = (key_prefix or resolve_oid_key_prefix(cfg) or "").strip().strip("/")
    # Auto-detect the source bucket from the OID's ImagePath form (secured vs public)
    # unless explicitly overridden — so a us-east-2 SECURED OID resolves to the
    # secured bucket, not the unsecured default.
    if not source_bucket:
        source_bucket = _detect_source_bucket(cfg, source_oid_fc, logger)
    if not source_bucket:
        raise ValueError("Could not resolve a source bucket; pass source_bucket explicitly.")

    logger.info(
        f"Source: s3://{source_bucket} | Test: s3://{test_bucket} ({test_region}) | "
        f"prefix: {key_prefix or '(bucket root)'}",
        indent=2,
    )

    session = get_boto3_session(cfg)
    dst_client = session.client("s3", region_name=test_region)

    # 1) Ensure the target bucket exists.
    if create_bucket:
        _ensure_bucket(dst_client, test_bucket, test_region, logger, dry_run)
    else:
        try:
            dst_client.head_bucket(Bucket=test_bucket)
        except Exception:
            logger.warning(f"Test bucket '{test_bucket}' not reachable and create_bucket=False.", indent=2)

    # 2) Subset the OID.
    oid_gdb = os.path.dirname(source_oid_fc)
    oid_name = os.path.splitext(os.path.basename(source_oid_fc))[0]
    test_oid_fc = os.path.join(oid_gdb, f"{oid_name}_uetest")
    built_oid, items = _subset_oid(source_oid_fc, test_oid_fc, test_count, selection, logger, dry_run)

    # 3) Cross-region sync of ONLY the subset's keys (preserving the source key).
    sync = _sync_keys(session, source_bucket, test_bucket, test_region, key_prefix, items, logger, dry_run)

    # 4) Rewrite the test OID's ImagePaths to secured form (live only).
    rewritten = 0
    if built_oid and not dry_run:
        rewritten = _rewrite_secured(test_oid_fc, key_prefix, logger)

    # 5) Publish (requires a registered cloud store) — else emit registration values.
    published = None
    if publish:
        incomplete = sync["failed"] + sync["no_key"]
        if not cloud_store_name:
            logger.warning("publish=True but cloud_store_name not provided; skipping publish.", indent=2)
        elif incomplete and not dry_run:
            # Publishing now would reference images missing from the test bucket.
            logger.warning(
                f"Skipping publish: {incomplete} image(s) were not synced "
                f"(failed {sync['failed']}, no-key {sync['no_key']}). Fix and re-run.", indent=2
            )
        else:
            published = _publish(cfg, test_oid_fc, cloud_store_name, share_with, logger, dry_run)
    else:
        logger.custom("Next (manual, in ArcGIS Enterprise): register a cloud store, then re-run with publish=True.", emoji="📋", indent=1)
        logger.info(f"  Cloud store → S3 bucket : {test_bucket}", indent=2)
        logger.info(f"  Region                  : {test_region}", indent=2)
        logger.info(f"  Root / object prefix    : {key_prefix or '(bucket root)'}", indent=2)
        logger.info("  Re-run with: publish=True, cloud_store_name='<registered name>', dry_run=False", indent=2)

    return {
        "test_oid_fc": test_oid_fc,
        "test_bucket": test_bucket,
        "test_region": test_region,
        "key_prefix": key_prefix,
        "source_bucket": source_bucket,
        "image_count": len(items),
        "sync": sync,
        "rewritten_paths": rewritten,
        "published_service": published,
        "dry_run": dry_run,
    }
