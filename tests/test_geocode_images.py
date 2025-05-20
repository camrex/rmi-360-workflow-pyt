from unittest.mock import MagicMock
from utils.geocode_images import get_exiftool_cmd, build_geocode_args_and_log

def test_get_exiftool_cmd_default():
    cfg = MagicMock()
    logger = MagicMock()
    cfg.get.side_effect = lambda k, d=None: {"geocoding.method": "exiftool", "geocoding.exiftool_geodb": "default"}.get(k, d)
    cfg.paths.geoloc500_config_path = "/tmp/geo500.cfg"
    cfg.paths.geocustom_config_path = "/tmp/geocustom.cfg"
    cmd = get_exiftool_cmd(cfg, logger)
    assert cmd == ["exiftool"]

def test_get_exiftool_cmd_geolocation500():
    cfg = MagicMock()
    logger = MagicMock()
    cfg.get.side_effect = lambda k, d=None: {"geocoding.method": "exiftool", "geocoding.exiftool_geodb": "geolocation500"}.get(k, d)
    cfg.paths.geoloc500_config_path = MagicMock()
    cfg.paths.geoloc500_config_path.resolve.return_value = "/tmp/geo500.cfg"
    cfg.paths.geocustom_config_path = MagicMock()
    cmd = get_exiftool_cmd(cfg, logger)
    assert cmd == ["exiftool", "-config", "/tmp/geo500.cfg"]

def test_build_geocode_args_and_log(tmp_path):
    logger = MagicMock()
    img = tmp_path / "img1.jpg"
    img.write_text("foo")
    rows = [(123, str(img), 1.1, 2.2), (456, str(tmp_path/"missing.jpg"), 3.3, 4.4)]
    args, logs = build_geocode_args_and_log(rows, logger)
    assert any("img1.jpg" in a for a in args)
    assert any("Geocoded OID 123" in log_entry for log_entry in logs)
    # Should warn for missing.jpg
    logger.warning.assert_called_with(f"Image path does not exist: {tmp_path/ 'missing.jpg'}")
