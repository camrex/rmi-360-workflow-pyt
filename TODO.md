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
- [ ] OID Maintenance: replace the secured-mode reachability check (currently a bucket key-existence proxy) with a true end-to-end serve check, and wire the orchestrator's optional auto-publish, once Esri Case #04187998 resolves.
