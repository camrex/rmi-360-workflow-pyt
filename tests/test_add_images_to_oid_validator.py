import pytest
from unittest.mock import patch, MagicMock
from utils.validators import add_images_to_oid_validator as validator

@pytest.fixture
def mock_cfg():
    cfg = MagicMock()
    cfg.get_logger.return_value = MagicMock()
    cfg.paths.oid_field_registry = "mock_registry.yaml"
    return cfg

def test_validate_success(mock_cfg):
    with patch("utils.validators.add_images_to_oid_validator.check_file_exists", return_value=True), \
         patch("utils.validators.add_images_to_oid_validator.load_field_registry", return_value={"OrientedImageryType": {"oid_default": "360"}}), \
         patch("utils.validators.add_images_to_oid_validator.validate_field_block", return_value=True), \
         patch("utils.validators.add_images_to_oid_validator.validate_type", return_value=True):
        assert validator.validate(mock_cfg) is True

def test_validate_missing_registry(mock_cfg):
    with patch("utils.validators.add_images_to_oid_validator.check_file_exists", return_value=False):
        assert validator.validate(mock_cfg) is False
    mock_cfg.get_logger().error.assert_called_with("OID field registry .yaml file not found.")

def test_validate_missing_field(mock_cfg):
    with patch("utils.validators.add_images_to_oid_validator.check_file_exists", return_value=True), \
         patch("utils.validators.add_images_to_oid_validator.load_field_registry", return_value={}):
        assert validator.validate(mock_cfg) is False
    mock_cfg.get_logger().error.assert_called_with("Missing required field: OrientedImageryType", error_type=validator.ConfigValidationError)

def test_validate_invalid_type(mock_cfg):
    # oid_default is not a string
    with patch("utils.validators.add_images_to_oid_validator.check_file_exists", return_value=True), \
         patch("utils.validators.add_images_to_oid_validator.load_field_registry", return_value={"OrientedImageryType": {"oid_default": 123}}), \
         patch("utils.validators.add_images_to_oid_validator.validate_field_block", return_value=True), \
         patch("utils.validators.add_images_to_oid_validator.validate_type", return_value=False):
        assert validator.validate(mock_cfg) is False

def test_validate_invalid_default_value(mock_cfg):
    # oid_default is not in VALID_IMAGE_TYPES
    with patch("utils.validators.add_images_to_oid_validator.check_file_exists", return_value=True), \
         patch("utils.validators.add_images_to_oid_validator.load_field_registry", return_value={"OrientedImageryType": {"oid_default": "INVALID"}}), \
         patch("utils.validators.add_images_to_oid_validator.validate_field_block", return_value=True), \
         patch("utils.validators.add_images_to_oid_validator.validate_type", return_value=True):
        assert validator.validate(mock_cfg) is False
    mock_cfg.get_logger().error.assert_called()
