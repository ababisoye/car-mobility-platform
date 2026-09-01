"""Dry-run-first DynamoDB schema marker migration for the demo environment."""

import argparse
import json
import sys


TARGET_SCHEMA_VERSION = 1
TABLES = {
    "bookings": "booking_id",
    "vehicles": "vehicle_id",
    "chauffeurs": "chauffeur_id",
    "quotes": "quote_id",
    "notifications": "notification_id",
    "payments": "record_id",
}
APPLY_CONFIRMATION = "APPLY-DEMO-SCHEMA-V1"


def migrate_table(table, key_field, apply_changes=False):
    summary = {"scanned": 0, "candidates": 0, "updated": 0, "concurrent_skips": 0, "invalid_versions": 0}
    cursor = None
    while True:
        request = {
            "ProjectionExpression": "#key, schema_version",
            "ExpressionAttributeNames": {"#key": key_field},
        }
        if cursor:
            request["ExclusiveStartKey"] = cursor
        page = table.scan(**request)
        for item in page.get("Items", []):
            summary["scanned"] += 1
            try:
                version = int(item.get("schema_version", 0))
            except (TypeError, ValueError):
                summary["invalid_versions"] += 1
                continue
            if version >= TARGET_SCHEMA_VERSION:
                continue
            summary["candidates"] += 1
            if not apply_changes:
                continue
            try:
                table.update_item(
                    Key={key_field: item[key_field]},
                    UpdateExpression="SET schema_version = :target",
                    ConditionExpression="attribute_not_exists(schema_version) OR schema_version < :target",
                    ExpressionAttributeValues={":target": TARGET_SCHEMA_VERSION},
                )
                summary["updated"] += 1
            except Exception as error:
                code = getattr(error, "response", {}).get("Error", {}).get("Code")
                if code == "ConditionalCheckFailedException":
                    summary["concurrent_skips"] += 1
                    continue
                raise
        cursor = page.get("LastEvaluatedKey")
        if not cursor:
            return summary


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Add schema_version=1 to legacy demo records without rewriting current records.")
    parser.add_argument("--expected-account-id", required=True, help="AWS account that is allowed to be scanned or changed.")
    parser.add_argument("--region", default="af-south-1")
    parser.add_argument("--table-prefix", default="luxury-rental-demo")
    parser.add_argument("--apply", action="store_true", help="Apply conditional updates. Omit for dry-run mode.")
    parser.add_argument("--confirmation", help=f"Required with --apply; must equal {APPLY_CONFIRMATION}.")
    return parser.parse_args(argv)


def validate_args(args):
    if not (args.expected_account_id.isdigit() and len(args.expected_account_id) == 12):
        raise SystemExit("--expected-account-id must contain exactly 12 digits")
    if args.apply and args.confirmation != APPLY_CONFIRMATION:
        raise SystemExit(f"Refusing write mode: pass --confirmation {APPLY_CONFIRMATION}")


def main(argv=None):
    args = parse_args(argv)
    validate_args(args)

    import boto3

    session = boto3.Session(region_name=args.region)
    actual_account_id = session.client("sts").get_caller_identity()["Account"]
    if actual_account_id != args.expected_account_id:
        raise SystemExit(f"Refusing account {actual_account_id}; expected {args.expected_account_id}")

    dynamodb = session.resource("dynamodb")
    report = {"mode": "apply" if args.apply else "dry-run", "target_schema_version": TARGET_SCHEMA_VERSION, "tables": {}}
    for suffix, key_field in TABLES.items():
        name = f"{args.table_prefix}-{suffix}"
        report["tables"][name] = migrate_table(dynamodb.Table(name), key_field, args.apply)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
