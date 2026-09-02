import re
import unittest
from pathlib import Path


DEMO_TERRAFORM = Path(__file__).parents[1] / "infra" / "environments" / "demo" / "main.tf"


class ZeroFundingPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = DEMO_TERRAFORM.read_text(encoding="utf-8")
        cls.resource_types = re.findall(r'resource\s+"([^"]+)"\s+"[^"]+"', cls.source)

    def value(self, name):
        match = re.search(rf"^\s*{re.escape(name)}\s*=\s*([^\r\n]+)", self.source, re.MULTILINE)
        self.assertIsNotNone(match, f"Demo policy requires {name} to be explicit")
        return match.group(1).strip().strip('"')

    def test_only_reviewed_zero_funding_resource_types_are_present(self):
        allowed = {
            "aws_budgets_budget",
            "aws_cloudwatch_log_group",
            "aws_dynamodb_table",
            "aws_iam_role",
            "aws_iam_role_policy",
            "aws_lambda_alias",
            "aws_lambda_function",
            "aws_lambda_function_url",
            "aws_lambda_permission",
        }
        unexpected = sorted(set(self.resource_types) - allowed)
        self.assertEqual(unexpected, [], f"Unreviewed demo resource types can create cost: {unexpected}")

    def test_database_capacity_and_count_remain_minimal(self):
        self.assertEqual(self.resource_types.count("aws_dynamodb_table"), 6)
        self.assertEqual(len(re.findall(r"^\s*read_capacity\s*=\s*1\s*$", self.source, re.MULTILINE)), 6)
        self.assertEqual(len(re.findall(r"^\s*write_capacity\s*=\s*1\s*$", self.source, re.MULTILINE)), 6)
        self.assertNotRegex(self.source, r'billing_mode\s*=\s*"PAY_PER_REQUEST"')

    def test_lambda_blast_radius_remains_capped(self):
        self.assertEqual(self.value("memory_size"), "128")
        self.assertEqual(self.value("timeout"), "5")
        self.assertEqual(self.value("reserved_concurrent_executions"), "1")
        self.assertEqual(self.value("architectures"), "[\"arm64\"]")

    def test_logs_budget_and_public_entrypoint_are_explicit(self):
        self.assertEqual(self.value("retention_in_days"), "1")
        self.assertEqual(self.value("limit_amount"), "1")
        self.assertEqual(self.value("authorization_type"), "NONE")
        self.assertIn('invoked_via_function_url = true', self.source)

    def test_demo_iam_does_not_grant_wildcard_actions_or_resources(self):
        self.assertNotRegex(self.source, r'Action\s*=\s*"\*"')
        self.assertNotRegex(self.source, r'Resource\s*=\s*"\*"')


if __name__ == "__main__":
    unittest.main()
