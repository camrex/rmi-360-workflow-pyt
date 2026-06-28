# =============================================================================
# 🛤️ Corridor Thinning Pipeline (utils/corridor)
# -----------------------------------------------------------------------------
# Backing logic for the pre-thinning corridor pipeline: prefilter Mosaic 360
# panorama points down to a manifest of images to ingest into an Oriented
# Imagery Dataset, so only the kept images are created and uploaded.
#
# Stages (run order): create_points (helper) -> calc_mp -> calc_sub_order ->
#   (detect_reversals) -> qc_sub_order / find_gaps -> thin -> qc_thin ->
#   export_manifest, with QC gates between stages.
#
# Ported from validated standalone scripts; logic preserved, parameters exposed.
# See docs and PIPELINE.md for the data model and correctness rules.
# =============================================================================

__all__ = [
    "units",
    "create_points",
    "calc_mp",
    "calc_sub_order",
    "detect_reversals",
    "thin",
    "qc_sub_order",
    "find_gaps",
    "qc_thin",
    "export_manifest",
]
