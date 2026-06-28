# =============================================================================
# 🛤️ RMI 360 Corridor Thinning Toolbox (rmi_360_corridor_thinning.pyt)
# -----------------------------------------------------------------------------
# Purpose:             ArcGIS Python Toolbox entry point for the PRE-THINNING
#                      corridor pipeline (manifest-driven OID ingestion).
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
#
# Description:
#   Separate, interactive toolbox holding the granular, QC-gated corridor-thinning
#   stage tools. It prefilters Mosaic 360 panorama points down to a MANIFEST of
#   images to ingest, so only kept images are created/uploaded (pre-thin), instead
#   of creating an OID for all panoramas and thinning afterward (post-thin).
#
#   This is intentionally SEPARATE from rmi_360_workflow.pyt: the corridor pipeline
#   needs human QC gates and manual editorial input between stages, which would
#   fight the main orchestrator's unattended-run model. The main orchestrator
#   consumes the exported manifest via its `thinning_mode = pre` switch.
#
# Registered Tools (run order):
#   00 Create Panorama Points (helper)
#   01 Calculate Mileposts (per-route)
#   02 Calculate Sequence (sub_order)
#   03 Detect Reversals (report-only)
#   04 Thin to Interval (flag)
#   05 QC Sequence (read-only)
#   06 Find Gaps (read-only)
#   07 QC Thinning (read-only)
#   08 Export Manifest
#   09 Run Corridor Thinning (chained, optional)
#
# Notes:
#   - All stage tools are runnable INDEPENDENTLY as checkpoints.
#   - Run order: 00 -> 01 -> 02 -> (03) -> 05/06 -> 04 -> 07 -> 08, QC between.
# =============================================================================

import sys
import importlib.util
from pathlib import Path


def _discover_toolbox_dir():
    """Find the repository root that contains the tools package."""
    candidates = []

    module_file = globals().get("__file__")
    if module_file:
        candidates.append(Path(module_file).resolve().parent)

    module_spec = globals().get("__spec__")
    if module_spec is not None:
        origin = getattr(module_spec, "origin", None)
        if origin and origin not in {"<string>", "built-in"}:
            candidates.append(Path(origin).resolve().parent)

    argv0 = sys.argv[0] if sys.argv else None
    if argv0 and argv0 not in {"-c", "-m"}:
        candidates.append(Path(argv0).resolve().parent)

    candidates.append(Path.cwd())

    for entry in sys.path:
        if not entry:
            continue
        try:
            candidates.append(Path(entry).resolve())
        except Exception:
            continue

    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)

        for root in (candidate, *candidate.parents):
            if (root / "tools" / "__init__.py").is_file():
                return str(root)

    return str(Path.cwd())


def _purge_conflicting_modules(package_prefix, toolbox_dir):
    """Remove non-local modules that would shadow the repository packages."""
    for name, module in list(sys.modules.items()):
        if name != package_prefix and not name.startswith(package_prefix + "."):
            continue

        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue

        try:
            module_path = Path(module_file).resolve()
        except Exception:
            continue

        if Path(toolbox_dir).resolve() not in module_path.parents:
            del sys.modules[name]


def _load_local_package(package_name, package_path, toolbox_dir):
    """Load a local package so absolute imports resolve to this repository."""
    _purge_conflicting_modules(package_name, toolbox_dir)
    init_file = package_path / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        package_name,
        init_file,
        submodule_search_locations=[str(package_path)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load package {package_name} from {init_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    spec.loader.exec_module(module)
    return module


toolbox_dir = _discover_toolbox_dir()
if toolbox_dir not in sys.path:
    sys.path.insert(0, toolbox_dir)

_load_local_package("utils", Path(toolbox_dir) / "utils", toolbox_dir)


def _load_tool_class(module_filename, class_name):
    """Load a tool class directly from the local tools directory."""
    module_path = Path(toolbox_dir) / "tools" / module_filename
    module_name = f"rmi_360_corridor_tools.{Path(module_filename).stem}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {class_name} from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return getattr(module, class_name)


CorridorCreatePointsTool = _load_tool_class("corridor_create_points_tool.py", "CorridorCreatePointsTool")
CorridorCalcMPTool = _load_tool_class("corridor_calc_mp_tool.py", "CorridorCalcMPTool")
CorridorCalcSequenceTool = _load_tool_class("corridor_calc_sequence_tool.py", "CorridorCalcSequenceTool")
CorridorDetectReversalsTool = _load_tool_class("corridor_detect_reversals_tool.py", "CorridorDetectReversalsTool")
CorridorThinTool = _load_tool_class("corridor_thin_tool.py", "CorridorThinTool")
CorridorQCSequenceTool = _load_tool_class("corridor_qc_sequence_tool.py", "CorridorQCSequenceTool")
CorridorFindGapsTool = _load_tool_class("corridor_find_gaps_tool.py", "CorridorFindGapsTool")
CorridorQCThinTool = _load_tool_class("corridor_qc_thin_tool.py", "CorridorQCThinTool")
CorridorExportManifestTool = _load_tool_class("corridor_export_manifest_tool.py", "CorridorExportManifestTool")
CorridorOrchestratorTool = _load_tool_class("corridor_orchestrator_tool.py", "CorridorOrchestratorTool")


class Toolbox(object):
    def __init__(self):
        self.label = "RMI 360 Corridor Thinning (Pre-Thin)"
        self.alias = "rmi360corridor"
        self.tools = [
            CorridorCreatePointsTool,
            CorridorCalcMPTool,
            CorridorCalcSequenceTool,
            CorridorDetectReversalsTool,
            CorridorThinTool,
            CorridorQCSequenceTool,
            CorridorFindGapsTool,
            CorridorQCThinTool,
            CorridorExportManifestTool,
            CorridorOrchestratorTool,
        ]
