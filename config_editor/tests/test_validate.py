from config_editor.core import config_io as cio
from config_editor.core import paths, validate


def test_read_supported_versions_from_source():
    versions = validate.read_supported_versions()
    assert "1.4.0" in versions          # the current (clean-break) version


def _sample_values():
    return cio.extract_values(cio.load_yaml(paths.sample_config_path()))


def test_sample_validates_clean_except_placeholders():
    values = _sample_values()
    skeleton = values  # validating the sample against itself
    issues = validate.validate_structure(values, skeleton)
    # No structural errors (schema_version is supported, all sections present).
    assert not validate.has_errors(issues)
    # The sample DOES carry <PLACEHOLDER> values -> warnings, not errors.
    assert any(i.level == "warning" and "placeholder" in i.message.lower() for i in issues)


def test_missing_section_is_error():
    skeleton = {"schema_version": "1.3.5", "aws": {"region": "x"}, "portal": {}}
    values = {"schema_version": "1.3.5", "aws": {"region": "y"}}  # portal missing
    issues = validate.validate_structure(values, skeleton, supported_versions={"1.3.5"})
    assert any(i.level == "error" and i.path == "portal" for i in issues)


def test_unknown_section_is_warning():
    skeleton = {"schema_version": "1.3.5", "aws": {}}
    values = {"schema_version": "1.3.5", "aws": {}, "bogus": {"k": 1}}
    issues = validate.validate_structure(values, skeleton, supported_versions={"1.3.5"})
    assert any(i.level == "warning" and i.path == "bogus" for i in issues)


def test_unsupported_version_is_error():
    skeleton = {"schema_version": "1.3.5"}
    values = {"schema_version": "0.9.0"}
    issues = validate.validate_structure(values, skeleton, supported_versions={"1.3.5"})
    assert any(i.level == "error" and i.path == "schema_version" for i in issues)


def test_placeholder_detection():
    skeleton = {"schema_version": "1.4.0", "aws": {"s3_bucket_panos_unsecured": "x"}}
    values = {"schema_version": "1.4.0", "aws": {"s3_bucket_panos_unsecured": "<YOUR_S3_BUCKET_NAME>"}}
    issues = validate.validate_structure(values, skeleton, supported_versions={"1.4.0"})
    assert any(i.path == "aws.s3_bucket_panos_unsecured" and i.level == "warning" for i in issues)
