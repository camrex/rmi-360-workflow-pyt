# =============================================================================
# 🛠️ RMI 360 OID Maintenance Toolbox (rmi_360_oid_maintenance.pyt)
# -----------------------------------------------------------------------------
# Purpose:             ArcGIS Python Toolbox entry point for OUT-OF-BAND OID
#                      maintenance: storage migration and diagnostics.
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             0.1.0 (scaffold)
# Author:              RMI Valuation, LLC
#
# Description:
#   Separate toolbox holding ad-hoc maintenance/repair tools that operate on an
#   ALREADY-published OID, outside the linear unattended pipeline in
#   rmi_360_workflow.pyt. Like the corridor-thinning toolbox, these are
#   interactive, technician-operated, and intentionally kept out of the main
#   orchestrator's run model.
#
#   Primary use case: move panoramas between the legacy public S3 bucket and the
#   secured (virtual cache) bucket, and migrate ImagePaths in either direction,
#   while secured-storage serving is verified with Esri (Case 04187998).
#
# Registered Tools:
#   Storage Migration:
#     01 Rewrite OID ImagePaths        (legacy <-> secured form; dry run default)
#     02 Sync OID S3 Objects           (bucket -> bucket, key-for-key; dry run)
#     10 Migrate OID Storage           (orchestrator: sync -> rewrite copy -> audit)
#   Diagnostics:
#     20 Validate ImagePath Reachability
#     21 Audit OID vs S3
#
# Notes:
#   - All mutating tools default to DRY RUN.
#   - Service (re)publishing is NOT done here -- use "Generate OID Service" in the
#     main workflow toolbox against the migrated *_secured / *_legacy copy.
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
    module_name = f"rmi_360_oid_maintenance_tools.{Path(module_filename).stem}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {class_name} from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return getattr(module, class_name)


OIDRewriteImagePathsTool = _load_tool_class("oid_rewrite_imagepaths_tool.py", "OIDRewriteImagePathsTool")
OIDSyncS3ObjectsTool = _load_tool_class("oid_sync_s3_objects_tool.py", "OIDSyncS3ObjectsTool")
OIDMigrateStorageTool = _load_tool_class("oid_migrate_storage_tool.py", "OIDMigrateStorageTool")
OIDValidateReachabilityTool = _load_tool_class("oid_validate_reachability_tool.py", "OIDValidateReachabilityTool")
OIDAuditStorageTool = _load_tool_class("oid_audit_storage_tool.py", "OIDAuditStorageTool")


class Toolbox(object):
    def __init__(self):
        self.label = "RMI 360 OID Maintenance"
        self.alias = "rmi360oidmaint"
        self.tools = [
            OIDRewriteImagePathsTool,
            OIDSyncS3ObjectsTool,
            OIDMigrateStorageTool,
            OIDValidateReachabilityTool,
            OIDAuditStorageTool,
        ]
