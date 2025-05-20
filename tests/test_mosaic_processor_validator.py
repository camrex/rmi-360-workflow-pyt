import pytest
from unittest.mock import MagicMock, patch

# Import the validator function
from utils.validators import mosaic_processor_validator

@pytest.fixture
def mock_cfg():
    mock = MagicMock()
    mock.get_logger.return_value = MagicMock()
    mock.get.side_effect = lambda k, d=None: {
        "executables.mosaic_processor": {
            "cfg_path": "some/path/to/config.cfg"
        },
        "executables.mosaic_processor.cfg_path": "some/path/to/config.cfg"
    }.get(k, d)
    mock.paths.validate_mosaic_config.return_value = True
    mock.paths.check_mosaic_processor_available.return_value = True
    return mock


def test_validator_success(mock_cfg):
    """Test validator returns True with valid config and paths."""
    assert mosaic_processor_validator.validate(mock_cfg) is True


def test_validator_missing_mp_cfg(mock_cfg):
    """Test validator returns False if mosaic_processor config is missing or wrong type."""
    mock_cfg.get.side_effect = lambda k, d=None: {} if k == "executables.mosaic_processor" else d
    assert mosaic_processor_validator.validate(mock_cfg) is False
    

def test_validator_invalid_cfg_path_type(mock_cfg):
    """Test validator returns False if cfg_path is not a string."""
    mock_cfg.get.side_effect = lambda k, d=None: {
        "executables.mosaic_processor": {"cfg_path": 123},
        "executables.mosaic_processor.cfg_path": 123
    }.get(k, d)
    assert mosaic_processor_validator.validate(mock_cfg) is False


def test_validator_empty_cfg_path(mock_cfg):
    """Test validator returns False if cfg_path is an empty string."""
    mock_cfg.get.side_effect = lambda k, d=None: {
        "executables.mosaic_processor": {"cfg_path": "   "},
        "executables.mosaic_processor.cfg_path": "   "
    }.get(k, d)
    assert mosaic_processor_validator.validate(mock_cfg) is False


def test_validator_invalid_mosaic_config(mock_cfg):
    """Test validator returns False if validate_mosaic_config fails."""
    mock_cfg.paths.validate_mosaic_config.return_value = False
    assert mosaic_processor_validator.validate(mock_cfg) is False


def test_validator_mosaic_processor_not_available(mock_cfg):
    """Test validator returns False if check_mosaic_processor_available fails."""
    mock_cfg.paths.check_mosaic_processor_available.return_value = False
    assert mosaic_processor_validator.validate(mock_cfg) is False


def test_validator_logs_errors_for_invalid_config(mock_cfg):
    """Test that logger.error is called for invalid config cases."""
    logger = mock_cfg.get_logger.return_value
    mock_cfg.get.side_effect = lambda k, d=None: {
        "executables.mosaic_processor": {"cfg_path": ""},
        "executables.mosaic_processor.cfg_path": ""
    }.get(k, d)
    mosaic_processor_validator.validate(mock_cfg)
    logger.error.assert_called()  # Should log error for empty cfg_path
