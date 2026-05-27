"""Tests for the independent auditor — report parsing."""

from __future__ import annotations

import pytest

from skill_evolution.core.auditor import Auditor, AuditFinding, AuditReport, AuditSeverity


class TestAuditReportParsing:
    def test_parse_passing_report(self):
        text = """\
===CHECK: overfitting===
Severity: PASS
Description: No signs of overfitting to specific tasks
Suggestion:

===CHECK: hardcoding===
Severity: PASS
Description: No hardcoded values found
Suggestion:

===OVERALL===
Severity: PASS
Summary: Skill is well-structured and generalizable.
"""
        auditor = Auditor.__new__(Auditor)
        report = auditor._parse_report(text)

        assert report.passed is True
        assert report.overall == AuditSeverity.PASS
        assert len(report.findings) == 2
        assert report.findings[0].check == "overfitting"
        assert report.findings[0].severity == AuditSeverity.PASS
        assert "well-structured" in report.summary

    def test_parse_failing_report(self):
        text = """\
===CHECK: overfitting===
Severity: FAIL
Description: Skill contains task-specific rules
Suggestion: Generalize the SQL injection check to cover all injection types

===CHECK: consistency===
Severity: WARNING
Description: Minor contradiction between sections
Suggestion: Align sections 2 and 4

===OVERALL===
Severity: FAIL
Summary: Skill has overfitting issues that need resolution.
"""
        auditor = Auditor.__new__(Auditor)
        report = auditor._parse_report(text)

        assert report.passed is False
        assert report.overall == AuditSeverity.FAIL
        assert report.findings[0].severity == AuditSeverity.FAIL
        assert report.findings[1].severity == AuditSeverity.WARNING

    def test_parse_warning_report(self):
        text = """\
===CHECK: generalizability===
Severity: WARNING
Description: Could be broader
Suggestion: Add more domains

===OVERALL===
Severity: WARNING
Summary: Minor concerns.
"""
        auditor = Auditor.__new__(Auditor)
        report = auditor._parse_report(text)

        assert report.passed is True
        assert report.overall == AuditSeverity.WARNING

    def test_parse_unparseable_no_checks_defaults_to_fail(self):
        auditor = Auditor.__new__(Auditor)
        report = auditor._parse_report("This is just random text with no structure.")
        assert report.passed is False
        assert report.overall == AuditSeverity.FAIL
        assert "unparseable" in report.summary.lower()

    def test_parse_checks_but_no_overall_defaults_to_warning(self):
        text = """\
===CHECK: overfitting===
Severity: PASS
Description: No overfitting
Suggestion:
"""
        auditor = Auditor.__new__(Auditor)
        report = auditor._parse_report(text)
        assert report.passed is True
        assert report.overall == AuditSeverity.WARNING
        assert len(report.findings) == 1

    def test_parse_overall_pass_explicitly(self):
        text = """\
===CHECK: consistency===
Severity: PASS
Description: All good
Suggestion:

===OVERALL===
Severity: PASS
Summary: Clean skill.
"""
        auditor = Auditor.__new__(Auditor)
        report = auditor._parse_report(text)
        assert report.overall == AuditSeverity.PASS

    def test_audit_report_passed_property(self):
        report = AuditReport(findings=[], overall=AuditSeverity.PASS, summary="ok")
        assert report.passed is True

        report = AuditReport(findings=[], overall=AuditSeverity.WARNING, summary="ok")
        assert report.passed is True

        report = AuditReport(findings=[], overall=AuditSeverity.FAIL, summary="bad")
        assert report.passed is False
