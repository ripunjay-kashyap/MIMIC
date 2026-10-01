"""Evaluate JSON findings against seeded issues, without database access.

Usage from backend: .venv/bin/python scripts/evaluate_run.py findings.json
Only this evaluation boundary reads files; the analysis functions are pure.
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

# Direct script execution puts scripts/, not backend/, on sys.path.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.schemas import Finding

SEEDED_ISSUES = Path(__file__).resolve().parents[1] / "demo_site" / "SEEDED_ISSUES.json"


def _basename(page: str) -> str:
    path = urlparse(page).path
    return path.rsplit("/", 1)[-1] or "index.html"


def evaluate(findings: list[Finding]) -> dict:
    issues = json.loads(SEEDED_ISSUES.read_text(encoding="utf-8"))
    detectable = [issue for issue in issues if issue["detectable_by"] != "visual"]
    found, missed, matched = [], [], set()
    for issue in detectable:
        matches = {
            index for index, finding in enumerate(findings)
            if finding.category in issue["expected_signals"]
            and (
                (finding.page is not None and _basename(finding.page) == _basename(issue["page"]))
                or (finding.page is None and bool({"long_path", "route_divergence"} & set(issue["expected_signals"])))
            )
        }
        (found if matches else missed).append(issue["id"])
        matched.update(matches)
    return {
        "found": found,
        "missed": missed,
        "recall": len(found) / len(detectable) if detectable else 0.0,
        "unmatched_findings": [
            f"{f.category}@{f.page}" for i, f in enumerate(findings) if i not in matched
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("findings", type=Path, help="JSON list of Finding objects")
    args = parser.parse_args()
    try:
        data = json.loads(args.findings.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("expected a JSON list of Finding objects")
        findings = [Finding.model_validate(item) for item in data]
        result = evaluate(findings)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
