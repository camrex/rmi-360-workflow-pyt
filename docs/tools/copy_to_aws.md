# ☁️ Tool: Copy to AWS (+ Set AWS Keyring Credentials)

## 🧰 Tool Name
**09 – Copy To AWS**  
**(includes: Set AWS Keyring Credentials)**

---

## 🧭 Purpose

This tool uploads **final, renamed, and metadata-tagged images** to an AWS S3 bucket using multithreaded parallel uploads. It supports:

- Pulling credentials from system keyring or `config.yaml`
- Uploading only new or updated files
- Logging upload results
- Preview-only dry run mode
- Flexible project-level path resolution

This workflow also includes the **Set AWS Keyring Credentials** tool, which securely stores AWS credentials for use by the Copy to AWS process.

---

## 🔧 Parameters

### Copy To AWS

| Parameter | Required | Description |
|----------|----------|-------------|
| `Input Folder for Images` | ✅ | Folder containing the `.jpg` images to upload |
| `Dry Run AWS` | ⬜️ | If checked, performs a no-op simulation of the upload |
| `Skip Existing Files in S3?` | ⬜️ | If checked, skips already existing images in the bucket |
| `Config File` | ✅ | Path to the project’s `config.yaml` |
| `Project Folder` | ✅ | Project root used for resolving relative paths |

### Set AWS Keyring Credentials

| Parameter | Required | Description |
|----------|----------|-------------|
| `AWS Access Key ID` | ✅ | Your AWS access key ID |
| `AWS Secret Access Key` | ✅ | Your AWS secret key (stored securely) |

---

## 🧩 Script Components

| Script | Role |
|--------|------|
| `copy_to_aws_tool.py` | Toolbox wrapper for AWS upload |
| `copy_to_aws.py` | Handles upload logic, retry, logging |
| `set_aws_keyring_tool.py` | Secure credential entry and keyring storage |
| `validate_config.py` | Verifies AWS config block for correctness |

---

## 🔐 Credential Handling

Configured in `config.yaml → aws`:

```yaml
aws:
  keyring_aws: true
  keyring_service_name: rmi_s3
  access_key: "..."       # Only used if keyring_aws = false
  secret_key: "..."
```

- When `keyring_aws: true`, credentials are securely stored using the keyring.
- Use **Set AWS Keyring Credentials** before uploading.
- If `keyring_aws: false`, the tool falls back to config-stored credentials.

---

## 📤 Output

| Output | Description |
|--------|-------------|
| `aws_upload_log.csv` | Log of all files uploaded / skipped / failed |
| `ArcGIS Progress Bar` | Live progress updates or CLI logging |
| `S3 Folder` | Files uploaded to: `s3://bucket/project_slug/...` structure |

Example config snippet:
```yaml
aws:
  s3_bucket: rmi-orient-img-test
  s3_bucket_folder: "config.project.slug"
```

---

## ✅ Validation

Run via `validate_tool_copy_to_aws()`

- Confirms presence of: `region`, `s3_bucket`, `s3_bucket_folder`
- Verifies credentials are resolvable via keyring or config
- Validates all optional parameters (`retries`, `max_workers`, etc.)
- Ensures upload folder is resolvable

---

## 📝 Notes

- 🛠 Run this **after `Rename and Tag Images`** is complete
- ✅ Safe to re-run with `skip_existing = true`
- 🧵 Multithreaded: Uploads use 5 threads by default
- 🔐 Keyring storage is cross-platform secure via the OS’s credential manager
