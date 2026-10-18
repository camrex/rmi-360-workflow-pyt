# ✅ TODO – RMI 360 Imaging Workflow Python Toolbox v1.1.0 and Beyond

- [x] Add sphinx documentation ✨ **COMPLETED**: Full Sphinx documentation system implemented with ReadTheDocs theme, API reference, and GitHub Pages deployment
- [ ] Clean-up unit tests
- [ ] Add support for Insta360 workflow
  - CLI conversion of INSP images to JPG
  - Georeferencing of JPG images
  - Calculation of Heading
- [ ] Remove dependency on `EXIFTOOL` for metadata updates (Handle using Python)
- [ ] Fix `enhance_images` to not expose seam line
- [ ] Monitor validator `ConfigManager` type-only import refactor; revert this change set if fatal runtime import/circular-reference behavior is observed.
- [ ] Config editor: extend `@when[...]` conditional-field disabling to other natural cases (e.g. `geocoding.geoloc500_config_path`/`geocustom_config_path` gated on `geocoding.exiftool_geodb`). Mechanism already built and applied to `aws.auth_mode` / `aws.secured_delivery.enabled`; remaining cases just need the annotations.
- [ ] Config editor: consider blocking/greying credential entry per `auth_mode` (e.g. hide `access_key`/`secret_key` unless `config`) beyond the current `@when` display rule, and surface bucket-existence results inline per field.
- [ ] Upload monitor: its AWS resources were removed 2026-10-16 (rmi-aws-infra change record 0017; see `docs/aws/lambda-monitoring.rst`). Either default *Copy To AWS* "Deploy Upload Monitor?" to false (`tools/copy_to_aws_tool.py`, `enable_monitor.value`) or retire the monitor code (`utils/deploy_lambda_monitor.py`, `aws_lambdas/`). Until then, untick it when running the tool.
- [ ] Secured delivery (`aws.secured_delivery`) is **not an option until ArcGIS Enterprise 12.2 at the earliest** (we run 12.1). Esri Case #04187998 concluded 2026-10 that the serving failure is on the Enterprise side. Keep `aws.secured_delivery.enabled: false`. The 2026 AWS test setup was removed 2026-10-16 (rmi-aws-infra change record 0014: buckets `rmi-oid-corridor-imagery` and `-e1`, IAM user `svc-arcgis-oid-imagery-reader`, its policy), and the ArcGIS cloud-store registrations were removed in the portal. Revisit after a 12.2+ upgrade; turning it back on needs that setup rebuilt, through rmi-aws-infra.
- [ ] OID Maintenance (deferred until Enterprise 12.2+): replace the secured-mode reachability check (currently a bucket key-existence proxy) with a true end-to-end serve check, and wire the orchestrator's optional auto-publish.
