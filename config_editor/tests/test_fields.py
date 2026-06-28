from config_editor.core import fields


def _schema():
    return fields.build_form_schema()


def test_sections_and_fields_present():
    sch = _schema()
    keys = {s["key"] for s in sch["sections"]}
    assert {"project", "aws", "portal", "corridor_thinning"} <= keys
    assert "general" in keys  # top-level scalars (schema_version, thinning_mode...)
    assert len(list(fields.iter_fields(sch))) > 100


def test_section_headers_from_at_section_markers():
    secs = {s["key"]: s for s in _schema()["sections"]}
    assert secs["aws"]["label"] == "AWS Storage"
    assert secs["oid_schema_template"]["label"] == "OID Schema & Fields"
    assert "S3 buckets" in secs["aws"]["help"]


def test_section_doc_block_captured():
    secs = {s["key"]: s for s in _schema()["sections"]}
    doc = secs["aws"]["doc"]
    # full header block surfaced (multi-line), dividers stripped, @section line excluded
    assert "credentials" in doc and "secured_delivery" in doc
    assert doc.count("\n") > 5
    assert "@section" not in doc
    assert "----" not in doc


def test_scan_sections_doc_unit():
    text = (
        "# ------------------------------------\n"
        "# @section: AWS Storage | short desc\n"
        "# Longer overview line one.\n"
        "#   - a bullet\n"
        "# ------------------------------------\n"
        "aws:\n"
        "  region: y\n"
    )
    s = fields.scan_sections(text)["aws"]
    assert s["title"] == "AWS Storage" and s["help"] == "short desc"
    assert s["doc"] == "Longer overview line one.\n  - a bullet"


def test_inline_help_extracted_without_bleed_or_tags():
    flds = {f["path"]: f for f in fields.iter_fields(_schema())}
    assert flds["aws.s3_bucket_panos_unsecured"]["help"] == "Public/unsecured panorama hosting"
    # tags stripped, first-line only
    assert "@choices" not in flds["thinning_mode"]["help"]
    assert flds["thinning_mode"]["help"] == "Pre-thin via corridor pipeline, or post-thin filter."


def test_choices_tag_makes_strict_select():
    flds = {f["path"]: f for f in fields.iter_fields(_schema())}
    sw = flds["portal.share_with"]
    assert sw["widget"] == "select" and sw["strict"] is True
    assert sw["choices"] == ["PRIVATE", "ORGANIZATION", "PUBLIC"]
    mp = flds["corridor_thinning.manifest.mp_num_source"]
    assert mp["choices"] == ["relocate", "manifest"]


def test_secret_tag_and_inferred_types():
    flds = {f["path"]: f for f in fields.iter_fields(_schema())}
    assert flds["aws.secret_key"]["widget"] == "secret"
    assert flds["aws.access_key"]["widget"] == "secret"
    assert flds["aws.secured_delivery.enabled"]["type"] == "bool"
    assert flds["aws.secured_delivery.enabled"]["widget"] == "checkbox"


def test_no_tags_means_free_text():
    flds = {f["path"]: f for f in fields.iter_fields(_schema())}
    slug = flds["project.slug"]
    assert slug["widget"] == "text" and slug["choices"] is None


def test_scan_sections_unit():
    text = (
        "# @section: Project | Identity stuff.\n"
        "project:\n"
        "  slug: x   # the slug\n"
        "# @section: AWS Storage\n"
        "aws:\n"
        "  region: y\n"
    )
    secs = fields.scan_sections(text)
    assert secs["project"] == {"title": "Project", "help": "Identity stuff.", "doc": ""}
    assert secs["aws"] == {"title": "AWS Storage", "help": "", "doc": ""}


def test_parse_inline_tags_unit():
    help_text, meta = fields._parse_inline_tags(
        "How creds resolve. @choices[a, b, c] @secret")
    assert help_text == "How creds resolve."
    assert meta["choices"] == ["a", "b", "c"]
    assert meta["secret"] is True


def _find(nodes, path):
    for n in nodes:
        if n.get("path") == path:
            return n
        if n["kind"] == "group":
            r = _find(n["children"], path)
            if r:
                return r
    return None


def test_repeatable_collection_node():
    sch = _schema()
    cf = _find(sch["sections"], "oid_schema_template.custom_fields")
    assert cf is not None and cf["kind"] == "collection"
    assert cf["item_label_field"] == "name"
    tpl = {t["key"]: t for t in cf["item_template"]}
    assert {"name", "type", "length", "alias"} <= set(tpl)
    # 'type' becomes an ESRI field-type dropdown
    assert tpl["type"]["widget"] == "select"
    assert "TEXT" in tpl["type"]["choices"] and "DOUBLE" in tpl["type"]["choices"]
    # new-entry defaults are empty-ish (not copied from an existing entry)
    assert tpl["name"]["default"] == ""
    assert tpl["type"]["default"] == "TEXT"


def test_collection_paths():
    paths = fields.collection_paths(_schema())
    assert "oid_schema_template.custom_fields" in paths
    assert "oid_schema_template.mosaic_fields" in paths


def test_when_condition_parsed():
    flds = {f["path"]: f for f in fields.iter_fields(_schema())}
    assert flds["aws.access_key"]["when"] == {"path": "aws.auth_mode", "values": ["config"]}
    assert flds["aws.secret_key"]["when"]["values"] == ["config"]
    assert flds["aws.keyring_service_name"]["when"] == {"path": "aws.auth_mode", "values": ["keyring"]}
    assert flds["aws.region"]["when"] is None  # unconditional fields have no 'when'
    # @when is stripped from displayed help
    assert "@when" not in flds["aws.access_key"]["help"]


def test_when_unit():
    _, meta = fields._parse_inline_tags("Some help @when[a.b=x, y]")
    assert meta["when"] == {"path": "a.b", "values": ["x", "y"]}


def test_collection_fields_not_in_iter_fields():
    # template fields are not concrete -> excluded from iter_fields
    paths = {f["path"] for f in fields.iter_fields(_schema())}
    assert not any(p.startswith("oid_schema_template.custom_fields.") for p in paths)
