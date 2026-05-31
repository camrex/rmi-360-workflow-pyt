import importlib.util
import pathlib
import sys
import types
from pathlib import Path
from typing import Any


_MISSING = object()
_STUBBED_MODULE_NAMES = [
    "arcpy",
    "utils",
    "utils.mosaic_processor",
    "utils.create_oid_feature_class",
    "utils.add_images_to_oid_fc",
    "utils.assign_group_index",
    "utils.calculate_oid_attributes",
    "utils.smooth_gps_noise",
    "utils.correct_gps_outliers",
    "utils.filter_distance_spacing",
    "utils.update_linear_and_custom",
    "utils.rename_images",
    "utils.apply_exif_metadata",
    "utils.geocode_images",
    "utils.geocode_geoareas",
    "utils.build_oid_footprints",
    "utils.prepare_delivery_subset",
    "utils.deploy_lambda_monitor",
    "utils.copy_to_aws",
    "utils.generate_oid_service",
    "utils.geoareas_exif_integration",
]


def noop(*args, **kwargs):
    pass


def _install_stub_module(module_name, **attrs):
    mod = types.ModuleType(module_name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[module_name] = mod
    return mod


def _stubbed_build_step_funcs_module():
    snapshots = {name: sys.modules.get(name, _MISSING) for name in _STUBBED_MODULE_NAMES}

    # External dependency imported at module import time.
    try:
        _install_stub_module("arcpy")

        # Build minimal stubs for all modules imported by build_step_funcs.

        _install_stub_module("utils")
        _install_stub_module("utils.mosaic_processor", run_mosaic_processor=noop)
        _install_stub_module("utils.create_oid_feature_class", create_oriented_imagery_dataset=noop)
        _install_stub_module("utils.add_images_to_oid_fc", add_images_to_oid=noop)
        _install_stub_module("utils.assign_group_index", assign_group_index=noop)
        _install_stub_module("utils.calculate_oid_attributes", enrich_oid_attributes=noop)
        _install_stub_module("utils.smooth_gps_noise", smooth_gps_noise=noop)
        _install_stub_module("utils.correct_gps_outliers", correct_gps_outliers=noop)
        _install_stub_module("utils.filter_distance_spacing", filter_distance_spacing=noop)
        _install_stub_module("utils.update_linear_and_custom", update_linear_and_custom=noop)
        _install_stub_module("utils.rename_images", rename_images=noop)
        _install_stub_module("utils.apply_exif_metadata", update_metadata_from_config=noop)
        _install_stub_module("utils.geocode_images", geocode_images=noop)
        _install_stub_module("utils.geocode_geoareas", geocode_geoareas=noop)
        _install_stub_module("utils.build_oid_footprints", build_oid_footprints=noop)
        _install_stub_module("utils.prepare_delivery_subset", prepare_delivery_subset=noop)
        _install_stub_module("utils.deploy_lambda_monitor", deploy_lambda_monitor=noop)
        _install_stub_module("utils.copy_to_aws", copy_to_aws=noop)
        _install_stub_module("utils.generate_oid_service", generate_oid_service=noop)
        _install_stub_module("utils.geoareas_exif_integration", should_use_geoareas=lambda cfg: True)

        repo_root = pathlib.Path(__file__).resolve().parents[1]
        module_path = repo_root / "utils" / "build_step_funcs.py"
        spec = importlib.util.spec_from_file_location("build_step_funcs_under_test", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load module spec for {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, prior in snapshots.items():
            if prior is _MISSING:
                sys.modules.pop(name, None)
            elif isinstance(prior, types.ModuleType):
                sys.modules[name] = prior
            else:
                sys.modules.pop(name, None)


class DummyCfg:
    def __init__(self):
        self.paths = types.SimpleNamespace(renamed=Path("renamed_folder"))

    def get(self, key, default=None):
        if key == "delivery_subset.enabled":
            return True
        if key == "geocoding.method":
            return "none"
        return default


def test_delivery_subset_outputs_feed_upload_and_service_steps():
    mod: Any = _stubbed_build_step_funcs_module()
    cfg = DummyCfg()

    calls: dict[str, Any] = {"copy": None, "service": None}

    def fake_prepare(cfg, oid_fc, params):
        params["delivery_manifest_path"] = "manifest.csv"
        params["delivery_oid_fc"] = "my_oid_delivery"
        return {"enabled": True}

    def fake_copy(**kwargs):
        calls["copy"] = kwargs
        return {"status": "completed"}

    def fake_service(oid_fc, cfg):
        calls["service"] = {"oid_fc": oid_fc, "cfg": cfg}
        return {"status": "completed"}

    mod.prepare_delivery_subset = fake_prepare
    mod.copy_to_aws = fake_copy
    mod.generate_oid_service = fake_service

    params = {
        "input_reels_folder": "reels",
        "oid_fc": "my_oid",
        "centerline_fc": "centerline",
        "route_id_field": "route",
        "enable_linear_ref": False,
        "enable_copy_to_aws": True,
        "enable_generate_service": True,
        "enable_deploy_lambda_monitor": False,
        "enable_smooth_gps": False,
        "enable_distance_filter": False,
        "enable_geocode": False,
    }

    step_funcs = mod.build_step_funcs(params, cfg)

    # Run prepare step first so runtime delivery params are populated.
    step_funcs["prepare_delivery_subset"]["func"]()
    step_funcs["copy_to_aws"]["func"]()
    step_funcs["generate_service"]["func"]()

    assert calls["copy"] is not None
    assert calls["copy"]["manifest_path"] == "manifest.csv"
    assert calls["copy"]["local_dir"] == cfg.paths.renamed

    assert calls["service"] is not None
    assert calls["service"]["oid_fc"] == "my_oid_delivery"


def test_delivery_subset_skip_when_not_enabled():
    mod = _stubbed_build_step_funcs_module()

    class DisabledCfg(DummyCfg):
        def get(self, key, default=None):
            if key == "delivery_subset.enabled":
                return False
            return super().get(key, default)

    cfg = DisabledCfg()
    params = {
        "input_reels_folder": "reels",
        "oid_fc": "my_oid",
        "centerline_fc": "centerline",
        "route_id_field": "route",
        "enable_linear_ref": False,
        "enable_copy_to_aws": True,
        "enable_generate_service": True,
        "enable_deploy_lambda_monitor": False,
        "enable_smooth_gps": False,
        "enable_distance_filter": False,
        "enable_geocode": False,
    }

    step_funcs = mod.build_step_funcs(params, cfg)
    skip_reason = step_funcs["prepare_delivery_subset"]["skip"](params)
    assert skip_reason == "Skipped (delivery_subset.disabled)"


def test_subset_folder_strategy_routes_upload_to_delivery_local_dir():
    mod: Any = _stubbed_build_step_funcs_module()
    cfg = DummyCfg()

    calls: dict[str, Any] = {"copy": None}

    def fake_prepare(cfg, oid_fc, params):
        params["delivery_manifest_path"] = "delivery_subset_manifest.csv"
        params["delivery_local_dir"] = "prepared_subset_dir"
        params["delivery_oid_fc"] = "my_oid_delivery"
        return {"enabled": True}

    def fake_copy(**kwargs):
        calls["copy"] = kwargs
        return {"status": "completed"}

    mod.prepare_delivery_subset = fake_prepare
    mod.copy_to_aws = fake_copy

    params = {
        "input_reels_folder": "reels",
        "oid_fc": "my_oid",
        "centerline_fc": "centerline",
        "route_id_field": "route",
        "enable_linear_ref": False,
        "enable_copy_to_aws": True,
        "enable_generate_service": False,
        "enable_deploy_lambda_monitor": False,
        "enable_smooth_gps": False,
        "enable_distance_filter": False,
        "enable_geocode": False,
    }

    step_funcs = mod.build_step_funcs(params, cfg)
    step_funcs["prepare_delivery_subset"]["func"]()
    step_funcs["copy_to_aws"]["func"]()

    assert calls["copy"] is not None
    assert calls["copy"]["manifest_path"] == "delivery_subset_manifest.csv"
    assert calls["copy"]["local_dir"] == "prepared_subset_dir"


def test_manifest_only_strategy_falls_back_to_renamed_dir_for_upload():
    mod: Any = _stubbed_build_step_funcs_module()
    cfg = DummyCfg()

    calls: dict[str, Any] = {"copy": None}

    def fake_prepare(cfg, oid_fc, params):
        params["delivery_manifest_path"] = "delivery_subset_manifest.csv"
        # Intentionally no delivery_local_dir for manifest-only behavior.
        return {"enabled": True}

    def fake_copy(**kwargs):
        calls["copy"] = kwargs
        return {"status": "completed"}

    mod.prepare_delivery_subset = fake_prepare
    mod.copy_to_aws = fake_copy

    params = {
        "input_reels_folder": "reels",
        "oid_fc": "my_oid",
        "centerline_fc": "centerline",
        "route_id_field": "route",
        "enable_linear_ref": False,
        "enable_copy_to_aws": True,
        "enable_generate_service": False,
        "enable_deploy_lambda_monitor": False,
        "enable_smooth_gps": False,
        "enable_distance_filter": False,
        "enable_geocode": False,
    }

    step_funcs = mod.build_step_funcs(params, cfg)
    step_funcs["prepare_delivery_subset"]["func"]()
    step_funcs["copy_to_aws"]["func"]()

    assert calls["copy"] is not None
    assert calls["copy"]["manifest_path"] == "delivery_subset_manifest.csv"
    assert calls["copy"]["local_dir"] == cfg.paths.renamed


def test_generate_service_falls_back_to_source_oid_when_delivery_oid_missing():
    mod: Any = _stubbed_build_step_funcs_module()
    cfg = DummyCfg()

    calls: dict[str, Any] = {"service": None}

    def fake_prepare(cfg, oid_fc, params):
        params["delivery_manifest_path"] = "delivery_subset_manifest.csv"
        # Intentionally no delivery_oid_fc to verify fallback behavior.
        return {"enabled": True}

    def fake_service(oid_fc, cfg):
        calls["service"] = {"oid_fc": oid_fc, "cfg": cfg}
        return {"status": "completed"}

    mod.prepare_delivery_subset = fake_prepare
    mod.generate_oid_service = fake_service

    params = {
        "input_reels_folder": "reels",
        "oid_fc": "my_source_oid",
        "centerline_fc": "centerline",
        "route_id_field": "route",
        "enable_linear_ref": False,
        "enable_copy_to_aws": False,
        "enable_generate_service": True,
        "enable_deploy_lambda_monitor": False,
        "enable_smooth_gps": False,
        "enable_distance_filter": False,
        "enable_geocode": False,
    }

    step_funcs = mod.build_step_funcs(params, cfg)
    step_funcs["prepare_delivery_subset"]["func"]()
    step_funcs["generate_service"]["func"]()

    assert calls["service"] is not None
    assert calls["service"]["oid_fc"] == "my_source_oid"
