# Description:
# Unit tests for PII detection rules (PII-001..PII-004).

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.file_scanner import scan_file_content
from src.models import Severity
from src.rules.pii import PII_RULES


def _scan(content: str) -> list[tuple[str, Severity]]:
    findings = scan_file_content(Path("test.txt"), content, rules=PII_RULES)
    return [(f.rule_id, f.severity) for f in findings]


class TestEmailDetection:
    def test_detects_real_email(self) -> None:
        results = _scan("contact = 'john.smith@realdomain.io'")
        assert ("PII-001", Severity.MEDIUM) in results

    def test_skips_example_domain(self) -> None:
        results = _scan("contact = 'user@example.com'")
        rule_ids = [r[0] for r in results]
        assert "PII-001" not in rule_ids

    def test_skips_test_domain(self) -> None:
        results = _scan("email = 'admin@test.com'")
        rule_ids = [r[0] for r in results]
        assert "PII-001" not in rule_ids

    def test_detects_corporate_email(self) -> None:
        results = _scan("ceo = 'alice@acme-corp.io'")
        assert ("PII-001", Severity.MEDIUM) in results


class TestPhoneDetection:
    def test_detects_formatted_phone(self) -> None:
        results = _scan("phone = '416-555-0192'")
        assert ("PII-002", Severity.MEDIUM) in results

    def test_detects_us_format(self) -> None:
        results = _scan("contact = '(800) 555-1234'")
        assert ("PII-002", Severity.MEDIUM) in results

    def test_skips_555_placeholder(self) -> None:
        # 555-555-5555 is the canonical placeholder — skip it.
        results = _scan("phone = '555-555-5555'")
        rule_ids = [r[0] for r in results]
        assert "PII-002" not in rule_ids


class TestSinDetection:
    def test_detects_canadian_sin(self) -> None:
        results = _scan("sin = '111 111 111'")
        assert ("PII-003", Severity.CRITICAL) in results

    def test_detects_hyphenated_sin(self) -> None:
        results = _scan("sin = '111-111-111'")
        assert ("PII-003", Severity.CRITICAL) in results


class TestSsnDetection:
    def test_detects_us_ssn(self) -> None:
        results = _scan("ssn = '111-11-1111'")
        assert ("PII-004", Severity.CRITICAL) in results

    def test_misses_invalid_ssn_000_prefix(self) -> None:
        results = _scan("ref = '000-12-3456'")
        rule_ids = [r[0] for r in results]
        assert "PII-004" not in rule_ids
