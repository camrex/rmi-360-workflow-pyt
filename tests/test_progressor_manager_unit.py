import pytest
from unittest.mock import patch, MagicMock
from utils.manager.progressor_manager import ProgressorManager

class DummyLogManager:
    def __init__(self):
        self.warnings = []
    def warning(self, msg):
        self.warnings.append(msg)


def test_context_manager_success():
    with patch("utils.manager.progressor_manager.arcpy") as mock_arcpy:
        mock_arcpy.SetProgressor = MagicMock()
        log = DummyLogManager()
        with ProgressorManager(total=5, label="Test", log_manager=log) as prog:
            assert prog.use_progressor is True
            mock_arcpy.SetProgressor.assert_called_once()
            assert prog.label == "Test"
            assert prog.total == 5


def test_context_manager_fallback_on_arcpy_error():
    with patch("utils.manager.progressor_manager.arcpy") as mock_arcpy:
        mock_arcpy.SetProgressor.side_effect = Exception("ArcPy fail")
        log = DummyLogManager()
        with ProgressorManager(total=5, label="Test", log_manager=log) as prog:
            assert prog.use_progressor is False
            assert any("ArcPy fail" in w for w in log.warnings)


def test_context_manager_zero_total():
    log = DummyLogManager()
    with ProgressorManager(total=0, label="Nothing", log_manager=log) as prog:
        assert prog.use_progressor is False
        assert prog.completed == 0


def test_update_progressor_and_cli(monkeypatch, capfd):
    # Test ArcPy progressor update
    with patch("utils.manager.progressor_manager.arcpy") as mock_arcpy:
        mock_arcpy.SetProgressor = MagicMock()
        mock_arcpy.SetProgressorLabel = MagicMock()
        mock_arcpy.SetProgressorPosition = MagicMock()
        with ProgressorManager(total=10, label="Test") as prog:
            prog.use_progressor = True
            prog.update(3, label="Step 3")
            mock_arcpy.SetProgressorLabel.assert_called_with("Step 3")
            mock_arcpy.SetProgressorPosition.assert_called_with(3)
    # Test CLI fallback
    with ProgressorManager(total=10, label="Test") as prog:
        prog.use_progressor = False
        prog.update(5)
        out = capfd.readouterr().out
        assert "50.0%" in out


def test_update_label_only(monkeypatch, capfd):
    with ProgressorManager(total=4, label="Init") as prog:
        prog.use_progressor = False
        prog.update(2, label="Halfway")
        out = capfd.readouterr().out
        assert "Halfway" in out


def test_exit_resets_progressor():
    with patch("utils.manager.progressor_manager.arcpy") as mock_arcpy:
        mock_arcpy.ResetProgressor = MagicMock()
        with ProgressorManager(total=2, label="Done") as prog:
            prog.use_progressor = True
        mock_arcpy.ResetProgressor.assert_called_once()
