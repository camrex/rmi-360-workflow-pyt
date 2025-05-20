import pytest
from unittest.mock import MagicMock
from utils.validators.calculate_oid_attributes_validator import validate

@pytest.fixture
def mock_cfg():
    cfg = MagicMock()
    cfg.get_logger.return_value = MagicMock()
    return cfg

def test_validator_success(monkeypatch, mock_cfg):
    # Simulate config with all required fields and correct types/defaults
    mock_cfg.get.side_effect = lambda k, d=None: {
        "oid_schema_template": {
            "esri_default": {},
            "mosaic_fields": {
                "mosaic_reel": {"name": "mosaic_reel"},
                "mosaic_frame": {"name": "mosaic_frame"}
            },
            "linear_ref_fields": {
                "route_identifier": {"name": "route_identifier"},
                "route_measure": {"name": "route_measure"}
            }
        },
        "camera_offset": {"z": {"a": 10}, "camera_height": {"a": 150}},
        "spatial_ref": {"gcs_horizontal_wkid": 4326, "vcs_vertical_wkid": 5703}
    }.get(k, d)
    monkeypatch.setattr("utils.validators.calculate_oid_attributes_validator.load_field_registry", lambda cfg: {
        "CameraPitch": {"name": "CameraPitch", "oid_default": 90, "category": "standard"},
        "CameraRoll": {"name": "CameraRoll", "oid_default": 0, "category": "standard"},
        "NearDistance": {"name": "NearDistance", "oid_default": 2, "category": "standard"},
        "FarDistance": {"name": "FarDistance", "oid_default": 50, "category": "standard"},
        "CameraHeight": {"name": "CameraHeight", "oid_default": 1.5, "category": "standard"},
        "SRS": {"name": "SRS", "category": "standard"},
        "X": {"name": "X", "category": "standard"},
        "Y": {"name": "Y", "category": "standard"},
        "Z": {"name": "Z", "category": "standard"},
        "CameraOrientation": {"name": "CameraOrientation", "category": "standard", "orientation_format": "type1_short"},
        "CameraHeading": {"name": "CameraHeading", "category": "standard"},
        "ImagePath": {"name": "ImagePath", "category": "standard"},
    })
    monkeypatch.setattr("utils.validators.calculate_oid_attributes_validator.validate_field_block", lambda *a, **kw: True)
    monkeypatch.setattr("utils.validators.calculate_oid_attributes_validator.validate_type", lambda *a, **kw: True)
    monkeypatch.setattr("utils.validators.calculate_oid_attributes_validator.validate_config_section", lambda *a, **kw: True)
    monkeypatch.setattr("utils.validators.calculate_oid_attributes_validator.validate_expression_block", lambda *a, **kw: True)
    assert validate(mock_cfg) is True

def test_validator_missing_required_field(monkeypatch, mock_cfg):
    # Simulate config missing CameraHeading in registry
    mock_cfg.get.side_effect = lambda k, d=None: {
        "oid_schema_template": {
            "esri_default": {},
            "mosaic_fields": {"Reel": {"name": "Reel"}, "Frame": {"name": "Frame"}}
        },
        "camera_offset": {"z": {"a": 10}, "camera_height": {"a": 150}},
        "spatial_ref": {"gcs_horizontal_wkid": 4326, "vcs_vertical_wkid": 5703}
    }.get(k, d)
    monkeypatch.setattr("utils.validators.calculate_oid_attributes_validator.load_field_registry", lambda cfg: {

        "CameraPitch": {"name": "CameraPitch", "oid_default": 90, "category": "standard"},
        "CameraRoll": {"name": "CameraRoll", "oid_default": 0, "category": "standard"},
        # "CameraHeading" is missing
        "NearDistance": {"name": "NearDistance", "oid_default": 2, "category": "standard"}
    })
    assert validate(mock_cfg) is False

def test_validator_bad_type(monkeypatch, mock_cfg):
    # Simulate config with wrong type for camera_offset.z
    mock_cfg.get.side_effect = lambda k, d=None: {
        "oid_schema_template": {
            "esri_default": {},
            "mosaic_fields": {"Reel": {"name": "Reel"}, "Frame": {"name": "Frame"}}
        },
        "camera_offset": {"z": "not_a_dict", "camera_height": {"a": 150}},
        "spatial_ref": {"gcs_horizontal_wkid": 4326, "vcs_vertical_wkid": 5703}
    }.get(k, d)
    monkeypatch.setattr("utils.validators.calculate_oid_attributes_validator.load_field_registry", lambda cfg: {

        "CameraPitch": {"name": "CameraPitch", "oid_default": 90, "category": "standard"},
        "CameraRoll": {"name": "CameraRoll", "oid_default": 0, "category": "standard"},
        "CameraHeading": {"name": "CameraHeading", "category": "standard"},
    })
    assert validate(mock_cfg) is False
