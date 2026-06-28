# 🛤️ Corridor Thinning — Pre-Thin Workflow

The corridor thinning pipeline prefilters Mosaic 360 panorama points down to a
**manifest of images to ingest**, so only kept images are created in the OID and
uploaded to AWS. It replaces post-OID thinning (`Filter Distance Spacing`) with
**pre-OID, manifest-driven thinning**, saving substantial AWS storage/processing.

Validated end-to-end on project 26-150 (Metra/UP Harvard, Geneva, Kenosha, McHenry
subdivisions): **262,925 captured → 196,067 editorially included → 51,110 thinned
to ~4.5 m** (WKID 6455, NAD83(2011) IL State Plane East, US survey feet).

---

## Post-thin vs pre-thin

| | Post-thin (default, legacy) | Pre-thin (new, optional) |
| --- | --- | --- |
| When | OID built for **all** panoramas, thinned before upload | Thin **first**, then build OID for kept only |
| Driver | `Filter Distance Spacing` step (`distance_spacing`) | Corridor manifest CSV |
| Switch | `thinning_mode: post` | `thinning_mode: pre` |
| AWS cost | Higher (all images processed) | Lower (kept images only) |

Pre-thin is **opt-in**. With `thinning_mode: post` (the default) nothing changes.

---

## Where it lives

The corridor stage tools live in a **separate, interactive toolbox**:
`rmi_360_corridor_thinning.pyt`. It is intentionally separate from the main
`rmi_360_workflow.pyt` orchestrator because the pipeline needs **human QC gates and
manual editorial input** between stages, which would fight the orchestrator's
unattended-run model. The main orchestrator simply **consumes the exported
manifest** via its `Thinning Mode = pre` switch.

All stage tools are runnable **independently as checkpoints**, and the QC tools are
**read-only and safe** to run at any time.

---

## The tools (run order)

| # | Tool | Writes | Purpose |
| --- | ------ | -------- | --------- |
| 00 | Create Panorama Points | point FC + reel/reel_start_ts/frame + empty include/mp_pre/track | GeoTagged Photos → Points + identity parse |
| 01 | Calculate Mileposts (per-route) | `mp_meas` | Per-route Locate Features Along Routes |
| 02 | Calculate Sequence (sub_order) | `sub_order` | Position sequence per (mp_pre, track) with frame tie-break |
| 03 | Detect Reversals (report-only) | report | Flag capture back-ups (LIVE vs HANDLED) |
| 04 | Thin to Interval (flag) | `flag_5m` | Anchor-reset thinning to a target interval |
| 05 | QC Sequence (read-only) | — | Validate the sequence |
| 06 | Find Gaps (read-only) | — | List large sub_order gaps |
| 07 | QC Thinning (read-only) | — | Deep QC the thinned set |
| 08 | Export Manifest | CSV | Combined manifest for Add Images To OID |
| 09 | Run Corridor Thinning (chained) | all of the above | Optional end-to-end run |

**Recommended order:** 00 → 01 → 02 → (03) → 05/06 → 04 → 07 → 08, with QC gates
between stages. The granularity is deliberate: QC-between-stages caught real bugs
during development (junction mis-snapping, mp_meas quantization ties, dual-track
overlap).

---

## Inputs you prepare (upstream, manual)

The toolbox starts at **Create Panorama Points / Calculate Mileposts**. You still
provide:

1. **Editorial inclusion** — set `include` (1 keep / 0 drop), `mp_pre`
   (subdivision), and `track` (parallel-track tag; NULL for normal points) on the
   point FC. This is the 262,925 → 196,067 editorial cut (overlap / redundant /
   off-track removed). Detect-on-all, act-on-`include=1`.
2. **Route centerlines** — per-subdivision **M-enabled** centerline features whose
   route id matches `mp_pre`.

---

## Correctness rules (preserved from the validated scripts)

- **Per-route Locate** — each subdivision's points locate only against its own
  route; cross-route snapping at junctions is structurally impossible.
- **(mp_pre, track) partitioning** — parallel tracks stay independent threads so
  thinning keeps both through dual-track overlaps.
- **Oriented-frame tie-break** — within `eps_miles`, ties are ordered by frame
  oriented to the local MP direction; geometry projection is fallback only.
- **WKID-aware threshold** — `5 m = 16.4042 US survey ft` at WKID 6455 via
  `metersPerUnit`. Never hard-coded; set the WKID parameter.
- **Reel identity = (reel, reel_start_ts)** parsed from the filename, not the reel
  number alone (a battery/power-cycle bug can inject out-of-sequence reels).
- `mp_meas` is **DOUBLE** (precision); thinning is **non-destructive** (a flag).

---

## Threshold / unit math

The Thin and QC Thinning tools take a **Linear Unit** threshold (default `5 Meters`)
plus a **trim** (default `1.5 Meters` → ~4.5 m effective) and a **WKID**. Meters are
converted to the data's planar units: `units = meters / metersPerUnit(wkid)`.
26-150 used 4.5 m (trim 1.5): 51,110 kept, p95 ~5.88 m, no within-run gap past
~6.1 m. 5.0 m gave 47,251 with p95 ~6.4 m.

---

## Producing and consuming the manifest

1. Run the corridor tools → **Export Manifest** writes a CSV (one row per kept
   image; `Path` is the operative key; `mp_pre`/`track`/`sub_order`/`reel`/`frame`/
   `X`/`Y`/`Z` are traceability).
2. In `config.yaml` set `thinning_mode: pre` and either set
   `corridor_thinning.manifest.path` or pass the manifest on the tool dialog.
3. Run **Add Images To OID** (or the orchestrator). It matches manifest entries to
   files on disk **by filename** (storage folders do not map 1:1 to subdivisions),
   adds only the kept images, and logs kept-vs-found reconciliation.
4. In the orchestrator, `Filter Distance Spacing` **auto-skips** in pre mode
   ("Skipped (pre-thinned via corridor manifest)").

---

## Migration note: post-thin → pre-thin

1. Keep running post-thin until the corridor pipeline is validated for a project.
2. Prepare the point FC editorial fields + route centerlines (upstream).
3. Run the corridor toolbox, gating on the read-only QC tools, to export a manifest.
4. Confirm the manifest count and per-subdivision counts look right (compare to the
   QC Thinning funnel).
5. Set `thinning_mode: pre`, point Add Images at the manifest, and run the main
   workflow. The post-thin distance filter is skipped automatically.
6. To revert, set `thinning_mode: post` and clear the manifest — behavior returns
   to the legacy all-images path.

---

## Out of scope

- **Reversal resolution** (the 3-segment F1/R/F2 keep-F2 policy) is *designed but
  not built* — Detect Reversals is report-only (0 live reversals on 26-150).
- Automating the editorial `include`/`mp_pre`/`track` selection or building route
  centerlines remains upstream manual GIS work.
