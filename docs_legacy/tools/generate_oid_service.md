# Tool: Generate OID Service

## Tool Name
Generate OID Service

## Purpose
Publishes an Oriented Imagery Dataset using ArcGIS Pro's oriented imagery service tool.

Before publish, the tool copies the input OID and rewrites `ImagePath` based on delivery mode:
- Legacy mode (`secured_storage.enabled: false`): public S3 URL
- Secured mode (`secured_storage.enabled: true`): `$virtualCacheDirectory:<key>`

Object keys are generated using the same shared helper used by `copy_to_aws`, preventing drift between uploaded keys and ImagePath values.

## Inputs
- OID feature class
- Config values from `portal`, `aws`, and optional `secured_storage`

## Outputs
- Duplicated OID feature class with rewritten `ImagePath`
- Published portal service item

## Runtime Behavior
1. Validates config (`generate_oid_service` validator).
2. Resolves delivery mode (`legacy` or `secured`).
3. Copies input OID to an `_aws` variant.
4. Rewrites `ImagePath` in copied OID:
   - Legacy: `https://<bucket>.s3.<region>.amazonaws.com/<object_key>`
   - Secured: `$virtualCacheDirectory:<object_key>`
5. Publishes via `arcpy.oi.GenerateServiceFromOrientedImageryDataset` with configured portal options.

## Configuration
```yaml
portal:
  project_folder: "config.project.number"
  share_with: "PRIVATE"
  add_footprint: "FOOTPRINT"
  portal_tags:
    - "config.project.number"
    - "Oriented Imagery"
  summary: "'Oriented Imagery for ' + config.project.number"

aws:
  s3_bucket: "<YOUR_S3_BUCKET_NAME>"
  region: "<YOUR_AWS_S3_REGION>"
  s3_bucket_folder: "config.project.slug"

secured_storage:
  enabled: false
  cloud_store_name: "<CLOUD_STORE_NAME>"
  s3_bucket: "<YOUR_SECURED_S3_BUCKET_NAME>"
  region: "<YOUR_AWS_S3_REGION>"
  s3_bucket_folder: "config.project.slug"
```

## Validation
Validator: `utils/validators/generate_oid_service_validator.py`

Checks include:
- Portal config structure (`project_folder`, tags, summary)
- AWS folder expression resolves
- If secured mode is enabled, validates secured storage bucket/region/folder settings

## Notes
- This tool does not upload images. Run Copy to AWS first.
- Secured mode requires matching cloud store setup in ArcGIS Enterprise publish workflow.
- The tool only writes ImagePath strings; cloud-store binding itself is selected in ArcGIS Pro publish UI.
