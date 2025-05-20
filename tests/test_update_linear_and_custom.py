from unittest.mock import MagicMock, patch
from utils.update_linear_and_custom import compute_linear_and_custom_updates, update_linear_and_custom

def dummy_resolve_expression(expr, cfg, row):
    # Simple dummy: just return row key if expr == "row['some_field']"
    if expr.startswith("row["):
        key = expr.split("[")[1].split("]")[0].strip("'\"")
        return row.get(key, None)
    return 42

def test_compute_linear_and_custom_updates_linear_and_custom():
    # Setup
    update_fields = ["OID@", "RouteID", "MP", "Custom1"]
    linear_fields = {
        "route_identifier": {"name": "RouteID", "type": "TEXT"},
        "route_measure": {"name": "MP", "type": "DOUBLE"}
    }
    custom_field_defs = [
        ("custom1", "Custom1", "row['OID@']", "DOUBLE")
    ]
    oid_to_loc = {1: {"route_id": "A", "mp_value": 12.5}}
    row = [1, None, None, None]
    # Patch resolve_expression in the helper
    import utils.update_linear_and_custom as ulc
    orig_resolve = ulc.resolve_expression
    ulc.resolve_expression = dummy_resolve_expression
    try:
        new_row, updated = compute_linear_and_custom_updates(
            cfg=MagicMock(),
            row=row,
            update_fields=update_fields,
            linear_fields=linear_fields,
            custom_field_defs=custom_field_defs,
            oid_to_loc=oid_to_loc,
            enable_linear_ref=True,
            logger=None
        )
        assert updated is True
        assert new_row[1] == "A"
        assert new_row[2] == 12.5
        assert new_row[3] == 1.0
    finally:
        ulc.resolve_expression = orig_resolve

def test_compute_linear_and_custom_updates_disable_linear():
    update_fields = ["OID@", "RouteID", "MP", "Custom1"]
    linear_fields = {
        "route_identifier": {"name": "RouteID", "type": "TEXT"},
        "route_measure": {"name": "MP", "type": "DOUBLE"}
    }
    custom_field_defs = [
        ("custom1", "Custom1", "row['OID@']", "DOUBLE")
    ]
    oid_to_loc = {1: {"route_id": "A", "mp_value": 12.5}}
    row = [1, None, None, None]
    import utils.update_linear_and_custom as ulc
    orig_resolve = ulc.resolve_expression
    ulc.resolve_expression = dummy_resolve_expression
    try:
        new_row, updated = compute_linear_and_custom_updates(
            cfg=MagicMock(),
            row=row,
            update_fields=update_fields,
            linear_fields=linear_fields,
            custom_field_defs=custom_field_defs,
            oid_to_loc=oid_to_loc,
            enable_linear_ref=False,
            logger=None
        )
        assert updated is True
        assert new_row[1] is None
        assert new_row[2] is None
        assert new_row[3] == 1.0
    finally:
        ulc.resolve_expression = orig_resolve

@patch('arcpy.management.GetCount')
@patch('arcpy.da.UpdateCursor')
@patch('arcpy.da.SearchCursor')
@patch('utils.update_linear_and_custom.compute_linear_and_custom_updates')
def test_update_linear_and_custom_main_logic(mock_compute, mock_search, mock_update, mock_getcount):
    mock_getcount.return_value = ["2"]
    # Setup mocks
    mock_logger = MagicMock()
    mock_cfg = MagicMock()
    mock_cfg.get_logger.return_value = mock_logger
    mock_cfg.get.side_effect = lambda k, d=None: {
        "oid_schema_template.linear_ref_fields": {
            "route_identifier": {"name": "RouteID", "type": "TEXT"},
            "route_measure": {"name": "MP", "type": "DOUBLE"}
        },
        "oid_schema_template.linear_ref_fields.route_identifier.name": "RouteID",
        "oid_schema_template.linear_ref_fields.route_measure.name": "MP",
        "oid_schema_template.custom_fields": {
            "custom1": {"name": "Custom1", "expression": "row['OID@']", "type": "DOUBLE"}
        }
    }.get(k, d)
    mock_cfg.get_progressor.side_effect = lambda total, label: MagicMock(__enter__=lambda s: s, __exit__=lambda s, exc_type, exc_val, exc_tb: None, update=lambda x: None)
    mock_cfg.validate.return_value = True
    # Simulate rows and updates
    mock_rows = [[1, None, None, None], [2, None, None, None]]
    mock_update.return_value.__enter__.return_value = mock_rows
    mock_compute.side_effect = lambda **kwargs: (kwargs['row'], True)
    update_linear_and_custom(mock_cfg, 'fake_oid_fc', centerline_fc=None, route_id_field=None, enable_linear_ref=False)
    mock_cfg.validate.assert_called_with(tool="update_linear_and_custom")
    assert mock_logger.info.called
    # Verify specific log messages
    mock_logger.success.assert_called_once()
    # If you need to check the exact message:
    # assert "Updated" in mock_logger.success.call_args[0][0]
