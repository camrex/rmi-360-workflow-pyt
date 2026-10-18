# CLAUDE.md

Guidance for Claude Code (and anyone) working in this repository.

ArcGIS Pro Python toolboxes for RMI's 360° rail-corridor imagery: Mosaic 51 capture →
Oriented Imagery Dataset (OID) → S3 upload → hosted service. The toolboxes are
`rmi_360_workflow.pyt` (main pipeline + orchestrator), `rmi_360_oid_maintenance.pyt`,
`rmi_360_corridor_thinning.pyt` and `rmi_360_env_checker.pyt`. Logic lives in `utils/`;
`tools/` holds thin ArcGIS tool wrappers. `config_editor/` is a separate standalone app.

## AWS: profile only

- **Every AWS call uses the named profile `rmi-360-workflow-pyt`** (IAM Identity Center,
  issued by rmi-aws-infra change 0049). Projects set it as `aws.profile` in
  `config.yaml`; blank falls back to `AWS_PROFILE`. With neither, or with `default`, the
  code refuses (`utils/shared/aws_utils.py`). Never add a path that falls back to boto3's
  default chain, a keyring, or keys in config.
- Sign in before a run: `aws sso login --profile rmi-360-workflow-pyt`.
- What the profile can do: list `rmi-360-prod` and `rmi-360-raw`; put `.jpg`/`.jpeg`
  under `rmi-360-prod/RMI*/`; read and put under `rmi-360-raw/RMI*/` and
  `rmi-360-raw/status/RMI*/`. **No delete, Lambda, EventBridge or IAM.** Slugs start
  with `RMI`. The full setup is in `docs/aws/setup-guide.rst`.
- **Never overwrite in `rmi-360-prod`**: a repeat put of a panorama re-runs tiling.
  `copy_to_aws` checks each key with `HeadObject` first and skips existing keys.
- Infrastructure changes (grants, buckets, lifecycle) belong to `E:\DevProjects\rmi-aws-infra`:
  write a request there rather than calling AWS to change anything.
- When working in this repo, make no AWS calls unless the operator asks, and never with
  any credential other than this profile.

## Decisions that constrain changes

- **Secured storage stays off** (`aws.secured_delivery.enabled: false`) until ArcGIS
  Enterprise 12.2+ (Esri case 04187998 concluded). Don't build secured-delivery features.
- **The upload monitor is being redesigned as a heartbeat**, not a Lambda: `copy_to_aws`
  writes status through `utils/shared/s3_status_tracker.StatusTracker` to
  `rmi-360-raw/status/{slug}/`. Don't redeploy or extend `deploy_lambda_monitor` /
  `aws_lambdas/`; they are to be removed.
- Processing runs on a dedicated Windows machine, not in AWS.

## Config schema

- `configs/config.sample.yaml` is the single source of truth for the schema; the config
  editor builds its form from it (annotation tags are documented in its header).
- `SUPPORTED_SCHEMA_VERSIONS` in `utils/manager/config_manager.py` is a clean break: the
  runtime loads only the current version. When keys are added, removed or renamed, bump
  it, bump the sample's `schema_version`, add rules to `config_editor/core/migrations.py`,
  and update the editor tests that hard-code the version.
- Users upgrade old configs with the config editor's **Upgrade**. It keeps keys that are
  not in the new schema (it lists them as "removed" but leaves them); delete those by hand.

## Tests

- The toolbox suite needs ArcGIS Pro's Python and must be run **one file at a time**:
  the files install conflicting stub modules, so a whole-suite run reports false
  failures. Some failures predate current work; compare against `main` before
  treating a failure as new.

  ```bash
  PRO="/c/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe"
  AWS_CONFIG_FILE=NUL AWS_SHARED_CREDENTIALS_FILE=NUL AWS_EC2_METADATA_DISABLED=true \
    "$PRO" -m pytest tests/test_aws_utils.py -q -p no:cacheprovider --basetemp <scratch dir>
  ```

  The `AWS_*` settings keep a test from ever reaching AWS. `--basetemp` avoids a
  WinError 5 on the default temp dir.
- Config editor: `config_editor/.venv/Scripts/python -m pytest config_editor/tests -q`
  (its venv is built from `config_editor/requirements.txt`; standalone Python 3.10+).
- ArcGIS Pro caches imported modules: restart Pro to pick up code changes.

## Conventions

- Every PR updates `CHANGELOG.md` under `[Unreleased]`.
- Gitignored runtime files live only in the working copy: `templates/templates.gdb`,
  `templates/exiftool/Geolocation500`, `templates/assets/rmi_logo.png`, `private/`, the
  built editor exe. Keep them backed up.
