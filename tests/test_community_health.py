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

    def test_threat_model_documents_boundaries_and_residual_risk(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        threat_model = (ROOT / "docs/threat-model.md").read_text(encoding="utf-8")

        self.assertIn("[threat model](docs/threat-model.md)", readme)
        for section in (
            "Assets",
            "Trust boundaries",
            "Abuse cases and controls",
            "Security invariants",
            "Risk acceptance and review triggers",
        ):
            with self.subTest(section=section):
                self.assertIn(f"## {section}", threat_model)

        for threat in (
            "Spoofing",
            "Tampering",
            "Repudiation",
            "Information disclosure",
            "Denial of service",
            "Elevation of privilege",
        ):
            with self.subTest(threat=threat):
                self.assertIn(f"| {threat} |", threat_model)

    def test_portfolio_walkthrough_is_linked_and_sets_safe_boundaries(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        walkthrough = (ROOT / "docs/demo-walkthrough.md").read_text(encoding="utf-8")

        self.assertIn(
            "[five-minute portfolio walkthrough](docs/demo-walkthrough.md)", readme
        )
        for section in (
            "Start the demonstration",
            "Demonstrate the customer journey",
            "Demonstrate operations",
            "Explain the engineering decisions",
            "Be explicit about limitations",
            "Stop and reset",
        ):
            with self.subTest(section=section):
                self.assertIn(f"## {section}", walkthrough)
        self.assertIn("requires no AWS account", walkthrough)
        self.assertIn("synthetic data", walkthrough)

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
