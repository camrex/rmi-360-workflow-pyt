# Camera Height Geoid Conversion (Ellipsoidal → NAVD88)

## Why this exists

Camera positions come from a Movella/Xsens Vision Navigator (XVN), RTK-corrected
through Point One Nav (mount point `POLARIS`, ITRF2014 ≈ WGS84). The XVN **only
outputs ellipsoidal height** — it has no geoid model. The OID, however, declares
vertical CRS **EPSG:5703 (NAVD88 height, orthometric meters)** and uses Esri's
Terrain3D elevation source, which is also orthometric.

Across CONUS the geoid separation N (where `h_ellipsoidal = H_orthometric + N`)
is roughly **−8 m to −33 m**, so unconverted camera heights sit **8–33 m below**
the orthometric ground surface. ArcGIS image-to-ground projection then models the
camera far below its true position, corrupting measurements taken from the
imagery.

The fix: convert each camera Z from WGS84/ITRF2014 ellipsoidal height to NAVD88
orthometric height via **GEOID18**, before the value is finalized in the OID.
Horizontal coordinates (EPSG:4326) and the vertical WKID (5703) are unchanged —
the conversion makes the existing label *true*.

## Where it happens

The conversion runs inside the **Calculate OID Attributes** step
(`utils/calculate_oid_attributes.py` → `convert_heights_to_navd88`), immediately
after Esri's `AddImagesToOrientedImageryDataset` populates rows from image EXIF
and before any downstream step (GPS smoothing, linear referencing, footprints)
reads Z. The whole Z column is converted in one vectorized pyproj call
(EPSG:4979 → EPSG:6349), and **only the Z** of the transform result is used —
lon/lat are never overwritten.

## Configuration

```yaml
spatial_ref:
  geoid_correction:
    enabled: true      # default true; set false to restore legacy (ellipsoidal) behavior
    model: "GEOID18"   # CONUS only; the only model currently supported
```

## Safety properties

- **Grid pinned, never silent:** the pyproj operation is selected by searching
  for the GEOID18 grid (`us_noaa_g2018u0.tif`) in the operation pipeline. If the
  grid is not installed, the step **fails hard** — PROJ's silent ballpark/no-op
  fallback can never write near-ellipsoidal values.
- **Coverage enforced:** points outside GEOID18 (non-CONUS) produce non-finite
  results and abort the step. No unconverted or extrapolated heights are written.
- **Plausibility band:** every applied separation must fall in −50 m … −2 m
  (CONUS GEOID18 is ≈ −8 … −33 m). A no-op (N≈0), positive, or oversized
  separation aborts the step.
- **Idempotent:** the original ellipsoidal height is preserved per-row in the
  `Z_Ellipsoidal` field (DOUBLE, added at runtime like `QCFlag`). Rows where it
  is already populated are re-derived from that original, so re-running the step
  can never double-convert.
- **Logged:** the step logs input/output Z ranges and the min/mean/max applied
  separation for each collect.

## Environment requirements

- **pyproj** (ships with ArcGIS Pro's Python; verified with pyproj 3.7.2 /
  PROJ 9.8.1 under ArcGIS Pro).
- **GEOID18 grid `us_noaa_g2018u0.tif`** must be in the PROJ data directory.
  ArcGIS Pro **bundles it** (`...\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\Library\share\proj`),
  so field workstations running the toolbox inside ArcGIS Pro need **no network
  access and no extra setup**.
- For any other (non-Pro) Python environment, install the grid offline with one
  of:
  - `projsync --file us_noaa_g2018u0` (needs network once), or
  - copy `us_noaa_g2018u0.tif` from an ArcGIS Pro install or
    <https://cdn.proj.org/> into `pyproj.datadir.get_data_dir()`, or
  - set `PROJ_DATA` to a directory containing the grid.
- Verify with:

  ```python
  from utils.shared.geoid_transform import get_geoid_transformer
  get_geoid_transformer("GEOID18")  # raises GeoidTransformError if the grid is missing
  ```

## Reprocessing existing OIDs

Any OID built before this change stores **ellipsoidal** heights mislabeled as
5703 — the cameras are ~8–33 m low. Relabeling fixes nothing; the numbers must
be recomputed. Use the dedicated maintenance tool:

**`RMI 360 OID Maintenance` → `40 - Fix OID Elevations (Ellipsoidal -> NAVD88)`**
(`tools/oid_fix_elevations_tool.py` → `utils/fix_oid_elevations.py`)

- Point it at **whichever feature class backs the published service** — the
  source OID or the `*_aws` delivery copy. They are independent datasets:
  fixing one does not propagate to the other (each carries its own
  `Z_Ellipsoidal` marker, so fixing both is safe). If the published copy was
  thinned/subset (e.g. a delivery subset), fix the `*_aws` copy to repair the
  live service, and fix the source separately for future rebuilds.
- Republish routing: a source-OID input runs the standard Generate OID Service
  flow (duplicate to `*_aws`, rewrite ImagePaths, publish — note this
  regenerates the `*_aws` copy from the source). A `*_aws` input is published
  **directly** under the un-suffixed service name, with no re-copy and no
  ImagePath rewrite — the copy is already in delivery form.
- **Dry run by default**: reports total/needs-fix/already-fixed/skipped row
  counts, stored → fixed Z ranges, the applied N range, a 5-row before→after
  sample, and (if Republish is checked) a read-only list of the portal items an
  overwrite would delete. Nothing is written until Dry Run is unchecked.
- The stored Z includes the camera lever-arm offset applied at build time; the
  fix recovers the pre-offset ellipsoidal source (using the project config's
  `camera_offset.z`), converts it, and re-applies the offset — so
  `Z_Ellipsoidal` keeps the same "pre-offset ellipsoidal source" semantics as
  the pipeline's enrich step, and re-runs of either path stay idempotent.
  (Numerically the fixed Z is simply `stored Z − N`, since N is independent of
  height.)
- Rewrites `SHAPE@Z`, `Z`, and the `CameraOrientation` string per row; rows with
  `Z_Ellipsoidal` already populated are skipped (safe to re-run).
- **Republish Service** (optional, off by default): deletes the existing portal
  items for the OID's service name (exact-title, owner-scoped), then runs the
  standard Generate OID Service flow (duplicate to `*_aws`, rewrite ImagePaths,
  publish). The images and their S3 objects are untouched — only the OID and
  the portal/service side change.

Afterward, spot-check: pick a camera, query Terrain3D at its lon/lat, and
confirm the new camera Z sits a small, sensible height above ground (~2.5–3 m
for the vehicle mast), not tens of meters below.

## Assumption

Operation is **CONUS-only** (GEOID18). Work in Alaska, Hawaii, or territories
requires adding the appropriate NGS model to
`utils/shared/geoid_transform.SUPPORTED_GEOID_MODELS` and setting
`spatial_ref.geoid_correction.model` accordingly; until then, out-of-coverage
points fail loudly by design.
