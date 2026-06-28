"""Round-trip fidelity tests against the real config.sample.yaml."""

from config_editor.core import config_io as cio
from config_editor.core import paths

SAMPLE = paths.sample_config_path()


def test_idempotent_round_trip():
    out1 = cio.dump_yaml_str(cio.load_yaml(SAMPLE))
    out2 = cio.dump_yaml_str(cio.loads_yaml(out1))
    assert out1 == out2  # editor output is a stable fixed point


def test_sample_round_trips_identically():
    """The sample is hygienic (no trailing ws, lowercase bools), so load->dump
    reproduces it line-for-line. Also guards that future edits keep it clean."""
    orig = [l.rstrip() for l in SAMPLE.read_text(encoding="utf-8").splitlines()]
    out = [l.rstrip() for l in cio.dump_yaml_str(cio.load_yaml(SAMPLE)).splitlines()]
    assert orig == out


def test_all_comments_preserved():
    orig = SAMPLE.read_text(encoding="utf-8")
    out = cio.dump_yaml_str(cio.load_yaml(SAMPLE))
    orig_comments = [l.strip() for l in orig.splitlines() if l.strip().startswith("#")]
    out_comments = [l.strip() for l in out.splitlines() if l.strip().startswith("#")]
    assert orig_comments == out_comments
    assert len(orig_comments) > 500  # the sample is heavily documented


def test_surgical_edit_changes_one_line():
    data = cio.load_yaml(SAMPLE)
    base = cio.dump_yaml_str(data).splitlines()
    cio.overlay_values(data, {"project": {"slug": "RMI_TEST_123"}})
    edited = cio.dump_yaml_str(data).splitlines()

    changed = [(b, n) for b, n in zip(base, edited) if b != n]
    assert len(changed) == 1
    before, after = changed[0]
    assert "RMI_TEST_123" in after
    assert "#" in after  # inline comment on that line is preserved


def test_extract_values_is_plain():
    data = cio.load_yaml(SAMPLE)
    values = cio.extract_values(data)
    assert isinstance(values, dict)
    assert "schema_version" in values
    # nested access works on plain dicts
    assert "s3_bucket_panos_unsecured" in values["aws"]


def test_replace_paths_overlays_collections_wholesale():
    data = cio.load_yaml(SAMPLE)
    # user removed custom2, added custom9
    user = {"oid_schema_template": {"custom_fields": {
        "custom1": {"name": "RR"},
        "custom9": {"name": "Zone"},
    }}}
    cio.overlay_values(data, user, replace_paths={"oid_schema_template.custom_fields"})
    cf = cio.extract_values(data)["oid_schema_template"]["custom_fields"]
    assert set(cf.keys()) == {"custom1", "custom9"}  # custom2 gone (replaced, not merged)
    # without replace_paths it would merge (custom2 would survive)
    data2 = cio.load_yaml(SAMPLE)
    cio.overlay_values(data2, user)
    cf2 = cio.extract_values(data2)["oid_schema_template"]["custom_fields"]
    assert "custom2" in cf2.keys()


def test_overlay_merges_maps_replaces_scalars():
    data = cio.load_yaml(SAMPLE)
    # merging a nested map must not wipe sibling keys
    before_region = cio.extract_values(data)["aws"].get("region")
    cio.overlay_values(data, {"aws": {"s3_bucket_panos_unsecured": "my-bucket"}})
    after = cio.extract_values(data)["aws"]
    assert after["s3_bucket_panos_unsecured"] == "my-bucket"
    assert after.get("region") == before_region  # sibling untouched
