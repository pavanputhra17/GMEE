"""Fail CI for missing, empty, skipped, failed or errored integration results."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def check_report(path: Path) -> int:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        raise ValueError("Integration JUnit report is missing or invalid.") from None
    cases = list(root.iter("testcase"))
    if not cases:
        raise ValueError("No integration tests ran.")
    for outcome in ("skipped", "failure", "error"):
        count = sum(1 for _ in root.iter(outcome))
        if count:
            raise ValueError(f"Integration suite contains {count} {outcome} result(s).")
    return len(cases)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        count = check_report(args.report)
    except ValueError as exc:
        print(f"Required integration gate failed: {exc}", file=sys.stderr)
        return 1
    print(f"Required integration gate passed: {count} tests, zero skips.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
