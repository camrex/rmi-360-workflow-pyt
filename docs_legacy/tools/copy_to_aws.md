# Tool: Copy to AWS

## Tool Name

09 - Copy To AWS

## Purpose

Uploads final image files from the renamed image folder to S3.

The destination bucket and key model now depend on secured storage mode:

- Legacy mode (`aws.secured_delivery.enabled: false`): uploads to `aws.s3_bucket_panos_unsecured`
- Secured mode (`aws.secured_delivery.enabled: true`): uploads to `aws.s3_bucket_panos_secured`

Both modes use the same object key builder used by OID ImagePath generation, so upload keys and ImagePath targets stay aligned.

## Inputs

- Renamed image folder (normally `paths.renamed`)
- Config values from `aws` (including the `aws.secured_delivery` sub-block)

## Outputs

- Uploaded images in target S3 bucket
- Upload log CSV (`aws_upload_log`)
- Upload summary CSV (`aws_upload_summary`)

## Runtime Behavior

1. Validates config (`copy_to_aws` validator).
2. Resolves delivery mode (`legacy` or `secured`).
3. Resolves target bucket and key prefix from config.
4. Builds upload tasks with shared OID key helper.
5. Uploads in batches using TransferManager.
6. Tracks uploaded, failed, skipped and writes detailed logs.

## Configuration

```yaml
aws:
  region: "<YOUR_AWS_S3_REGION>"
  auth_mode: "instance"
  s3_bucket_folder: "config.project.slug"
  s3_bucket_raw: "<YOUR_S3_RAW_BUCKET_NAME>"
  s3_bucket_panos_unsecured: "<YOUR_S3_BUCKET_NAME>"
  s3_bucket_panos_secured: "<YOUR_SECURED_S3_BUCKET_NAME>"
  s3_bucket_panos_unsecured_region: null   # optional override; null -> aws.region
  s3_bucket_panos_secured_region: null     # optional override; null -> aws.region
  secured_delivery:
    enabled: false
    cloud_store_name: "<CLOUD_STORE_NAME>"
  skip_existing: true
  max_workers: 16
  retries: 3
  upload_batch_size: 25
  allow_cancel_file_trigger: true
  use_acceleration: true
```

## Validation

Validator: `utils/validators/copy_to_aws_validator.py`

Checks include:

- Required `aws` keys (`region`, `s3_bucket_panos_unsecured`, `s3_bucket_folder`)
- `auth_mode` value (`instance`, `keyring`, `config`)
- Worker/retry setting types
- Resolved bucket folder expression
- If secured mode is enabled, validates `aws.s3_bucket_panos_secured` and `aws.secured_delivery.cloud_store_name`

## Notes

- Upload can be canceled by ArcGIS cancel event, and optionally by `cancel_copy.txt`.
- If Transfer Acceleration is requested but bucket acceleration is not enabled, upload falls back to standard endpoint.
- In secured mode, upload bucket switches with the same flag used for ImagePath mode.
