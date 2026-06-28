from config_editor.core import config_io as cio
from config_editor.core import migrate, paths

SKELETON = """\
schema_version: "2.0.0"
a: 1                 # alpha
b:
  x: 10              # bx
  y: 20              # by
new_section:
  k: "default"       # newly added key
"""


def _write(tmp_path, text, name="skel.yaml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_upgrade_merges_values_adds_new_renames(tmp_path):
    skel = _write(tmp_path, SKELETON)
    old = {
        "schema_version": "1.0.0",
        "a": 99,
        "b": {"x": 11},          # y missing -> filled from skeleton default
        "old_section": {"z": 5}, # to be renamed into b.y
    }
    rules = [{"op": "rename", "from": "old_section.z", "to": "b.y"}]

    result = migrate.upgrade(old, target_skeleton_path=skel, rules=rules)
    values = cio.extract_values(result.config)

    assert values["schema_version"] == "2.0.0"           # adopts target version
    assert values["a"] == 99                              # carried over
    assert values["b"]["x"] == 11                         # carried over
    assert values["b"]["y"] == 5                          # renamed in
    assert values["new_section"]["k"] == "default"        # added from skeleton
    assert "old_section" not in values                    # emptied + pruned

    rep = result.report
    assert rep.source_version == "1.0.0" and rep.target_version == "2.0.0"
    assert "new_section.k" in rep.added_keys
    assert "old_section.z -> b.y" in rep.renamed
    assert rep.removed_keys == []                          # z was renamed, not lost


def test_upgrade_reports_removed_key(tmp_path):
    skel = _write(tmp_path, SKELETON)
    old = {"schema_version": "1.0.0", "a": 1, "b": {"x": 1, "y": 2}, "gone": {"deep": 7}}
    result = migrate.upgrade(old, target_skeleton_path=skel)
    assert "gone.deep" in result.report.removed_keys


def test_upgrade_preserves_comments(tmp_path):
    skel = _write(tmp_path, SKELETON)
    old = {"schema_version": "1.0.0", "a": 42}
    result = migrate.upgrade(old, target_skeleton_path=skel)
    out = cio.dump_yaml_str(result.config)
    assert "# alpha" in out and "# newly added key" in out
    assert "a: 42" in out


def test_upgrade_against_real_sample_sets_current_version():
    # Old config missing many of today's keys should upgrade cleanly to the sample's version.
    old = {"schema_version": "1.3.1", "project": {"slug": "OLD"}}
    result = migrate.upgrade(old, target_skeleton_path=paths.sample_config_path())
    values = cio.extract_values(result.config)
    sample_version = cio.extract_values(cio.load_yaml(paths.sample_config_path()))["schema_version"]
    assert values["schema_version"] == sample_version
    assert values["project"]["slug"] == "OLD"            # user value preserved
    assert len(result.report.added_keys) > 20            # lots of new keys filled with defaults
