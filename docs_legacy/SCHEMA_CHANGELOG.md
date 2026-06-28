
# 📄 SCHEMA_CHANGELOG.md

This changelog tracks structural changes to the Oriented Imagery Dataset (OID) schema, the `config.yaml` layout, and the field registry.

---

## [1.4.0] - 2026-06-28

### Changed (BREAKING — clean break, no backward compatibility)

- Consolidated the `aws` and `secured_storage` sections into a single `aws` block.
  The two sections duplicated `region` and `s3_bucket_folder` and split the three
  buckets confusingly. New layout:
  - `aws.s3_bucket` → `aws.s3_bucket_panos_unsecured`
  - `secured_storage.s3_bucket` → `aws.s3_bucket_panos_secured`
  - `aws.s3_bucket_raw` (unchanged) — reels/raw + artifact backups
  - `secured_storage.enabled` → `aws.secured_delivery.enabled`
  - `secured_storage.cloud_store_name` → `aws.secured_delivery.cloud_store_name`
  - `secured_storage.region` / `secured_storage.s3_bucket_folder` → **removed**
    (use the single `aws.region` / `aws.s3_bucket_folder`)
- Added optional per-bucket region overrides: `aws.s3_bucket_panos_unsecured_region`,
  `aws.s3_bucket_panos_secured_region` (null → use `aws.region`).
- Removed the deprecated `aws.keyring_aws` flag (auth_mode is the single switch).
- Runtime accepts **only** `1.4.0`. Older configs are rejected at load — upgrade them
  with the config editor (its Upgrade applies the renames automatically).

## [1.3.5] - 2026-06-28

### Added

- `custom_fields` entries may now be populated from the corridor manifest via a
  `manifest_field` key (joined by image Name), with an optional `default`. Used for
  per-image values the pipeline does not otherwise derive — e.g. parallel `track`.
  Added a sample `custom2: Track` field. Populated by `add_images_to_oid_fc.py`.
- `linear_ref_fields` (`route_identifier`, `route_measure`) accept a `manifest_field`
  key so MP_Pre / MP_Num can come from the manifest in pre-thin mode. MP_Pre always
  uses the manifest's intended subdivision (`mp_pre`), which prevents nearest-route
  snapping to the wrong parallel subdivision.
- `corridor_thinning.manifest.mp_num_source` (`"relocate"` | `"manifest"`, default
  `"relocate"`): `relocate` re-runs linear referencing constrained to the intended
  subdivision; `manifest` copies `mp_meas` directly.

### Changed

- `config.sample.yaml` now declares schema version `1.3.5`.
- Runtime accepts `1.3.1`–`1.3.5` for backward compatibility. All additions are
  optional and gated on the new keys, so existing configs behave unchanged.

## [1.3.3] - 2026-05-30

### Added (1.3.2)

- Added `sequence_order` config block for optional SequenceOrder population.
- Added `secured_storage` config block for virtual cache ImagePath mode.

### Changed (1.3.2)

- `config.sample.yaml` now declares schema version `1.3.3`.
- Runtime accepts `1.3.1`, `1.3.2`, and `1.3.3` for backward compatibility.

## [1.3.2] - 2026-05-30

### Added

- Added optional `gps_smoothing.segment_break_distance_m`.
- Added optional `gps_smoothing.segment_break_time_seconds`.
- GPS smoothing/correction can now split a single reel into multiple capture segments when there is a large location or time gap.

### Changed

- `config.sample.yaml` now declares schema version `1.3.2`.
- Runtime continues accepting `1.3.1` configs for backward compatibility.

## [1.0.0] – 2025-05-08

### ✅ Added

- Introduced structured `oid_schema_template` block in `config.yaml`.
- Added support for field groups:
  - `mosaic_fields` (e.g., Reel, Frame)
  - `grp_idx_fields` (e.g., GroupIndex)
  - `linear_ref_fields` (e.g., MP_Pre, MP_Num)
  - `custom_fields` (e.g., RR from project.rr_mark)
- Created `esri_oid_fields_registry.yaml` for required and optional ESRI fields with schema enforcement.
- Added support for
  - `oid_default` values in registry
  - `expression` logic in `custom_fields`
- All field creation now driven by config, not hardcoded logic.
- Schema template output can be reused across projects.

### 📁 New `config.yaml` Top-Level Keys (in order)

- `schema_version`
- `logs`
- `project`
- `camera`
- `camera_offset`
- `spatial_ref`
- `executables`
- `oid_schema_template`
- `gps_smoothing`
- `image_output`
- `aws`
- `portal`
- `geocoding`
- `image_enhancement`
- `orchestrator`

Each key corresponds to one or more steps in the workflow and is validated before execution.

### ✏️ Changed

- Previously hardcoded fields like `RR`, `MP_Num`, `GroupIndex` now fully config-defined.
- `CameraHeight` is now calculated from a detailed breakdown under `camera_offset`.
- Filename format and metadata tags now use `resolve_expression()` for dynamic control.

### ❌ Removed

- Hardcoded OID schema construction from tools.
- Deprecated legacy `camera_calculations` and `field_list` structures.

---

## 🗂 Notes

- Templates are built using `build_oid_schema.py`.
- Validation is performed by `validate_config.py` and `schema_validator.py`.
- Tools that consume schemas: `create_oid_feature_class.py`, `create_oid_template_tool.py`.
