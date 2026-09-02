import re
import unittest
from pathlib import Path


WORKFLOW_ROOT = Path(__file__).parents[1] / ".github" / "workflows"


class CiSupplyChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = {path.name: path.read_text(encoding="utf-8") for path in WORKFLOW_ROOT.glob("*.yml")}

    def test_external_actions_are_pinned_to_full_commits(self):
        for name, source in self.workflows.items():
            action_lines = re.findall(r"^\s*(?:-\s+)?uses:\s*([^\s#]+)(?:\s+#\s*(v\d+))?\s*$", source, re.MULTILINE)
            self.assertTrue(action_lines, f"{name} should declare at least one external action")
            for reference, version_comment in action_lines:
                self.assertRegex(reference, r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$", f"Floating action reference in {name}: {reference}")
                self.assertRegex(version_comment, r"^v\d+$", f"Pinned action in {name} needs a readable major-version comment")

    def test_workflows_keep_least_privilege_permissions(self):
        validation = self.workflows["terraform-validate.yml"]
        release = self.workflows["release-demo.yml"]
        for name, source in self.workflows.items():
            self.assertRegex(source, r"(?m)^permissions:\s*\n\s+contents:\s+read\s*$", f"{name} must default to read-only contents")
            self.assertNotRegex(source, r"(?m)^\s+(contents|actions|pull-requests|packages):\s+write\s*$")
        self.assertNotIn("id-token: write", validation)
        self.assertEqual(release.count("id-token: write"), 1)
        self.assertRegex(release, r"(?s)release:\s+.*?permissions:\s+contents:\s+read\s+id-token:\s+write")


if __name__ == "__main__":
    unittest.main()
