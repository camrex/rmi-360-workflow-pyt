from utils.build_step_funcs import build_step_funcs, skip_if_copy_to_aws_disabled

def test_skip_if_copy_to_aws_disabled():
    # The orchestrator's parameters_to_dict passes typed booleans for enable_* flags.
    assert skip_if_copy_to_aws_disabled({"enable_copy_to_aws": False}) == "Skipped (disabled by user)"
    assert skip_if_copy_to_aws_disabled({"enable_copy_to_aws": True}) is None
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
        "smooth_gps", "correct_gps", "filter_distance", "update_linear_custom", "rename_images",
        "geoareas_enrichment", "update_metadata", "exiftool_geocoding", "build_footprints",
        "prepare_delivery_subset", "deploy_lambda_monitor", "copy_to_aws", "generate_service"
    ]
    assert set(step_funcs.keys()) == set(expected_keys)
    # Check structure
    for _key, entry in step_funcs.items():
        assert "label" in entry
        assert callable(entry["func"])
        # skip is optional
        if "skip" in entry:
            assert callable(entry["skip"])


# --- Corridor manifest: one resolution for every manifest-consuming step -----

class _Cfg:
    def __init__(self, vals=None):
        self.vals = vals or {}

    def get(self, key, default=None):
        return self.vals.get(key, default)


def test_resolve_run_manifest_dialog_wins():
    from utils.build_step_funcs import resolve_run_manifest
    cfg = _Cfg({"thinning_mode": "pre", "corridor_thinning.manifest.path": "cfg.csv"})
    assert resolve_run_manifest({"corridor_manifest_path": "dlg.csv"}, cfg) == "dlg.csv"


def test_resolve_run_manifest_dialog_pre_uses_config_path_even_if_config_post():
    from utils.build_step_funcs import resolve_run_manifest
    cfg = _Cfg({"thinning_mode": "post", "corridor_thinning.manifest.path": "cfg.csv"})
    assert resolve_run_manifest({"thinning_mode": "pre"}, cfg) == "cfg.csv"


def test_resolve_run_manifest_config_pre_with_dialog_default_post():
    # Config-only setups (dialog left at its default "post") keep working.
    from utils.build_step_funcs import resolve_run_manifest
    cfg = _Cfg({"thinning_mode": "pre", "corridor_thinning.manifest.path": "cfg.csv"})
    assert resolve_run_manifest({"thinning_mode": "post"}, cfg) == "cfg.csv"


def test_resolve_run_manifest_none_when_post_everywhere():
    from utils.build_step_funcs import resolve_run_manifest
    cfg = _Cfg({"thinning_mode": "post", "corridor_thinning.manifest.path": "cfg.csv"})
    assert resolve_run_manifest({"thinning_mode": "post"}, cfg) is None
    assert resolve_run_manifest({"thinning_mode": "pre"}, _Cfg()) is None


def test_update_linear_step_receives_dialog_manifest():
    # The headline bug: the dialog manifest reached Add Images only.
    import sys
    mod = sys.modules["utils.build_step_funcs"]
    captured = {}
    orig = mod.update_linear_and_custom
    mod.update_linear_and_custom = lambda **kw: captured.update(kw)
    try:
        p = {"oid_fc": "oid", "centerline_fc": "cl", "route_id_field": "rid",
             "enable_linear_ref": True, "corridor_manifest_path": "dlg.csv"}
        step_funcs = mod.build_step_funcs(p, _Cfg())
        step_funcs["update_linear_custom"]["func"]()
    finally:
        mod.update_linear_and_custom = orig
    assert captured["manifest_path"] == "dlg.csv"
