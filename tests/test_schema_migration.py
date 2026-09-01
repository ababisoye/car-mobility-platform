import importlib.util
import unittest
from pathlib import Path


script_path = Path(__file__).parents[1] / "scripts" / "migrate-demo-schema.py"
spec = importlib.util.spec_from_file_location("schema_migration", script_path)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class FakeMigrationTable:
    def __init__(self):
        self.items = {
            "legacy": {"booking_id": "legacy"},
            "current": {"booking_id": "current", "schema_version": 1},
        }

    def scan(self, **_kwargs):
        return {"Items": list(self.items.values())}

    def update_item(self, Key, **_kwargs):
        self.items[Key["booking_id"]]["schema_version"] = 1


class SchemaMigrationTests(unittest.TestCase):
    def test_dry_run_identifies_without_updating_legacy_records(self):
        table = FakeMigrationTable()
        result = migration.migrate_table(table, "booking_id")
        self.assertEqual(result, {"scanned": 2, "candidates": 1, "updated": 0, "concurrent_skips": 0, "invalid_versions": 0})
        self.assertNotIn("schema_version", table.items["legacy"])

    def test_apply_updates_only_legacy_records(self):
        table = FakeMigrationTable()
        result = migration.migrate_table(table, "booking_id", apply_changes=True)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(table.items["legacy"]["schema_version"], 1)

    def test_apply_requires_exact_confirmation(self):
        args = migration.parse_args(["--expected-account-id", "123456789012", "--apply"])
        with self.assertRaises(SystemExit):
            migration.validate_args(args)

    def test_invalid_versions_are_reported_without_overwrite(self):
        table = FakeMigrationTable()
        table.items["legacy"]["schema_version"] = "unknown"
        result = migration.migrate_table(table, "booking_id", apply_changes=True)
        self.assertEqual(result["invalid_versions"], 1)
        self.assertEqual(result["updated"], 0)


if __name__ == "__main__":
    unittest.main()
