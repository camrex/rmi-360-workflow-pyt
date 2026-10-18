# 🛤️ Corridor Thinning — Design Notes

The design record for the corridor thinning pipeline: why each stage works the way
it does, the parameter choices and their 26-150 results, the reversal-resolution
design, and the gotchas. For how to run the toolbox, see
[corridor_thinning.md](corridor_thinning.md).

This is the original `PIPELINE.md` from the standalone scripts the toolbox was
ported from. It is kept as written apart from this preface and the corrections
marked *(2026 correction)*. The scripts it names map to the toolbox like this:

| Script | Toolbox tool (`rmi_360_corridor_thinning.pyt`) | Module |
| --- | --- | --- |
| `calc_mp.py` | 01 Calculate Mileposts | `utils/corridor/calc_mp.py` |
| `calc_sub_order.py` | 02 Calculate Sequence | `utils/corridor/calc_sub_order.py` |
| `detect_reversals.py` | 03 Detect Reversals | `utils/corridor/detect_reversals.py` |
| `thin_5m.py` | 04 Thin to Interval | `utils/corridor/thin.py` |
| `qc_sub_order.py` | 05 QC Sequence | `utils/corridor/qc_sub_order.py` |
| `find_gaps.py` | 06 Find Gaps | `utils/corridor/find_gaps.py` |
| `qc_thin.py` | 07 QC Thinning | `utils/corridor/qc_thin.py` |
| `export_manifest.py` | 08 Export Manifest | `utils/corridor/export_manifest.py` |

In the toolbox, the constants below (`EPS_MILES`, `THRESHOLD_FT`,
`MIN_BACKTRACK_FT`, …) are tool parameters whose defaults are set in each tool's
dialog. The `corridor_thinning.*` block in `config.yaml` mirrors them, but the
stage tools do not read it.

**Units changed in the port.** The scripts worked in the data's US survey feet. The
toolbox takes the threshold *and the trim* in meters and converts both through the
WKID. The scripts' `THRESHOLD_TRIM_FT=1.5` was **1.5 ft**, giving 16.4042 − 1.5 ≈
14.90 ft ≈ **4.54 m**. A trim of 1.5 *meters* gives 3.5 m. To reproduce the 26-150
result in the toolbox, use a trim of 1.5 ft (≈ 0.457 m).

---

Prefilter Mosaic 360 panorama points down to a manifest of images to ingest
into an Oriented Imagery Dataset (OID), so only the kept images are created
and uploaded to AWS. Replaces post-OID thinning with pre-OID, manifest-driven
thinning.

Validated end-to-end on project 26-150 (Metra/UP Harvard, Geneva, Kenosha,
McHenry subdivisions): 262,925 captured -> 196,067 editorially included ->
51,110 thinned to ~4.5 m. ArcGIS Pro, data in WKID 6455 (NAD83(2011)
IL State Plane East, US ft).

---

## The pipeline at a glance

| Stage | Script | Writes | Purpose |
|-------|--------|--------|---------|
| 1 | `calc_mp.py` | `mp_meas` | Per-route milepost via Locate Features Along Routes |
| 2 | `calc_sub_order.py` | `sub_order` | Position sequence per (mp_pre, track) with frame tie-break |
| 3 | `detect_reversals.py` | `reversal_id`* | Flag capture back-ups (report-only by default) |
| 4 | `thin_5m.py` | `flag_5m` | Anchor-reset thinning to a target interval |
| 5a | `qc_sub_order.py` | — | QC the sequence (read-only) |
| 5b | `find_gaps.py` | — | List large sub_order gaps (read-only) |
| 5c | `qc_thin.py` | — | Deep QC the thinned set (read-only) |
| 6 | `export_manifest.py` | CSV | Single combined manifest for Add Images To OID |

Run order: 1 -> 2 -> (3) -> 5a/5b -> 4 -> 5c -> 6, with QC gates between.

---

## Core data model and identity

These are the hard-won rules that make the pipeline correct. Preserve them in
the toolbox.

**Capture run = (reel, reel_start_ts), parsed from the filename.**
Reel NUMBER alone is NOT a reliable key:
- A Mosaic battery/power-cycle bug can inject an out-of-sequence reel 1
  mid-stream (e.g. ...12, [powercycle], 1, 13, 14...).
- Reel numbers continue across days and across disjoint locations; sometimes
  reset; sometimes a different reel number is chosen to cover an area.

The filename embeds the reel START timestamp, which IS the reliable cross-reel
ordering key:
  `pano_reel_0023_20260619-160716_26-150_000037.jpg`
   -> reel=0023, reel_start_ts=20260619-160716, frame=000037
Regex (project tag is a free wildcard, can be anything):
  `reel_(\d+)_(\d{8}-\d{6})_.*_(\d+)\.jpg`

Within a reel, `frame` is monotonic and tie-free -> the high-resolution
sequence signal. `Name` is globally unique. `DateTime` is per-frame capture
time (corroborates frame order).

**Ordering signal hierarchy:**
- reel + reel_start_ts : which contiguous capture run a frame belongs to
- frame               : fine sequence within a run (clean, no ties)
- mp_meas             : position along route (coarse; near-ties - see below)
- planar X/Y bearing  : direction (RTK+IMU corrected, clean)
- DateTime            : global capture order / corroboration

**mp_meas has near-ties.** Adjacent points sometimes land on identical or
near-identical measures. Normal spacing ~0.00065 mi (~3.4 ft); ties span
0..0.0002 mi. This is why sequencing must break ties by FRAME, not by raw
measure (Stage 2).

*(2026 correction)* This paragraph originally blamed the ties on Locate Features
Along Routes quantizing its measures. A later check found Locate's `MEAS`
bit-identical to `measureOnLine` on the route geometry, so Locate does not round.
The ties are real geometry: adjacent points that project to almost the same spot
on the route. The frame tie-break is the right fix either way.

---

## Stage details, parameters, and decisions

### Stage 1 — calc_mp.py (mileposts)
- **Per-route Locate**: each subdivision's points are located against ONLY its
  own route (matched by mp_pre). A point cannot take a measure from a route it
  doesn't belong to. This was REQUIRED, not optional: at junctions (e.g.
  Harvard/McHenry, Harvard/Geneva convergence near OTC) a single global Locate
  snapped points to the wrong route, producing huge mp jumps. Per-route Locate
  makes cross-route snapping structurally impossible.
- **Full precision, no rounding** -> adds no artificial ties of its own.
- **All points** (regardless of include) get a measure.
- NULL mp_meas = point beyond search radius of its own route (expected; the
  200 ft radius was chosen to capture exactly what's needed).
- Params: points FC, routes FC (M-enabled), route_id_field (=mp_pre on both),
  meas_out_field, key_field (Name - unique), search_radius (200 ft used).
- Locate output kept the full point schema (no ORIG_FID), so results are
  matched back by Name, not OID.

### Stage 2 — calc_sub_order.py (sequence)
- **Partition = (mp_pre, track).** track is NULL for normal points (-> "_main"
  sentinel) and set for parallel-track overlaps. This keeps parallel tracks
  that share a milepost range (Harvard track-1 / track-4 overlap near CY Jct)
  as INDEPENDENT threads so thinning doesn't collapse them into one.
- **Primary order: mp_meas ascending.** **Tie/near-tie break: oriented frame.**
  Points within EPS_MILES of each other are a group; ordered by frame in the
  direction that makes mp ASCEND in that capture run (detect frame-vs-mp sign
  from same-run neighbors -> ascending frame if forward-captured, descending if
  reverse-captured). Frame is exact where geometry projection stumbles on
  near-ties. Geometry bracket-projection remains only as a fallback when
  orientation can't be derived.
- EPS_MILES = 0.0003 mi (~1.6 ft): below normal spacing (0.00065), above
  artifact floor (0.0002). Tune per dataset from the min-step/p05 stats.
- track is a SHORT integer; tkey() coerces to string to avoid mixed-type sort.
- Scope: include = 1.
- sub_order is unique within (mp_pre, track), NOT within mp_pre alone.

### Stage 3 — detect_reversals.py (capture back-ups)
- A reversal = within a capture run, walking by frame, the planar BEARING flips
  to oppose the run's prevailing direction AND the span retraces >= MIN_BACKTRACK_FT
  of actual backward displacement. The displacement floor (not just bearing)
  guards against heading spin at near-zero speed (the real false-positive risk
  with RTK; GPS noise is otherwise minimal).
- Reports each reversal's include=1 (LIVE, pollutes working set) vs include=0
  (HANDLED, already excluded) breakdown. include=0 is a MIXED bag (reversals +
  off-track + redundant passes + unneeded frames), so detect on ALL points but
  only act on LIVE ones.
- On 26-150: 1 reversal total, fully HANDLED (already include=0). Zero LIVE.
  Keep as a QC tool for future captures.
- Params: MIN_BACKTRACK_FT=15, OPPOSE_DEG=120, PREVAIL_WINDOW=7,
  MIN_REVERSAL_FRAMES=2, INCLUDE_SCOPE (None=all), ONLY_REPORT_LIVE.
- Reversal RESOLUTION (3-segment overlap F1/R/F2: keep F2 the corrected pass,
  drop R + F1-overlap) was DESIGNED but NOT built - no live reversals needed it.
  See "Reversal resolution" below if a future capture has LIVE reversals.

### Stage 4 — thin_5m.py (anchor-reset thinning)
- Walks each (mp_pre, track) partition by sub_order. Keeps an anchor; drops
  every following point within THRESHOLD_FT planar of the anchor; first point
  to clear becomes the new anchor (kept). Resets anchor at every partition
  boundary so each track/subdivision thins independently and overlaps keep both
  tracks. Distance-based (not count-based) -> self-corrects to ground distance
  regardless of capture density.
- THRESHOLD_FT = 16.4042 ft = 5 m in US survey ft (data is 6455 / US ft -
  the unit conversion matters). THRESHOLD_TRIM_FT pulls it in (1.5 -> ~4.5 m).
  *(2026 correction: that trim is 1.5 **feet**; the toolbox's trim is in meters,
  see the units note at the top.)*
- Non-destructive: writes flag_5m (1 keep / 0 drop). include=0 -> NULL.
- 26-150 chose 4.5 m (THRESHOLD_TRIM_FT=1.5): tighter, p95 ~5.88 m, no
  within-run gap past ~6.1 m, 51,110 kept. 5.0 m gave 47,251 with p95 ~6.4 m.

### Stage 5 — QC (all read-only)
- `qc_sub_order.py`: contiguity (1..N per partition), reconciliation, step
  distance, large jumps, cluster reversals, null audit. NOTE: the cluster-
  reversal heuristic (uses a 0.5 ft proximity proxy) FALSE-FIRES at reel
  boundaries where two runs meet close with a heading change - interpret flags
  in that light; confirm sub_order + mp_meas both ascend = correct order.
- `find_gaps.py`: lists sub_order steps over a threshold, classifies reel-
  boundary (benign) vs within-run (investigate) via the reel/frame fields.
- `qc_thin.py`: deep thinned-set QC - spacing violations (kept pair < threshold;
  should be 0 within-run), full percentile distribution, distance histogram,
  stretched gaps, coverage holes, dual-track overlap, reduction funnel. Set its
  THRESHOLD_FT to match the thinning threshold actually used.

### Stage 6 — export_manifest.py (manifest)
- Selects include=1 AND flag_5m=1; one row per kept image; ordered mp_pre then
  sub_order. Path is the operative key for Add Images To OID (which reads
  X/Y/Z + orientation from EXIF). Other columns are traceability.
- Field formatting controlled at source: track -> "4"/"" (not 4.0), reel/frame
  zero-padding preserved, full-precision mp_meas/X/Y/Z, no literal "NaN".
- Single combined manifest (all subdivisions, mp_pre as a column).
- Storage folders (chicago/geneva/harvard/kenosha = capture sessions) do NOT
  map 1:1 to subdivisions (= mileposts). Images for one subdivision can live in
  multiple folders (junction/convergence geography; best-run selection across
  on/off-track access points). Path carries the true location regardless.
  AWS staging must follow actual Path, not assume subdivision=folder.

---

## Reversal resolution (designed, not yet built)

If a future capture has LIVE reversals (Stage 3 reports include=1 points), a
reversal creates 3 overlapping segments against increasing MP:
  F1 forward (... up to OUTER turnaround = local mp max)
  R  reverse (... back to INNER turnaround = local mp min)
  F2 forward (... resumes past the outer turnaround)
Triply-covered overlap zone = [inner mp, outer mp].
Resolution policy chosen: KEEP F2 (the corrected/intentional resumption that
flows continuously into the post-reversal corridor), DROP all R and the F1
points that F2 re-covers (F1 points with mp >= F2's lowest mp). Keep F1 points
below F2's reach so no bottom-slice gap. Flag (don't delete) - set include=0 or
a dedicated flag, reviewable. Find turnarounds via X/Y bearing reversal (clean),
read mp at those frames to bound the zone.

---

## Reduction funnel (26-150 reference)

  262,925 captured
  196,067 include=1 (editorial: overlap/redundant/off-track removed) = 74.6%
   51,110 flag_5m=1 (4.5 m thin)                = 26.1% of incl, 19.4% of all

---

## Known gotchas (carry into the toolbox)

- WKID 6455 is US survey FEET. 5 m = 16.4042 ft. Don't write `if d >= 5`.
- `in_memory` can fail for Locate event tables -> write to a real FGDB table.
- file-GDB sql_clause ORDER BY: don't COALESCE a numeric field with a string;
  sort in Python instead (the v2 sub_order script does this).
- Edit sessions lock tables -> guard Delete() in try/except.
- mp_meas must be DOUBLE to preserve precision.
- Detect on ALL points (reversal evidence intact), act only on include=1.
