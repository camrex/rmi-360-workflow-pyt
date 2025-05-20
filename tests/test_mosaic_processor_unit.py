from unittest.mock import MagicMock, patch, mock_open, call
from utils import mosaic_processor

# ----------------------
# Test build_mosaic_command
# ----------------------
def test_build_mosaic_command_basic():
    cmd = mosaic_processor.build_mosaic_command(
        exe_path='mp.exe',
        input_dir='input',
        output_dir='output',
        grp_path='calib.grp',
        start_frame=1,
        end_frame=10,
        skip_gpx=True,
        skip_render=False,
        skip_reel_fix=True,
        wrap_in_shell=False
    )
    assert 'mp.exe' in cmd
    assert '--output_dir' in cmd
    assert '--grp_path' in cmd
    assert '--start_frame' in cmd
    assert '--end_frame' in cmd
    assert '--no_gpx_integration' in cmd
    assert '--no_reel_fixing' in cmd
    assert '--no_render' not in cmd


def test_build_mosaic_command_shell_wrap():
    cmd = mosaic_processor.build_mosaic_command(
        exe_path='C:/Program Files/mp.exe',
        input_dir='input',
        output_dir='output',
        grp_path='calib.grp',
        wrap_in_shell=True
    )
    assert cmd.startswith('cmd /c')
    assert '"C:/Program Files/mp.exe"' in cmd

# ----------------------
# Test pad_frame_numbers
# ----------------------
@patch('os.rename')
@patch('os.walk')
def test_pad_frame_numbers_renames_files(mock_walk, mock_rename):
    mock_walk.return_value = [
        ('output_dir', [], ['reel_1.jpg', 'reel_2.jpg', 'reel_10.jpg'])
    ]
    logger = MagicMock()
    output_dir = 'output_dir'
    count = mosaic_processor.pad_frame_numbers(output_dir, logger)
    assert count == 3
    assert mock_rename.call_count == 3
    logger.info.assert_called()

# ----------------------
# Test run_processor_stage
# ----------------------
@patch('subprocess.run')
def test_run_processor_stage_success(mock_run):
    mock_run.return_value.returncode = 0
    cfg = MagicMock()
    input_dir = 'input'
    output_dir = 'output'
    log_f = MagicMock()
    log_path = 'log.txt'
    stage_name = 'Render + Reel Fix'
    result = mosaic_processor.run_processor_stage(
        cfg, input_dir, output_dir, 1, 10, log_f, log_path, stage_name,
        skip_render=False, skip_reel_fix=False, skip_gpx=False
    )
    assert result is True


@patch('subprocess.run')
def test_run_processor_stage_failure(mock_run):
    mock_run.return_value.returncode = 1
    cfg = MagicMock()
    input_dir = 'input'
    output_dir = 'output'
    log_f = MagicMock()
    log_path = 'log.txt'
    stage_name = 'Render + Reel Fix'
    result = mosaic_processor.run_processor_stage(
        cfg, input_dir, output_dir, 1, 10, log_f, log_path, stage_name,
        skip_render=False, skip_reel_fix=False, skip_gpx=False
    )
    assert result is False

# ----------------------
# Test run_mosaic_processor (integration)
# ----------------------
@patch('os.makedirs')
@patch('builtins.open', new_callable=mock_open)
@patch('os.rename')
@patch('os.walk')
@patch('subprocess.run')
def test_run_mosaic_processor_happy_path(mock_run, mock_walk, mock_rename, mock_open_fn, mock_makedirs):
    # Setup subprocess to succeed for all stages
    mock_run.return_value.returncode = 0
    mock_walk.return_value = [
        ('output_dir', [], ['reel_1.jpg', 'reel_2.jpg'])
    ]
    cfg = MagicMock()
    cfg.get_logger.return_value = MagicMock()
    cfg.get.side_effect = lambda k, d=None: {
        'executables.mosaic_processor.grp_path': 'grp.grp',
        'executables.mosaic_processor.exe_path': 'mp.exe',
        'executables.mosaic_processor.cfg_path': 'mp.cfg',
        'logs.process_log': 'log.txt'
    }.get(k, d)
    cfg.validate.return_value = True
    cfg.paths.mosaic_processor_grp = MagicMock()
    cfg.paths.mosaic_processor_exe = MagicMock()
    cfg.paths.mosaic_processor_cfg = MagicMock()
    result = mosaic_processor.run_mosaic_processor(cfg, 'input', 1, 10)
    assert result is None  # The function does not return, just completes
    assert mock_run.call_count >= 1
    assert mock_open_fn.call_count >= 1
    assert mock_rename.call_count == 2
