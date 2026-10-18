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
- [ ] Config editor: extend `@when[...]` conditional-field disabling to other natural cases (e.g. `geocoding.geoloc500_config_path`/`geocustom_config_path` gated on `geocoding.exiftool_geodb`). Mechanism already built and applied to `aws.secured_delivery.enabled`; remaining cases just need the annotations.
- [ ] Config editor: surface bucket-existence results inline per field (the AWS check reports them in a modal today).
- [ ] Secured delivery (`aws.secured_delivery`) is **not an option until ArcGIS Enterprise 12.2 at the earliest** (we run 12.1). Esri Case #04187998 concluded 2026-10 that the serving failure is on the Enterprise side. Keep `aws.secured_delivery.enabled: false`. The 2026 AWS test setup was removed 2026-10-16 (rmi-aws-infra change record 0014: buckets `rmi-oid-corridor-imagery` and `-e1`, IAM user `svc-arcgis-oid-imagery-reader`, its policy), and the ArcGIS cloud-store registrations were removed in the portal. Revisit after a 12.2+ upgrade; turning it back on needs that setup rebuilt, through rmi-aws-infra.
- [ ] OID Maintenance (deferred until Enterprise 12.2+): replace the secured-mode reachability check (currently a bucket key-existence proxy) with a true end-to-end serve check, and wire the orchestrator's optional auto-publish.
