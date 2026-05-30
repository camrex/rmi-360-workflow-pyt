# Tool: Copy to AWS

## Tool Name
09 - Copy To AWS

## Purpose
Uploads final image files from the renamed image folder to S3.

The destination bucket and key model now depend on secured storage mode:
- Legacy mode (`secured_storage.enabled: false`): uploads to `aws.s3_bucket`
- Secured mode (`secured_storage.enabled: true`): uploads to `secured_storage.s3_bucket`

Both modes use the same object key builder used by OID ImagePath generation, so upload keys and ImagePath targets stay aligned.

## Inputs
- Renamed image folder (normally `paths.renamed`)
- Config values from `aws` and optional `secured_storage`

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
  s3_bucket: "<YOUR_S3_BUCKET_NAME>"
  s3_bucket_folder: "config.project.slug"
  skip_existing: true
  max_workers: 16
  retries: 3
  upload_batch_size: 25
  allow_cancel_file_trigger: true
  use_acceleration: true

secured_storage:
  enabled: false
  s3_bucket: "<YOUR_SECURED_S3_BUCKET_NAME>"
  region: "<YOUR_AWS_S3_REGION>"
  s3_bucket_folder: "config.project.slug"
```

## Validation
Validator: `utils/validators/copy_to_aws_validator.py`

Checks include:
- Required `aws` keys (`region`, `s3_bucket`, `s3_bucket_folder`)
- `auth_mode` value (`instance`, `keyring`, `config`)
- Worker/retry setting types
- Resolved bucket folder expression
- If secured mode is enabled, validates `secured_storage.s3_bucket`, `region`, and `s3_bucket_folder`

## Notes
- Upload can be canceled by ArcGIS cancel event, and optionally by `cancel_copy.txt`.
- If Transfer Acceleration is requested but bucket acceleration is not enabled, upload falls back to standard endpoint.
- In secured mode, upload bucket switches with the same flag used for ImagePath mode.
