import pytest
from unittest.mock import MagicMock, patch
from utils.correct_gps_outliers import interpolate_gps_outliers, correct_gps_outliers

@pytest.fixture
def sample_rows():
    # 6 points: 0 and 5 are anchors, 1-2 and 3-4 are two outlier sequences
    return [
        {'oid': 1, 'qcflag': None, 'x': 0, 'y': 0, 'z': 10, 'heading': 0, 'pitch': 0, 'roll': 0, 'orientation': '', 'xy': (0,0)},
        {'oid': 2, 'qcflag': 'GPS_OUTLIER', 'x': 0, 'y': 0, 'z': 10, 'heading': 0, 'pitch': 0, 'roll': 0, 'orientation': '', 'xy': (0,0)},
        {'oid': 3, 'qcflag': 'GPS_OUTLIER', 'x': 0, 'y': 0, 'z': 10, 'heading': 0, 'pitch': 0, 'roll': 0, 'orientation': '', 'xy': (0,0)},
        {'oid': 4, 'qcflag': 'GPS_OUTLIER', 'x': 0, 'y': 0, 'z': 10, 'heading': 0, 'pitch': 0, 'roll': 0, 'orientation': '', 'xy': (0,0)},
        {'oid': 5, 'qcflag': 'GPS_OUTLIER', 'x': 0, 'y': 0, 'z': 10, 'heading': 0, 'pitch': 0, 'roll': 0, 'orientation': '', 'xy': (0,0)},
        {'oid': 6, 'qcflag': None, 'x': 10, 'y': 0, 'z': 10, 'heading': 0, 'pitch': 0, 'roll': 0, 'orientation': '', 'xy': (10,0)},
    ]

def test_interpolate_gps_outliers_basic(sample_rows):
    # Should interpolate positions for oids 2,3,4,5 between anchors 1 and 6
    rows, corrected = interpolate_gps_outliers(
        [dict(r) for r in sample_rows],
        default_h_wkid=4326,
        default_v_wkid=5703,
        logger=None
    )
    # OIDs 2,3,4,5 should be corrected
    assert corrected == {2,3,4,5}
    # Check interpolated positions
    xs = [rows[i]['x'] for i in range(1,5)]
    ys = [rows[i]['y'] for i in range(1,5)]
    # Should be evenly distributed between 0 and 10
    assert xs == pytest.approx([2,4,6,8])
    assert all(y == 0 for y in ys)
    # Orientation string should be updated
    for i in range(1,5):
        assert '4326' in rows[i]['orientation']
        assert '5703' in rows[i]['orientation']

def test_interpolate_gps_outliers_skips_edges(sample_rows):
    # Mark first and last as outliers (should be skipped)
    rows = [dict(r) for r in sample_rows]
    rows[0]['qcflag'] = 'GPS_OUTLIER'
    rows[-1]['qcflag'] = 'GPS_OUTLIER'
    result_rows, corrected = interpolate_gps_outliers(
        rows,
        default_h_wkid=4326,
        default_v_wkid=5703,
        logger=None
    )
    # No correction for edge outliers
    assert 1 not in corrected
    assert 6 not in corrected

@patch('arcpy.da.UpdateCursor')
@patch('arcpy.da.SearchCursor')
@patch('utils.correct_gps_outliers.interpolate_gps_outliers')
def test_correct_gps_outliers_main_logic(mock_interpolate, mock_search, mock_update):
    # Setup mocks
    mock_logger = MagicMock()
    mock_cfg = MagicMock()
    mock_cfg.get_logger.return_value = mock_logger
    mock_cfg.get.side_effect = lambda k, d=None: {"spatial_ref.gcs_horizontal_wkid": 4326, "spatial_ref.vcs_vertical_wkid": 5703}.get(k, d)
    mock_cfg.get_progressor.side_effect = lambda total, label: MagicMock(__enter__=lambda s: s, __exit__=lambda s, exc_type, exc_val, exc_tb: None, update=lambda x: None)
    mock_cfg.validate.return_value = True
    # Simulate rows and corrections
    mock_rows = [
        {'oid': 1, 'qcflag': None, 'x': 0, 'y': 0, 'z': 10, 'heading': 0, 'pitch': 0, 'roll': 0, 'orientation': '', 'xy': (0,0)},
        {'oid': 2, 'qcflag': 'GPS_OUTLIER', 'x': 0, 'y': 0, 'z': 10, 'heading': 0, 'pitch': 0, 'roll': 0, 'orientation': '', 'xy': (0,0)},
        {'oid': 3, 'qcflag': None, 'x': 10, 'y': 0, 'z': 10, 'heading': 0, 'pitch': 0, 'roll': 0, 'orientation': '', 'xy': (10,0)},
    ]
    mock_interpolate.return_value = (mock_rows, {2})
    mock_search.return_value.__enter__.return_value = [
        (1, None, (0,0), '', 0, 0, 0, 10, 0, 0),
        (2, 'GPS_OUTLIER', (0,0), '', 0, 0, 0, 10, 0, 0),
        (3, None, (10,0), '', 0, 0, 0, 10, 10, 0),
    ]
    mock_update.return_value.__enter__.return_value = [
        [1, None, (0,0), '', 0, 0, 0, 10, 0, 0],
        [2, 'GPS_OUTLIER', (0,0), '', 0, 0, 0, 10, 0, 0],
        [3, None, (10,0), '', 0, 0, 0, 10, 10, 0],
    ]
    correct_gps_outliers(mock_cfg, 'fake_oid_fc')
    mock_cfg.validate.assert_called_with(tool="correct_gps_outliers")
    mock_interpolate.assert_called()
    # Should log corrected OIDs
    assert mock_logger.info.called
    assert mock_logger.debug.called
