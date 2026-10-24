"""Unit tests for the clean-base tripwire's JUnit report reader.

Task 5.1 of ``speed-up-fast-test-suite`` (design D4). The tripwire reads the
passed count from the fast-suite report instead of running the suite again.
These tests use small hand-written reports in ``tmp_path``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from tests._tripwire_report import junit_passed_count

# Three passed cases, one skipped case and one module-level skip. Pytest writes
# a module-level skip as a test case with an empty classname.
_CASES = """
<testcase classname="tests.test_a" name="test_one" time="0.01"/>
<testcase classname="tests.test_a" name="test_two" time="0.01"/>
<testcase classname="tests.test_b" name="test_three"><system-out>x</system-out></testcase>
<testcase classname="tests.test_b" name="test_skipped" time="0.00">
  <skipped type="pytest.skip" message="not here">skipped</skipped>
</testcase>
<testcase classname="" name="tests.test_web" time="0.00">
  <skipped type="pytest.skip" message="could not import 'fastapi'">skipped</skipped>
</testcase>
"""
_FAILED_CASE = """
<testcase classname="tests.test_c" name="test_broken" time="0.01">
  <failure message="assert 1 == 2">assert 1 == 2</failure>
</testcase>
"""
_ERROR_CASE = """
<testcase classname="tests.test_c" name="test_fixture" time="0.01">
  <error message="failed on setup">fixture error</error>
</testcase>
"""


def _suite(cases: str) -> str:
    """Return a bare ``<testsuite>`` element that holds ``cases``."""
    return f'<testsuite name="pytest" errors="0" failures="0" skipped="2">{cases}</testsuite>'


def _write_report(tmp_path: Path, body: str) -> tuple[Path, list[Path]]:
    """Write a report that is newer than a one-file code root.

    Returns:
        The report path and the list of code roots to check it against.
    """
    code_root = tmp_path / "src"
    code_root.mkdir()
    source = code_root / "module.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    old = source.stat().st_mtime - 1000
    os.utime(source, (old, old))
    report = tmp_path / "fast-junit.xml"
    report.write_text(f'<?xml version="1.0" encoding="utf-8"?>{body}', encoding="utf-8")
    return report, [code_root]


@pytest.mark.parametrize(
    "body",
    [f"<testsuites>{_suite(_CASES)}</testsuites>", _suite(_CASES)],
    ids=["testsuites-root", "testsuite-root"],
)
def test_passed_count_excludes_skipped_cases(tmp_path: Path, body: str) -> None:
    """Passed counts the cases with no skipped, failure or error child."""
    report, roots = _write_report(tmp_path, body)

    assert junit_passed_count(report, roots) == 3


@pytest.mark.parametrize("bad_case", [_FAILED_CASE, _ERROR_CASE], ids=["failure", "error"])
def test_report_with_failure_or_error_fails(tmp_path: Path, bad_case: str) -> None:
    """A report that records a failure or an error says the fast suite did not pass."""
    report, roots = _write_report(tmp_path, f"<testsuites>{_suite(_CASES + bad_case)}</testsuites>")

    with pytest.raises(AssertionError, match="fast suite did not pass"):
        junit_passed_count(report, roots)


def test_missing_report_names_the_path(tmp_path: Path) -> None:
    """A report path with no file there fails and names that path."""
    missing = tmp_path / "nowhere" / "fast-junit.xml"

    with pytest.raises(AssertionError, match="nowhere/fast-junit.xml"):
        junit_passed_count(missing, [tmp_path])


def test_report_older_than_a_source_file_is_stale(tmp_path: Path) -> None:
    """A ``*.py`` file newer than the report, at any depth, makes the report stale."""
    report, roots = _write_report(tmp_path, _suite(_CASES))
    nested = roots[0] / "pkg" / "late.py"
    nested.parent.mkdir()
    nested.write_text("LATE = 1\n", encoding="utf-8")
    report_time = report.stat().st_mtime
    os.utime(nested, (report_time + 10, report_time + 10))

    with pytest.raises(AssertionError, match="stale") as excinfo:
        junit_passed_count(report, roots)
    assert "late.py" in str(excinfo.value)
