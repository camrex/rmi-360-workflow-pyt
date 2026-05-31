# =============================================================================
# 📦 RMI 360 Imaging Workflow Toolbox (rmi_360_workflow.pyt)
# -----------------------------------------------------------------------------
# Purpose:             ArcGIS Python Toolbox entry point for the RMI 360 Imaging Workflow
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.1.1
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
# Last Updated:        2025-05-22
#
# Description:
#   This file defines the ArcGIS Python Toolbox interface, registering all pipeline tools for the RMI 360 workflow.
#   It acts as a wrapper and dispatcher, exposing tools for imagery processing, OID management, reporting, and AWS integration.
#   No business logic is implemented here; all workflow logic resides in the /tools and /utils modules.
#
# File Location:        /rmi_360_workflow.pyt
# Called By:            ArcGIS Pro (Toolbox registration), ArcGIS Python Toolbox Loader
#
# Directory Layout:
#   tools/              → Tool classes (UI + execution)
#   utils/              → Core processing and validation modules
#   utils/manager/      → Configuration, Logging, Path and Progressor management modules
#   utils/validators/   → Configuration and schema validation modules
#   utils/shared/       → Reusable stateless utilities
#   docs_legacy/        → Markdown documentation
#   configs/            → YAML templates and schema registry
#   templates/          → HTML report and style templates
#
# Registered Tools:
#   - 🧰 Process360Workflow
#   - 🎞️ RunMosaicProcessorTool
#   - 🏗️ CreateOrientedImageryDatasetTool
#   - 🧬 CreateOIDTemplateTool
#   - 📐 BuildOIDFootprints
#   - 🧭 AddImagesToOIDTool
#   - 🧮 UpdateLinearAndCustomTool
#   - 🛰️ SmoothGPSNoiseTool
#   - 🏷️ RenameAndTagImagesTool
#   - ☁️ CopyToAwsTool
#   - 🌐 GenerateOIDService
#   - 🌍 GeocodeImagesTool
#   - 📝 GenerateReportFromJSONTool
#   - 🔐 SetAWSKeyringCredentialsTool
#
# Documentation:
#   See: docs/TOOL_OVERVIEW.md and docs/toolbox_reference.md
#
# Notes:
#   - Supports background execution where applicable
#   - Designed for ArcGIS Pro 3.4+ with Python 3.9+ environments
#   - All tool logic is modularized for maintainability and extensibility
# =============================================================================

# Add toolbox directory to Python path for imports
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
    module_name = f"rmi_360_workflow_tools.{Path(module_filename).stem}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {class_name} from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return getattr(module, class_name)


# Import tools to run individually without relying on the generic 'tools' package name
Process360Workflow = _load_tool_class("process_360_orchestrator.py", "Process360Workflow")
RunMosaicProcessorTool = _load_tool_class("run_mosaic_processor_tool.py", "RunMosaicProcessorTool")
CreateOrientedImageryDatasetTool = _load_tool_class("create_oid_tool.py", "CreateOrientedImageryDatasetTool")
AddImagesToOIDTool = _load_tool_class("add_images_to_oid_tool.py", "AddImagesToOIDTool")
SmoothGPSNoiseTool = _load_tool_class("smooth_gps_noise_tool.py", "SmoothGPSNoiseTool")
UpdateLinearAndCustomTool = _load_tool_class("update_linear_and_custom_tool.py", "UpdateLinearAndCustomTool")
RenameAndTagImagesTool = _load_tool_class("rename_and_tag_tool.py", "RenameAndTagImagesTool")
GeocodeImagesTool = _load_tool_class("geocode_images_tool.py", "GeocodeImagesTool")
BuildOIDFootprints = _load_tool_class("build_oid_footprints_tool.py", "BuildOIDFootprints")
CopyToAwsTool = _load_tool_class("copy_to_aws_tool.py", "CopyToAwsTool")
GenerateOIDService = _load_tool_class("generate_oid_service_tool.py", "GenerateOIDService")
GenerateReportFromJSONTool = _load_tool_class("generate_report_tool.py", "GenerateReportFromJSONTool")
CreateOIDTemplateTool = _load_tool_class("create_oid_template_tool.py", "CreateOIDTemplateTool")
SetAWSKeyringCredentialsTool = _load_tool_class("set_aws_keyring_tool.py", "SetAWSKeyringCredentialsTool")


class Toolbox(object):
    def __init__(self):
        self.label = "RMI 360 Imaging Workflow Python Toolbox"
        self.alias = "rmi360workflow"
        self.tools = [
            Process360Workflow,
            RunMosaicProcessorTool,
            CreateOrientedImageryDatasetTool,
            AddImagesToOIDTool,
            SmoothGPSNoiseTool,
            UpdateLinearAndCustomTool,
            RenameAndTagImagesTool,
            GeocodeImagesTool,
            BuildOIDFootprints,
            CopyToAwsTool,
            GenerateOIDService,
            GenerateReportFromJSONTool,
            CreateOIDTemplateTool,
            SetAWSKeyringCredentialsTool
        ]
