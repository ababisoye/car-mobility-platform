import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
LINK_PATTERN = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")
REMOTE_SCHEMES = {"http", "https", "mailto"}


def local_link_targets(document):
    content = document.read_text(encoding="utf-8")
    for match in LINK_PATTERN.finditer(content):
        raw_target = match.group(1).strip()
        if raw_target.startswith("<") and raw_target.endswith(">"):
            raw_target = raw_target[1:-1]
        else:
            raw_target = raw_target.split(maxsplit=1)[0]

        parsed = urlsplit(raw_target)
        if parsed.scheme.lower() in REMOTE_SCHEMES or not parsed.path:
            continue

        yield unquote(parsed.path)


class DocumentationLinkTests(unittest.TestCase):
    def test_local_markdown_links_resolve_inside_repository(self):
        failures = []

        for document in sorted(ROOT.rglob("*.md")):
            for target in local_link_targets(document):
                resolved = (document.parent / target).resolve()
                relative_document = document.relative_to(ROOT)

                if not resolved.is_relative_to(ROOT):
                    failures.append(
                        f"{relative_document}: link escapes repository: {target}"
                    )
                elif not resolved.exists():
                    failures.append(
                        f"{relative_document}: missing local target: {target}"
                    )

        self.assertEqual([], failures, "\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
