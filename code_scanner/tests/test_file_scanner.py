# Description:
# Integration-style tests for the file_scanner module — exercises scan_file,
# scan_directory, and the clean/dirty fixture files.

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.file_scanner import scan_directory, scan_file, scan_file_content
from src.models import Severity

FIXTURES = Path(__file__).parent / "fixtures"


class TestScanFileContent:
    def test_empty_content_returns_no_findings(self) -> None:
        findings = scan_file_content(Path("x.py"), "")
        assert findings == []

    def test_long_lines_are_skipped(self) -> None:
        long_line = "password = 'abc' " + "x" * 3000
        findings = scan_file_content(Path("x.py"), long_line)
        assert findings == []

    def test_multiple_findings_on_same_file(self) -> None:
        content = (
            'password = "realvalue"\n'
            'STRIPE = "sk_test_FAKE_KEY_123456789012345678901234"\n'
        )
        findings = scan_file_content(Path("x.py"), content)
        rule_ids = {f.rule_id for f in findings}
        assert "SEC-009" in rule_ids
        assert "SEC-005" in rule_ids


class TestScanFile:
    def test_dirty_fixture_has_findings(self) -> None:
        dirty = FIXTURES / "sample_dirty.txt"
        findings = scan_file(dirty)
        assert len(findings) > 0

    def test_dirty_fixture_has_critical_findings(self) -> None:
        dirty = FIXTURES / "sample_dirty.txt"
        findings = scan_file(dirty)
        severities = {f.severity for f in findings}
        assert Severity.CRITICAL in severities

    def test_clean_fixture_has_no_findings(self) -> None:
        clean = FIXTURES / "sample_clean.txt"
        findings = scan_file(clean)
        assert findings == [], f"Unexpected findings: {[f.rule_id for f in findings]}"

    def test_filename_rule_triggers_on_env_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("API_KEY=real_value\n", encoding="utf-8")
        findings = scan_file(env_file)
        rule_ids = {f.rule_id for f in findings}
        # FT-001 (filename) + SEC-008 (content) should both fire.
        assert "FT-001" in rule_ids

    def test_binary_file_skipped(self, tmp_path: Path) -> None:
        binary = tmp_path / "image.bin"
        binary.write_bytes(b"\x00\x01\x02\x03" * 100)
        findings = scan_file(binary)
        assert findings == []


class TestScanDirectory:
    def test_fixtures_dir_dirty_has_findings(self) -> None:
        result = scan_directory(FIXTURES)
        assert result.total > 0
        assert result.scanned_files >= 2

    def test_ignore_pattern_excludes_file(self) -> None:
        import re

        result = scan_directory(FIXTURES, ignore_patterns=[re.compile(r"sample_dirty")])
        # With dirty file ignored, only clean file is scanned — 0 findings expected.
        assert result.total == 0

    def test_scan_result_tracks_file_count(self) -> None:
        result = scan_directory(FIXTURES)
        assert result.scanned_files == 2  # clean + dirty
