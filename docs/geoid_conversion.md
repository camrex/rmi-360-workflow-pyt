# Camera Height Conversion (Ellipsoidal → NAVD88)

## Why this exists

Camera positions come from a Movella/Xsens Vision Navigator (XVN), RTK-corrected
through Point One Nav. The XVN **only outputs ellipsoidal height** — it has no
geoid model — and that height is in the **reference frame of the RTK
corrections**. The OID, however, declares vertical CRS **EPSG:5703 (NAVD88
height, orthometric meters)** and uses Esri's Terrain3D elevation source, which
is also orthometric.

Getting from one to the other takes two corrections:

| Step | What it corrects | Size across CONUS |
| --- | --- | --- |
| 1. Reference frame | Moves the height from the corrections' frame (ITRF2014 for `POLARIS`) to **NAD83(2011)**, the frame GEOID18 is defined against | about **+0.9 m** (west) to **+1.5 m** (southeast); ~+1.1 m in IL/KC |
| 2. Geoid | NAD83(2011) ellipsoidal height → **NAVD88** orthometric via **GEOID18** | geoid separation N ≈ **−8 m to −33 m** |

Without step 2, cameras sit 8–33 m below the orthometric ground surface. Without
step 1, they sit about 1 m low. ArcGIS image-to-ground projection uses the camera
Z directly, so either error corrupts measurements taken from the imagery.
Horizontal coordinates (EPSG:4326) and the vertical WKID (5703) are unchanged —
the conversion makes the existing label *true*.

## Which frame are our heights in?

It depends on the **NTRIP mount point** configured on the XVN:

| Point One mount point | Frame of the corrections | `source_frame` |
| --- | --- | --- |
| `POLARIS` | ITRF2014 at the current epoch | `ITRF2014` |
| `POLARIS_LOCAL` | NAD83(2011) at epoch 2010.0 (US) | `NAD83_2011` |

The rig connects to **`POLARIS`** (confirmed on the XVN, 2026-10-01; believed
unchanged since the XVN was acquired), so the default is `ITRF2014`. If the
mount point ever changes, the `source_frame` of the projects captured under it
must change with it. Other global/PPP solutions use `ITRF2020`; `WGS84` is
accepted and treated as ITRF2020 (current WGS84 realizations match it to a few
centimetres).

Staying on `POLARIS` is deliberate: the archive stays in one frame, and the
WGS 84 horizontal label (4326) remains honest — `POLARIS_LOCAL` would put
NAD83(2011) positions (about 1–1.5 m apart horizontally) under that label.

## Where it happens

The conversion runs inside the **Calculate OID Attributes** step
(`utils/calculate_oid_attributes.py` → `convert_heights_to_navd88`), immediately
after Esri's `AddImagesToOrientedImageryDataset` populates rows from image EXIF
and before any downstream step (GPS smoothing, linear referencing, footprints)
reads Z. Both steps are single vectorized pyproj calls
(`utils/shared/geoid_transform.py`):

1. `to_nad83_2011` — source frame → NAD83(2011) geographic 3D (EPSG:6319) at each
   row's **capture epoch** (decimal year from `AcquisitionDate`), using PROJ's
   time-dependent Helmert transformation.
2. `ellipsoidal_to_orthometric` — EPSG:4979 → EPSG:6349, i.e. the GEOID18 grid
   shift.

**Only the Z** of the results is used — lon/lat are never overwritten.

## Configuration

```yaml
spatial_ref:
  geoid_correction:
    enabled: true          # default true; set false to restore legacy (ellipsoidal) behavior
    model: "GEOID18"       # CONUS only; the only model currently supported
    source_frame: "ITRF2014"  # frame of the camera heights: POLARIS = ITRF2014 (schema 1.6.0)
```

`source_frame` was added in schema **1.6.0**; the Config Editor's Upgrade fills
it with `ITRF2014`. It is never guessed: if it is missing, the conversion stops.

## Safety properties

- **Frame operation pinned, never a no-op:** the frame step is selected by
  searching for a pipeline containing both `helmert` and `t_epoch`. PROJ's own
  WGS 84 → NAD83(2011) operation is a **zero-shift placeholder** (2 m accuracy,
  dh = 0) — that is why `WGS84` is mapped to ITRF2020 rather than EPSG:4979. If no
  time-dependent operation exists, the step fails hard.
- **Frame shift band:** every applied height change must be finite with
  magnitude 0.1–3 m. A near-zero shift means a no-op slipped through; the step
  aborts.
- **Capture epoch required:** a row without `AcquisitionDate` (when the source
  frame needs a shift) aborts the step. The shift changes by only ~1 mm/year,
  but no height is written without a known epoch.
- **Grid pinned, never silent:** the GEOID18 operation is selected by searching
  for the grid (`us_noaa_g2018u0.tif`) in its pipeline. If the grid is not
  installed, the step **fails hard**.
- **Coverage enforced:** points outside GEOID18 (non-CONUS) produce non-finite
  results and abort the step.
- **Geoid plausibility band:** every applied separation must fall in −50 m … −2 m
  (CONUS GEOID18 is ≈ −8 … −33 m).
- **Idempotent and traceable:** the original ellipsoidal height is preserved
  per-row in `Z_Ellipsoidal` (DOUBLE) and the applied frame/epoch in `Z_Frame`
  (TEXT, e.g. `ITRF2014@2026.051`; `NAD83_2011` when no shift applied). Both are
  added at runtime like `QCFlag`. Rows with `Z_Ellipsoidal` populated are
  re-derived from that original, so re-running the step never double-converts.
- **Logged:** the step logs the frame shift (min/mean/max, epoch range), the
  input/output Z ranges, and the min/mean/max geoid separation.

## Environment requirements

- **pyproj** (ships with ArcGIS Pro's Python; verified with pyproj 3.7.2 /
  PROJ 9.8.1 under ArcGIS Pro). The ITRF → NAD83(2011) Helmert operations come
  from PROJ's database — no extra grid is needed for the frame step.
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
  from utils.shared.geoid_transform import get_frame_transformer, get_geoid_transformer
  get_geoid_transformer("GEOID18")     # raises GeoidTransformError if the grid is missing
  get_frame_transformer("ITRF2014")    # raises if no time-dependent Helmert is available
  ```

## Reprocessing existing OIDs

Two generations of OIDs need repair:

| OID state | How to recognize it | Error |
| --- | --- | --- |
| Built before the geoid conversion | `Z_Ellipsoidal` empty | cameras **8–33 m** low (ellipsoidal heights labeled NAVD88) |
| Converted under schema 1.5.0 | `Z_Ellipsoidal` set, `Z_Frame` empty | cameras about **1 m** low (GEOID18 applied without the frame shift) |

Relabeling fixes nothing; the numbers must be recomputed. Two routes:

- **Rebuilding anyway?** Re-run **Calculate OID Attributes**. It recomputes every
  row from `Z_Ellipsoidal` (or the raw EXIF Z) with both steps and writes
  `Z_Frame`.
- **Repair in place** with the maintenance tool:
  **`RMI 360 OID Maintenance` → `40 - Fix OID Elevations (-> NAVD88)`**
  (`tools/oid_fix_elevations_tool.py` → `utils/fix_oid_elevations.py`).

Tool 40 decides per row:

| Row state | Action |
| --- | --- |
| `Z_Ellipsoidal` empty (never converted) | Full conversion: remove the lever-arm offset, frame step, GEOID18, re-add the offset; set `Z_Ellipsoidal` and `Z_Frame` |
| `Z_Ellipsoidal` set, `Z_Frame` empty (1.5.0) | `Z += dh` (frame shift at the row's position and capture epoch), set `Z_Frame`. With source frame `NAD83_2011`, Z is unchanged and only `Z_Frame` is recorded |
| `Z_Frame` matches the Source Frame | Skipped — safe to re-run |
| `Z_Frame` names a different frame | **Whole run refused** (no frame mixing); nothing written |

- Applying `dh` to the stored Z keeps each row's lever-arm offset exactly as it
  was built (no dependence on today's `camera_offset.z`); since N does not depend
  on height, this equals a full recompute. `Z_Ellipsoidal` is never modified for
  these rows.
- **Source Frame parameter:** project configs older than 1.6.0 have no
  `source_frame`. Leave the parameter blank to use the config's value, or set it
  (for `POLARIS` captures: `ITRF2014`). With neither, the tool stops.
- Point it at **whichever feature class backs the published service** — the
  source OID or the `*_aws` delivery copy. They are independent datasets: fixing
  one does not propagate to the other (each carries its own markers, so fixing
  both is safe). If the published copy was thinned/subset (e.g. a delivery
  subset), fix the `*_aws` copy to repair the live service, and fix the source
  separately for future rebuilds.
- Republish routing: a source-OID input runs the standard Generate OID Service
  flow (duplicate to `*_aws`, rewrite ImagePaths, publish — note this
  regenerates the `*_aws` copy from the source). A `*_aws` input is published
  **directly** under the un-suffixed service name, with no re-copy and no
  ImagePath rewrite — the copy is already in delivery form.
- **Dry run by default**: reports per-state row counts (converted /
  frame-corrected / marked-only / already-fixed / skipped), the applied frame
  shift and N ranges, a 5-row before→after sample, and (if Republish is checked)
  the republish preflight result and a read-only list of the portal items an
  overwrite would delete. Nothing is written until Dry Run is unchecked.
- Rewrites `SHAPE@Z`, `Z`, and the `CameraOrientation` string per row.
- **Republish Service** (optional, off by default): runs a read-only preflight,
  then deletes the existing portal items for the OID's service name
  (exact-title, owner-scoped) and runs the standard Generate OID Service flow.
  The images and their S3 objects are untouched — only the OID and the
  portal/service side change. (This toolbox never writes EXIF `GPSAltitude`, so
  the image files need no repair.)

## Spot-checking against Terrain3D / lidar

Pick a few cameras, query the ground elevation (Terrain3D, or USGS 3DEP lidar,
both NAVD88) at each camera's lon/lat, and compute **camera Z − ground**. On a
hi-rail capture it should be close to the **mast height plus the rail-head height
above the sampled ground** — e.g. about 3.1 m for the mast in the data
dictionary sample, plus a few tenths of a metre — and roughly constant along the
line.

- If it comes out **8–33 m negative**, the OID was never converted.
- If it comes out **about 1 m short** of the expected value (≈1.1 m in IL/KC,
  ≈0.9 m further west, ≈1.5 m in the southeast), the OID was converted without
  the frame step — run tool 40.
- After this fix, cameras sit about **1 m higher** than under schema 1.5.0, so
  spot-check results recorded before the fix will read ~1 m lower than new ones.

## Assumption

Operation is **CONUS-only** (GEOID18). Work in Alaska, Hawaii, or territories
requires adding the appropriate NGS model to
`utils/shared/geoid_transform.SUPPORTED_GEOID_MODELS` and setting
`spatial_ref.geoid_correction.model` accordingly; until then, out-of-coverage
points fail loudly by design.
