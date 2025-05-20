from utils import gather_metrics

def make_fake_cursor(rows):
    class FakeCursor:
        def __init__(self, rows, *args):
            self._rows = rows
        def __enter__(self):
            return iter(self._rows)
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
    return lambda path, fields: FakeCursor(rows)

def test_collect_oid_metrics_basic():
    rows = [
        (1.1, 5, None, 'A', 0),
        (2.2, 5, None, 'A', 1),
        (3.3, 5, None, 'B', 0),
        (None, 5, None, None, None),
        (4.4, 5, '2025-01-01', 'A', 2)
    ]
    cursor_factory = make_fake_cursor(rows)
    result = gather_metrics.collect_oid_metrics('dummy', cursor_factory=cursor_factory)
    assert sorted(result['mp_values']) == [1.1, 2.2, 3.3, 4.4]
    assert set(result['reel_data'].keys()) == {'A', 'B'}
    assert result['reel_data']['A']['frames'] == [0, 1, 2]
    assert result['reel_data']['B']['frames'] == [0]

from unittest.mock import MagicMock

def test_collect_oid_metrics_error():
    def bad_cursor_factory(path, fields):
        raise RuntimeError('fail')
    logger = MagicMock()
    result = gather_metrics.collect_oid_metrics('dummy', cursor_factory=bad_cursor_factory, logger=logger)
    assert result['mp_values'] == []
    assert result['acq_dates'] == []
    assert result['reel_data'] == {}
    assert logger.error.called

def test_summarize_oid_metrics_empty():
    metrics = {'mp_values': [], 'acq_dates': [], 'reel_data': {}}
    summary, reels = gather_metrics.summarize_oid_metrics(metrics)
    assert summary['total_images'] == 0
    assert summary['mp_min'] == '—'
    assert reels == []

def test_summarize_oid_metrics_normal():
    import datetime
    metrics = {
        'mp_values': [1.0, 2.0, 3.0, 2.0],
        'acq_dates': [datetime.datetime(2024, 1, 1, 10, 0, 0), datetime.datetime(2024, 1, 1, 12, 0, 0)],
        'reel_data': {
            'A': {'frames': [0, 1, 1], 'dates': [datetime.datetime(2024, 1, 1, 10, 0, 0)]},
            'B': {'frames': [0, 2], 'dates': [datetime.datetime(2024, 1, 1, 12, 0, 0)]},
        }
    }
    summary, reels = gather_metrics.summarize_oid_metrics(metrics)
    assert summary['total_images'] == 4
    assert summary['mp_min'] == 1.0
    assert summary['mp_max'] == 3.0
    assert summary['mp_delta'] == 2.0
    assert summary['acq_start'] == '2024-01-01 10:00:00'
    assert summary['acq_end'] == '2024-01-01 12:00:00'
    assert any(r['reel'] == '000A' and r['image_count'] == 2 for r in reels)
    assert any(r['reel'] == '000B' and r['image_count'] == 2 for r in reels)

def test_summarize_oid_metrics_reel_missing_frames():
    import datetime
    metrics = {
        'mp_values': [1.0],
        'acq_dates': [datetime.datetime(2024, 1, 1, 10, 0, 0)],
        'reel_data': {
            'A': {'frames': [], 'dates': []},
        }
    }
    summary, reels = gather_metrics.summarize_oid_metrics(metrics)
    assert reels[0]['image_count'] == 0
