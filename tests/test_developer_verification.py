import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/terraform-check.ps1"
WORKFLOW = ROOT / ".github/workflows/terraform-validate.yml"


def terraform_roots():
    return {
        versions_file.parent.relative_to(ROOT).as_posix()
        for versions_file in (ROOT / "infra").rglob("versions.tf")
        if (versions_file.parent / "providers.tf").is_file()
    }


class DeveloperVerificationTests(unittest.TestCase):
    def test_local_helper_covers_tests_and_every_terraform_root(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("-m unittest discover -s tests -v", script)
        self.assertIn("fmt -check -recursive infra", script)
        self.assertEqual(5, len(terraform_roots()))
        for root in terraform_roots():
            with self.subTest(root=root):
                self.assertIn(f'"{root}"', script)

    def test_ci_covers_every_terraform_root(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        for root in terraform_roots():
            with self.subTest(root=root):
                self.assertIn(f"- {root}", workflow)

    def test_helper_cannot_plan_or_apply_infrastructure(self):
        script = SCRIPT.read_text(encoding="utf-8").lower()

        self.assertNotIn("$terraformcommand.source plan", script)
        self.assertNotIn("$terraformcommand.source apply", script)
        self.assertNotIn("terraform plan", script)
        self.assertNotIn("terraform apply", script)


if __name__ == "__main__":
    unittest.main()
