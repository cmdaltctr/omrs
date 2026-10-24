"""Read the fast-suite JUnit report for the clean-base tripwire.

Design D4 of ``speed-up-fast-test-suite``. The fast-suite step writes a report
with ``--junitxml``; the tripwire reads the passed count from it and does not
run the suite a second time. The leading underscore keeps pytest from
collecting this file. Both the tripwire and its unit tests import it.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path

_NOT_PASSED = ("skipped", "failure", "error")


def junit_passed_count(report: Path, code_roots: Iterable[Path]) -> int:
    """Return the passed count from a pytest JUnit report.

    A passed case is a ``<testcase>`` with no ``skipped``, ``failure`` or
    ``error`` child. The root can be ``<testsuites>`` (pytest and xdist
    write this) or a bare ``<testsuite>``. Deselected tests are not in the
    report, so the caller gets that count elsewhere.

    Args:
        report: Path of the JUnit XML report from the fast-suite run.
        code_roots: Folders whose ``*.py`` files must all be older than the
            report, normally the repository's ``src/`` and ``tests/``.

    Returns:
        The number of passed test cases.

    Raises:
        AssertionError: The report is missing, is older than a ``*.py`` file
            under ``code_roots``, or records a failure or an error.
    """
    if not report.is_file():
        raise AssertionError(f"JUnit report not found: {report}")

    report_mtime = report.stat().st_mtime_ns
    for root in code_roots:
        for source in root.rglob("*.py"):
            if source.stat().st_mtime_ns > report_mtime:
                raise AssertionError(
                    f"JUnit report {report} is stale: {source} changed after it was "
                    "written. Run the fast suite again with --junitxml."
                )

    cases = ET.parse(report).getroot().iter("testcase")  # noqa: S314 - our own pytest output
    passed = failures = errors = 0
    for case in cases:
        children = {child.tag for child in case}
        failures += "failure" in children
        errors += "error" in children
        passed += not children.intersection(_NOT_PASSED)
    if failures or errors:
        raise AssertionError(
            f"fast suite did not pass: {report} records {failures} failed and "
            f"{errors} errored test cases"
        )
    return passed
