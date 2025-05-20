import pytest
from unittest.mock import MagicMock, patch

from utils.smooth_gps_noise import smooth_gps_noise

@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.get_logger.return_value = MagicMock()
    gps_smoothing = {
        "capture_spacing_meters": 5.0,
        "deviation_threshold_m": 0.5,
        "angle_bounds_deg": [175, 185],
        "proximity_check_range_m": 0.75,
        "max_route_dist_deviation_m": 0.5,
        "smoothing_window": 1,
        "outlier_reason_threshold": 2
    }
    def get_side_effect(key, default=None):
        if key == "gps_smoothing":
            return gps_smoothing
        elif key.startswith("gps_smoothing."):
            subkey = key.split(".", 1)[1]
            return gps_smoothing.get(subkey, default)
        return default
    cfg.get.side_effect = get_side_effect
    cfg.paths.get_log_file_path.return_value = "mock_debug.csv"
    cfg.validate.return_value = True
    cfg.get_progressor.side_effect = lambda total, label: MagicMock(__enter__=lambda s: s, __exit__=lambda s, exc_type, exc_val, exc_tb: None, update=lambda x: None)
    return cfg

@patch('arcpy.da.SearchCursor')
@patch('arcpy.ListFields')
@patch('arcpy.management.AddField')
@patch('arcpy.da.UpdateCursor')
def test_smooth_gps_noise_basic(mock_update_cursor, mock_add_field, mock_list_fields, mock_search_cursor, mock_config):
    # Setup fake points
    mock_oid = MagicMock()
    mock_oid.name = 'OID@'
    mock_qcflag = MagicMock()
    mock_qcflag.name = 'QCFlag'
    mock_list_fields.return_value = [mock_oid, mock_qcflag]
    # Simulate two points in a reel
    mock_search_cursor.return_value.__enter__.return_value = iter([
        (1, MagicMock(centroid=MagicMock(X=0, Y=0, Z=0)), '2025-01-01T00:00:00', 'A'),
        (2, MagicMock(centroid=MagicMock(X=0, Y=1, Z=0)), '2025-01-01T00:01:00', 'A'),
    ])
    mock_update_cursor.return_value.__enter__.return_value = iter([
        [1, None],
        [2, None],
    ])

    # Should run without error
    smooth_gps_noise(mock_config, 'fake_oid_fc')
    mock_config.validate.assert_called_with(tool="smooth_gps_noise")
    mock_add_field.assert_not_called()  # QCFlag already present
    # Would check update calls here if needed

@patch('arcpy.da.SearchCursor')
@patch('arcpy.ListFields')
@patch('arcpy.management.AddField')
@patch('arcpy.da.UpdateCursor')
def test_smooth_gps_noise_adds_qcflag(mock_update_cursor, mock_add_field, mock_list_fields, mock_search_cursor, mock_config):
    # Simulate missing QCFlag
    mock_oid = MagicMock()
    mock_oid.name = 'OID@'
    mock_list_fields.return_value = [mock_oid]
    mock_search_cursor.return_value.__enter__.return_value = iter([
        (1, MagicMock(centroid=MagicMock(X=0, Y=0, Z=0)), '2025-01-01T00:00:00', 'A'),
        (2, MagicMock(centroid=MagicMock(X=0, Y=1, Z=0)), '2025-01-01T00:01:00', 'A'),
    ])
    mock_update_cursor.return_value.__enter__.return_value = iter([
        [1, None],
        [2, None],
    ])

    smooth_gps_noise(mock_config, 'fake_oid_fc')
    mock_add_field.assert_called_once_with('fake_oid_fc', 'QCFlag', 'TEXT', field_length=50)

@patch('arcpy.da.SearchCursor')
@patch('arcpy.ListFields')
@patch('arcpy.management.AddField')
@patch('arcpy.da.UpdateCursor')
def test_smooth_gps_noise_handles_empty(mock_update_cursor, mock_add_field, mock_list_fields, mock_search_cursor, mock_config):
    # No points in feature class
    mock_oid = MagicMock()
    mock_oid.name = 'OID@'
    mock_qcflag = MagicMock()
    mock_qcflag.name = 'QCFlag'
    mock_list_fields.return_value = [mock_oid, mock_qcflag]
    mock_search_cursor.return_value.__enter__.return_value = iter([])
    mock_update_cursor.return_value.__enter__.return_value = iter([])

    smooth_gps_noise(mock_config, 'fake_oid_fc')
    mock_add_field.assert_not_called()  # QCFlag already present
    # Should log 'No outlier flags to apply.'
