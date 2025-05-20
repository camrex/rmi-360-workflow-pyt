import pytest
import json
from unittest.mock import MagicMock, patch, mock_open
from utils import report_data_builder

def test_resolve_if_expression_literal():
    cfg = MagicMock()
    assert report_data_builder.resolve_if_expression(42, cfg) == 42
    assert report_data_builder.resolve_if_expression('foo', cfg) == 'foo'

def test_resolve_if_expression_config(monkeypatch):
    cfg = MagicMock()
    cfg.resolve.return_value = 'resolved!'
    assert report_data_builder.resolve_if_expression('config.project.name', cfg) == 'resolved!'

def test_initialize_report_data_basic():
    paths_dict = {'oid_fc': 'fc', 'input_reels_folder': 'reels'}
    cfg = MagicMock()
    cfg.get.side_effect = lambda k, d=None: {'project': {'slug': 'slug'}, 'camera': {'focal': 'config.camera.focal'}}.get(k, d)
    cfg.resolve.side_effect = lambda v: 'resolved_' + v
    cfg.paths.original = '/orig'
    cfg.paths.enhanced = '/enh'
    cfg.paths.renamed = '/ren'
    report = report_data_builder.initialize_report_data(paths_dict, cfg)
    assert report['paths']['oid_fc'] == 'fc'
    assert report['paths']['reels_input'] == 'reels'
    assert report['camera']['focal'] == 'resolved_config.camera.focal'

def test_save_report_json_success(tmp_path):
    report_data = {'foo': 1}
    cfg = MagicMock()
    cfg.get.return_value = 'sluggy'
    cfg.paths.report = tmp_path
    logger = MagicMock()
    result = report_data_builder.save_report_json(report_data, cfg, logger=logger)
    assert result == str(tmp_path / 'report_data_sluggy.json')
    with open(result, 'r') as f:
        assert json.load(f) == report_data

def test_save_report_json_failure(monkeypatch):
    report_data = {'foo': 1}
    cfg = MagicMock()
    cfg.get.return_value = 'sluggy'
    cfg.paths.report = '/nonexistent/path'
    logger = MagicMock()
    # Patch open to throw
    with patch('builtins.open', side_effect=OSError):
        result = report_data_builder.save_report_json(report_data, cfg, logger=logger)
        assert result is None
        assert logger.error.called

def test_load_report_json_if_exists_success(tmp_path):
    cfg = MagicMock()
    cfg.get.return_value = 'sluggy'
    cfg.paths.report = tmp_path
    logger = MagicMock()
    data = {'foo': 123}
    file_path = tmp_path / 'report_data_sluggy.json'
    with open(file_path, 'w') as f:
        json.dump(data, f)
    loaded = report_data_builder.load_report_json_if_exists(cfg, logger=logger)
    assert loaded == data

def test_load_report_json_if_exists_not_found(tmp_path):
    cfg = MagicMock()
    cfg.get.return_value = 'sluggy'
    cfg.paths.report = tmp_path
    logger = MagicMock()
    loaded = report_data_builder.load_report_json_if_exists(cfg, logger=logger)
    assert loaded is None

def test_load_report_json_if_exists_failure(monkeypatch, tmp_path):
    cfg = MagicMock()
    cfg.get.return_value = 'sluggy'
    cfg.paths.report = tmp_path
    logger = MagicMock()
    file_path = tmp_path / 'report_data_sluggy.json'
    file_path.write_text('not json')
    loaded = report_data_builder.load_report_json_if_exists(cfg, logger=logger)
    assert loaded is None
    assert logger.error.called
