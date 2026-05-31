# Security Notes

## Pillow In ArcGIS Pro Bundled Python

This project is designed to run in the ArcGIS Pro bundled Python environment.
As noted in [requirements.txt](requirements.txt), dependencies are intentionally left unpinned to align with Esri's bundled packages.

Because Pillow is provided by that bundled environment, Pillow vulnerability remediation is primarily controlled by ArcGIS Pro patch/update availability.

## OSV-Flagged Pillow Advisories

The latest scan flagged Pillow vulnerabilities via OSV.

- GHSA IDs: add the IDs reported by your scan output here.
- PYSEC IDs: add the IDs reported by your scan output here.

Note: No GHSA/PYSEC IDs are currently tracked in this repository; use your scanner report as the source of truth for exact IDs.

## Mitigations

- Upgrade ArcGIS Pro to a patched build as soon as available. Recommended minimum targets: 3.4.4+ or 3.5.5+ (if those builds include Pillow fixes for the flagged advisories).
- Until patched, avoid processing untrusted image files in this workflow.
- Restrict execution to trusted datasets and controlled input pipelines.

## Monitoring And Reporting

- Monitor ArcGIS Pro release notes and patch announcements for bundled Python/Pillow security fixes.
- Monitor upstream Pillow advisories (GitHub Security Advisories and OSV) for new or updated CVEs/GHSA/PYSEC records.
- If you identify an unaddressed vulnerability affecting this project, report it through repository security reporting channels (private security advisory/report if enabled) or open an issue with the advisory IDs and reproduction details.
