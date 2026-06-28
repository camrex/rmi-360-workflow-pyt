# Toolbox: OID Maintenance (`rmi_360_oid_maintenance.pyt`)

## Purpose

Out-of-band maintenance and diagnostics for an **already-published** OID, kept
separate from the linear pipeline in `rmi_360_workflow.pyt` (same rationale as the
corridor-thinning toolbox: interactive, technician-operated, not part of the
unattended orchestrator).

Primary use case: move panoramas between the unsecured public S3 bucket
(`aws.s3_bucket_panos_unsecured`) and the secured bucket (`aws.s3_bucket_panos_secured`), and migrate
`ImagePath` values in either direction, while secured-storage serving is verified
with Esri (Case #04187998).

> All mutating tools default to **Dry Run**. Re-publishing the hosted service is
> NOT done here — use **Generate OID Service** (main workflow) against the migrated
> `*_secured` / `*_legacy` OID copy, which is already mode-aware via
> `aws.secured_delivery.enabled`.

## Why a migration is cheap

The object **key layout is identical** across delivery modes
(`{prefix}/{filename}`, prefix = `project.slug` by default). So a migration is a
key-for-key bucket copy plus an `ImagePath` rewrite — no re-upload from the local
machine, no re-processing of imagery. The two `ImagePath` forms are defined in
exactly one place (`utils/shared/oid_storage_paths.py::build_oid_image_path_for_mode`),
shared by both publishing and migration.

## Registered Tools

### Storage Migration

| # | Tool | Concern | Mutates? |
| --- | ------ | --------- | ---------- |
| 01 | Rewrite OID ImagePaths | `ImagePath` form (legacy ↔ secured) | OID rows (in place) |
| 02 | Sync OID S3 Objects | Object location (bucket → bucket) | Destination bucket |
| 10 | Migrate OID Storage (orchestrator) | sync → rewrite copy → audit | Bucket + an OID copy |

### Diagnostics

| # | Tool | Purpose | Mutates? |
| ---- | ------ | --------- | ---------- |
| 20 | Validate ImagePath Reachability | Probe that sampled ImagePaths resolve | No (read-only) |
| 21 | Audit OID vs S3 | Reconcile OID keys against bucket keys | No (read-only) |

## Tool detail

### 01 — Rewrite OID ImagePaths

Rewrites every `ImagePath` into the chosen form, recovering each filename from
whatever form the row currently holds (handles `$virtualCacheDirectory:`, full S3
URLs, presigned query strings, bare keys). Idempotent. Mutates the feature class in
place — point it at a copy if you need the source kept.

- Inputs: OID feature class, target mode (`secured` | `legacy`), project folder,
  optional config, dry-run flag.

### 02 — Sync OID S3 Objects

Server-side `copy_object` of every key under the project prefix from source to
destination bucket, key-for-key. `skip_existing` HEADs the destination first.

- Inputs: direction (`legacy_to_secured` | `secured_to_legacy`), optional prefix
  override, skip-existing flag, project folder, optional config, dry-run flag.
- Note: for cross-account buckets, ensure the configured AWS session can write to
  the destination.

### 10 — Migrate OID Storage (orchestrator)

Chains the three migration concerns for one OID in either direction:

1. Sync image objects to the destination bucket.
2. Copy the OID to `{name}_secured` / `{name}_legacy` and rewrite ImagePaths on the
   copy (source kept pristine, mirroring `generate_oid_service`'s `_aws` pattern).
3. Audit the rewritten copy against the destination bucket.

Does **not** republish. On completion it points you at the copy to publish with
Generate OID Service.

### 20 — Validate ImagePath Reachability

Samples up to N rows and probes each `ImagePath`:

- Legacy/public rows: HTTP HEAD the URL (falls back to GET on 405), expect 2xx.
- Secured rows: **TODO(esri-04187998)** a true end-to-end serve check is not yet
  possible; as a conservative proxy this confirms the underlying object key exists
  in `aws.s3_bucket_panos_secured`. This catches "bytes never landed in the secured
  bucket" but NOT "Enterprise cannot serve from the cloud store."

### 21 — Audit OID vs S3

Reconciles the keys implied by each `ImagePath` against the keys present in the
delivery bucket. Reports rows missing from the bucket and orphaned bucket objects.
The natural before/after check around a migration.

## Interim strategy (while Esri Case #04187998 is open)

Keep the secured bucket private and untouched; run in **legacy mode**
(`aws.secured_delivery.enabled: false`) against the public `aws.s3_bucket_panos_unsecured`. When Esri
resolves the case:

1. The single `aws.s3_bucket_folder` prefix expression (default `config.project.slug`)
   is shared by both buckets, so keys line up across the migration.
2. Run **02 — Sync OID S3 Objects** (`legacy_to_secured`) to copy keys.
3. Set `aws.secured_delivery.enabled: true`.
4. Run **Generate OID Service** to republish with `$virtualCacheDirectory:` paths —
   or use **10 — Migrate OID Storage** to stage the copy, then publish it.

Existing public-URL services keep working off the public bucket until you choose to
re-point them, so migration can be incremental and is reversible
(`secured_to_legacy`) as a rollback.

## Core Utils

- `utils/shared/oid_storage_migration.py` — all migration/diagnostic primitives.
- `utils/shared/oid_storage_paths.py` — single source of truth for ImagePath forms
  and key layout.
- `utils/shared/aws_utils.py` — validated boto3 session / bucket access.

## Tests

- `tests/test_oid_storage_migration.py` — covers rewrite (apply / dry-run /
  idempotent / unparseable), sync (dry-run / copy + skip-existing), audit, and both
  reachability paths. arcpy cursors and all S3 access are faked via module seams.

## Notes

- All mutating tools default to Dry Run.
- Service (re)publishing routes through Generate OID Service in the main workflow.
- Scaffold status: tool versions are `0.1.0`; the secured reachability check and the
  orchestrator's optional auto-publish are intentionally left as marked TODOs until
  Esri Case #04187998 resolves.
