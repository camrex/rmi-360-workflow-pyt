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
    class DummyCfg:
        pass
    def dummy_func(*args, **kwargs): return "called"
    # Patch all used functions in the build_step_funcs module
    import sys
    mod = sys.modules["utils.build_step_funcs"]
    mod.run_mosaic_processor = dummy_func
    mod.create_oriented_imagery_dataset = dummy_func
    mod.add_images_to_oid = dummy_func
    mod.assign_group_index = dummy_func
    mod.enrich_oid_attributes = dummy_func
    mod.smooth_gps_noise = dummy_func
    mod.correct_gps_outliers = dummy_func
    mod.update_linear_and_custom = dummy_func
    mod.enhance_images_in_oid = dummy_func
    mod.rename_images = dummy_func
    mod.update_metadata_from_config = dummy_func
    mod.geocode_images = dummy_func
    mod.build_oid_footprints = dummy_func
    mod.deploy_lambda_monitor = dummy_func
    mod.copy_to_aws = dummy_func
    mod.generate_oid_service = dummy_func
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
    for _key, entry in step_funcs.items():
        assert "label" in entry
        assert callable(entry["func"])
        # skip is optional
        if "skip" in entry:
            assert callable(entry["skip"])
