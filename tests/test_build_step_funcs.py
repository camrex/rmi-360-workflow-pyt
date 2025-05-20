import pytest
from utils.build_step_funcs import build_step_funcs, skip_enhance_images, skip_if_copy_to_aws_disabled

def test_skip_enhance_images():
    assert skip_enhance_images({"skip_enhance_images": "true"}) == "Skipped (enhancement disabled)"
    assert skip_enhance_images({"skip_enhance_images": "false"}) is None
    assert skip_enhance_images({}) is None

def test_skip_if_copy_to_aws_disabled():
    assert skip_if_copy_to_aws_disabled({"copy_to_aws": "false"}) == "Skipped (disabled by user)"
    assert skip_if_copy_to_aws_disabled({"copy_to_aws": "true"}) is None
    assert skip_if_copy_to_aws_disabled({}) == "Skipped (disabled by user)"

def test_build_step_funcs_structure():
    # Minimal mocks for required functions and config
    class DummyCfg: pass
    def dummy_func(*args, **kwargs): return "called"
    # Patch all used functions in the build_step_funcs module
    import sys
    mod = sys.modules["utils.build_step_funcs"]
    setattr(mod, "run_mosaic_processor", dummy_func)
    setattr(mod, "create_oriented_imagery_dataset", dummy_func)
    setattr(mod, "add_images_to_oid", dummy_func)
    setattr(mod, "assign_group_index", dummy_func)
    setattr(mod, "enrich_oid_attributes", dummy_func)
    setattr(mod, "smooth_gps_noise", dummy_func)
    setattr(mod, "correct_gps_outliers", dummy_func)
    setattr(mod, "update_linear_and_custom", dummy_func)
    setattr(mod, "enhance_images_in_oid", dummy_func)
    setattr(mod, "rename_images", dummy_func)
    setattr(mod, "update_metadata_from_config", dummy_func)
    setattr(mod, "geocode_images", dummy_func)
    setattr(mod, "build_oid_footprints", dummy_func)
    setattr(mod, "deploy_lambda_monitor", dummy_func)
    setattr(mod, "copy_to_aws", dummy_func)
    setattr(mod, "generate_oid_service", dummy_func)
    # Minimal params
    p = {
        "project_folder": "pf",
        "input_reels_folder": "irf",
        "oid_fc": "oid",
        "centerline_fc": "cl",
        "route_id_field": "rid",
        "enable_linear_ref": "true"
    }
    step_funcs = build_step_funcs(p, DummyCfg())
    # Check all expected keys exist
    expected_keys = [
        "run_mosaic_processor", "create_oid", "add_images", "assign_group_index", "enrich_oid",
        "smooth_gps", "correct_gps", "update_linear_custom", "enhance_images", "rename_images",
        "update_metadata", "geocode", "build_footprints", "deploy_lambda_monitor", "copy_to_aws", "generate_service"
    ]
    assert set(step_funcs.keys()) == set(expected_keys)
    # Check structure
    for key, entry in step_funcs.items():
        assert "label" in entry
        assert callable(entry["func"])
        # skip is optional
        if "skip" in entry:
            assert callable(entry["skip"])
