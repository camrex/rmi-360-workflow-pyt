This folder holds the OID schema template geodatabase used by the RMI Mosaic 360 Tools.

The geodatabase (`templates.gdb`) is not included in version control and must be created manually.

To generate the geodatabase and base OID schema table, run the following script:

    from utils.oid_schema import create_oid_schema_template
    create_oid_schema_template()

This will:
- Create `templates/templates.gdb` if it does not exist
- Add a table named `oid_schema_template` using the standard schema
- Append any additional fields defined in `config.yaml > custom_oid_fields`

The script only needs to be run once, unless the schema is updated.
