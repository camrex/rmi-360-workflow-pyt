from unittest.mock import MagicMock, patch
from utils.enhance_images import enhance_images_in_oid  # Used indirectly in line 59

def test_process_images_in_parallel_logic(monkeypatch):
    # Import the helper from the module (now defined inside enhance_images_in_oid)
    import utils.enhance_images as enh
    # Mock enhance_single_image to just return a dummy result
    def dummy_enhance_single_image(p, cfg, logger):
        # Use the input path as the key to ensure unique entries
        return ([str(p), f"enh_{p}", [str(p), 10, 20, 0, 0, 0, 0, 15, 25], False], None)
    monkeypatch.setattr(enh, "enhance_single_image", dummy_enhance_single_image)
    # Prepare dummy progressor
    class DummyProgressor:
        def update(self, idx): pass
    # Call the helper
    paths = ["img1.jpg", "img2.jpg"]
    cfg = MagicMock()
    logger = MagicMock()
    max_workers = 2
    progressor = DummyProgressor()
    from utils.enhance_images import process_images_in_parallel
    path_map, log_rows, brightness_deltas, contrast_deltas, failed_exif_copies = process_images_in_parallel(
        paths, cfg, logger, max_workers, progressor)
    assert len(path_map) == 2
    assert all(isinstance(row, list) for row in log_rows)
    assert all(isinstance(d, float) for d in brightness_deltas)
    assert all(isinstance(d, float) for d in contrast_deltas)
    assert failed_exif_copies == []

@patch('arcpy.da.SearchCursor')
@patch('utils.enhance_images.process_images_in_parallel')
def test_enhance_images_in_oid_runs(mock_process, mock_search):
    # Setup dummy config and logger
    mock_logger = MagicMock()
    mock_cfg = MagicMock()
    mock_cfg.get_logger.return_value = mock_logger
    # Return correct config values for all keys used in enhance_images_in_oid
    def get_side_effect(key, default=None):
        if key == "image_enhancement.enabled":
            return True
        if key == "image_enhancement.output.mode":
            return "directory"
        if key == "image_enhancement.max_workers":
            return 2
        return default
    mock_cfg.get.side_effect = get_side_effect
    mock_cfg.get_progressor.side_effect = lambda total, label: MagicMock(__enter__=lambda s: s, __exit__=lambda s, exc_type, exc_val, exc_tb: None, update=lambda x: None)
    mock_cfg.validate.return_value = True
    # Patch out disk space, write_log, update_oid_image_paths, and enhancement logic
    import utils.enhance_images as enh
    enh.check_sufficient_disk_space = lambda oid_fc_path, cfg: None
    enh.write_log = lambda log_rows, cfg, logger: None
    enh.update_oid_image_paths = lambda oid_fc_path, path_map, logger: None
    mock_process.return_value = ({"img1.jpg": "enh1.jpg"}, [["img1.jpg", 10, 20, 0, 0, 0, 0, 15, 25]], [5.0], [5.0], [])
    mock_search.return_value.__enter__.return_value = [["img1.jpg"]]
    result = enh.enhance_images_in_oid(mock_cfg, "fake_oid_fc")
    assert result == {"img1.jpg": "enh1.jpg"}
