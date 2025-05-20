import pytest
from unittest.mock import patch, MagicMock
from utils.validators import assign_group_index_validator as validator

@pytest.fixture
def mock_cfg():
    cfg = MagicMock()
    cfg.get_logger.return_value = MagicMock()
    return cfg

def test_validator_success(mock_cfg):
    grp_idx = {"group_index": {"name": "GroupIndex", "type": "Integer"}}
    mock_cfg.get.return_value = grp_idx
    with patch("utils.validators.assign_group_index_validator.validate_type", return_value=True), \
         patch("utils.validators.assign_group_index_validator.validate_field_block", return_value=True):
        assert validator.validate(mock_cfg)

def test_validator_missing_grp_idx(mock_cfg):
    mock_cfg.get.return_value = None
    with patch("utils.validators.assign_group_index_validator.validate_type", return_value=False):
        assert validator.validate(mock_cfg) is False

def test_validator_field_block_invalid(mock_cfg):
    grp_idx = {"group_index": {"name": "GroupIndex", "type": "Integer"}}
    mock_cfg.get.return_value = grp_idx
    with patch("utils.validators.assign_group_index_validator.validate_type", return_value=True), \
         patch("utils.validators.assign_group_index_validator.validate_field_block", return_value=False):
        assert not validator.validate(mock_cfg)
