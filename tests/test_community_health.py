import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CommunityHealthTests(unittest.TestCase):
    def test_public_repository_guidance_is_present(self):
        required_files = (
            "CONTRIBUTING.md",
            "SECURITY.md",
            ".github/pull_request_template.md",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            ".github/ISSUE_TEMPLATE/feature_request.yml",
            ".github/ISSUE_TEMPLATE/config.yml",
        )

        for relative_path in required_files:
            with self.subTest(path=relative_path):
                self.assertTrue((ROOT / relative_path).is_file())

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("[contribution guide](CONTRIBUTING.md)", readme)
        self.assertIn("[security policy](SECURITY.md)", readme)
        self.assertIn("no open-source license", readme)

    def test_architecture_decisions_explain_demo_tradeoffs(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        decisions = (ROOT / "docs/architecture-decisions.md").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "[architecture decisions](docs/architecture-decisions.md)", readme
        )
        for decision in (
            "Why there is no NAT Gateway",
            "Why there is no load balancer or API Gateway",
            "Accepted demo limitations",
            "Promotion conditions",
        ):
            with self.subTest(decision=decision):
                self.assertIn(decision, decisions)

    def test_security_reports_are_directed_to_a_private_channel(self):
        security_policy = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        issue_config = (
            ROOT / ".github/ISSUE_TEMPLATE/config.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("Do not open a public issue", security_policy)
        self.assertIn("blank_issues_enabled: false", issue_config)
        self.assertIn(
            "https://github.com/ababisoye/car-mobility-platform/security/advisories/new",
            issue_config,
        )


if __name__ == "__main__":
    unittest.main()
