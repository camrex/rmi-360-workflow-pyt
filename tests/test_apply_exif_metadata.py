import pytest
from utils.apply_exif_metadata import _extract_required_fields, _resolve_tags

def test_extract_required_fields_simple():
    tags = {
        "Artist": "field.Author",
        "Copyright": "field.Copyright",
        "Keywords": ["field.Keyword1", "field.Keyword2"]
    }
    fields = _extract_required_fields(tags)
    # Should include Author, Copyright, Keyword1, Keyword2, X, Y, QCFlag
    for f in ["Author", "Copyright", "Keyword1", "Keyword2", "X", "Y", "QCFlag"]:
        assert f in fields

def test_resolve_tags_basic(monkeypatch):
    tags = {
        "Artist": "field.Author",
        "Keywords": ["field.Keyword1", "field.Keyword2"]
    }
    row = {"Author": "Alice", "Keyword1": "foo", "Keyword2": "bar"}
    # Patch resolve_expression to just return the value from row
    monkeypatch.setattr("utils.apply_exif_metadata.resolve_expression", lambda expr, row_dict: row_dict[expr.split(".")[1]])
    result = _resolve_tags(tags, row)
    assert result["Artist"] == "Alice"
    assert result["Keywords"] == "foo;bar"
