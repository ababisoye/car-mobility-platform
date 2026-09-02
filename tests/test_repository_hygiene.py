import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SECRET_PATTERNS = {
    "AWS access key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "GitHub token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Slack token": re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "live Stripe key": re.compile(rb"\b[rs]k_live_[A-Za-z0-9]{16,}\b"),
}


class RepositoryHygieneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
        )
        cls.tracked = [Path(value.decode("utf-8")) for value in result.stdout.split(b"\0") if value]

    def test_sensitive_generated_files_are_not_tracked(self):
        forbidden = []
        for path in self.tracked:
            normalized = path.as_posix().lower()
            name = path.name.lower()
            if (
                "/.terraform/" in f"/{normalized}"
                or name == ".env"
                or name.endswith((".tfstate", ".tfplan", ".pem", ".p12", ".pfx", ".zip"))
                or (name.endswith(".tfvars") and not name.endswith(".tfvars.example"))
            ):
                forbidden.append(path.as_posix())
        self.assertEqual(forbidden, [], f"Sensitive generated files are tracked: {forbidden}")

    def test_tracked_files_contain_no_high_confidence_secret_patterns(self):
        findings = []
        for relative_path in self.tracked:
            data = (ROOT / relative_path).read_bytes()
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(data):
                    findings.append(f"{relative_path.as_posix()}: {label}")
        self.assertEqual(findings, [], f"Possible committed secrets: {findings}")


if __name__ == "__main__":
    unittest.main()
