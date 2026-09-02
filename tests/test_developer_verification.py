import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/terraform-check.ps1"


class DeveloperVerificationTests(unittest.TestCase):
    def test_helper_covers_tests_and_every_terraform_root(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("-m unittest discover -s tests -v", script)
        self.assertIn("fmt -check -recursive infra", script)
        for root in (
            "infra/bootstrap",
            "infra/environments/demo",
            "infra/environments/nonprod",
            "infra/environments/production",
            "infra/github-release-role",
        ):
            with self.subTest(root=root):
                self.assertIn(f'"{root}"', script)

    def test_helper_cannot_plan_or_apply_infrastructure(self):
        script = SCRIPT.read_text(encoding="utf-8").lower()

        self.assertNotIn("$terraformcommand.source plan", script)
        self.assertNotIn("$terraformcommand.source apply", script)
        self.assertNotIn("terraform plan", script)
        self.assertNotIn("terraform apply", script)


if __name__ == "__main__":
    unittest.main()
