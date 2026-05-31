# Tool: Update Linear and Custom Attributes

## Tool Name

06 - Update Linear and Custom Attributes

## Purpose

Updates OID rows with:

- Linear referencing fields (for example `MP_Pre`, `MP_Num`) when LR is enabled
- Custom expression-driven fields from config
- Optional `SequenceOrder` population when enabled

## Inputs

- OID feature class
- Optional centerline feature class and route ID field
- Workflow LR toggle (`enable_linear_ref`)
- Config blocks:
  - `oid_schema_template.linear_ref_fields`
  - `oid_schema_template.custom_fields`
  - `sequence_order` (optional)

## Outputs

- Updated OID attributes for linear/custom fields
- Optional populated `SequenceOrder`

## Runtime Behavior

1. Validates config (`update_linear_and_custom` validator).
2. If LR is enabled and centerline inputs are present, runs locate-along-route and maps route and MP values by OID.
3. Applies linear field updates and custom expression updates.
4. Applies optional SequenceOrder assignment if `sequence_order.enabled` is true.

## SequenceOrder Logic

SequenceOrder is optional and config-gated.

When enabled:

- If LR is enabled and LR fields exist, ordering uses grouped `MP_Pre` and `MP_Num`.
- Otherwise ordering falls back to `AcquisitionDate`.
- Ties are resolved deterministically by OID.

Decision controls:

- `sequence_order.prefix_order`: explicit ordering for prefix groups
- `sequence_order.descending_prefixes`: prefixes that sort MP descending
- `sequence_order.null_milepost_position`: where null MP rows go (`start` or `end`)

## Configuration

```yaml
sequence_order:
  enabled: false
  field_name: "SequenceOrder"
  acquisition_datetime_field: "AcquisitionDate"
  lr_prefix_field: "MP_Pre"
  lr_mile_field: "MP_Num"
  prefix_order: []
  descending_prefixes: []
  null_milepost_position: "end"
```

## Validation

Validator: `utils/validators/update_linear_and_custom_validator.py`

Checks include:

- `linear_ref_fields` and `custom_fields` schema blocks
- Field block structure and types
- Optional `sequence_order` structure and value types
- `sequence_order.null_milepost_position` in (`start`, `end`)

## Notes

- If SequenceOrder is disabled, field values are left as-is (typically null).
- If LR is enabled but MP fields are unavailable at runtime, SequenceOrder falls back to datetime ordering.
- Null MP rows are not dropped; they are placed deterministically and logged.
