import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class AuthenticationConfigurationTests(unittest.TestCase):
    def test_generator_preview_and_terraform_share_the_runtime_floor(self):
        generator = (ROOT / "scripts" / "generate-admin-password-hash.py").read_text(encoding="utf-8")
        preview = (ROOT / "scripts" / "preview-demo.py").read_text(encoding="utf-8")
        variables = (ROOT / "infra" / "environments" / "demo" / "variables.tf").read_text(encoding="utf-8")
        self.assertIn("ITERATIONS = 210_000", generator)
        self.assertIn("210_000", preview)
        self.assertGreaterEqual(variables.count(">= 210000"), 2)
        self.assertGreaterEqual(variables.count("<= 2000000"), 2)


if __name__ == "__main__":
    unittest.main()
