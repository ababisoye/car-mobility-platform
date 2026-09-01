# DynamoDB data migration controls

Every newly created booking, vehicle, chauffeur, quote, notification, payment and webhook-event record includes `schema_version`. Version 1 establishes the migration contract without changing the existing key design.

## Rules

- Application changes must read the current schema and the immediately previous schema during a migration window.
- Migrations must be additive before they are destructive.
- Run a dry-run first and review counts for every table.
- Verify the AWS account ID before any scan or write.
- Use conditional updates so concurrent application writes are not overwritten.
- Never print full records or customer fields in migration output.
- Do not migrate production and demo data with the same command or credentials.
- Approve backup, recovery and retention costs before a migration that can lose or transform data.

## Version 1 dry-run

The helper scans only each primary key and `schema_version`. Although it does not write in dry-run mode, DynamoDB reads may still consume capacity on a deployed stack.

```powershell
python scripts/migrate-demo-schema.py --expected-account-id 123456789012
```

The JSON report shows scanned records and candidates per table. It does not contain record values.

## Apply version 1

Only after reviewing the dry-run, using temporary AWS credentials, and confirming the exact account:

```powershell
python scripts/migrate-demo-schema.py `
  --expected-account-id 123456789012 `
  --apply `
  --confirmation APPLY-DEMO-SCHEMA-V1
```

The helper writes only records below version 1. Its condition expression prevents it from overwriting a record that another process has already migrated. Re-running it is safe: current records are counted as scanned but not changed.

## Verification and rollback

Run the dry-run again; every table should report zero candidates. Exercise booking creation, quotation, payment and dashboard reads before closing the change.

Version 1 only adds a marker, so older application code ignores it and application rollback remains safe. Future migrations must document their own backward-read period, verification query and data rollback procedure before implementation.

This repository has not run the migration against AWS. The tool is committed as a controlled capability, not as authorization to alter data.
