# Description:
# Formats and outputs scan results to the terminal (with color) or as JSON.
# Falls back to plain text when stdout is not a TTY or color is disabled.

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from io import TextIOWrapper
from pathlib import Path
from typing import TextIO

from src.models import Finding, ScanResult, Severity

log = logging.getLogger(__name__)

# ANSI color codes — only used when output is a TTY.
_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[31m"
_BRIGHT_RED = "\033[91m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_DIM = "\033[2m"
_WHITE = "\033[97m"

_SEVERITY_COLOR: dict[Severity, str] = {
    Severity.CRITICAL: _BRIGHT_RED,
    Severity.HIGH: _RED,
    Severity.MEDIUM: _YELLOW,
    Severity.LOW: _CYAN,
}

_SEP_DOUBLE = "=" * 70
_SEP_SINGLE = "-" * 70


def _supports_color(stream: TextIO) -> bool:
    return hasattr(stream, "isatty") and stream.isatty()


class Reporter:
    def __init__(self, stream: TextIO = sys.stdout, color: bool | None = None) -> None:
        self._stream = stream
        self._color = _supports_color(stream) if color is None else color

    def _c(self, text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if self._color else text

    def _line(self, text: str = "") -> None:
        print(text, file=self._stream)

    def _severity_badge(self, severity: Severity) -> str:
        color = _SEVERITY_COLOR.get(severity, "")
        label = f"[{severity.value}]"
        return self._c(label, _BOLD + color)

    def print_report(self, result: ScanResult, scan_label: str = "") -> None:
        log.debug("print_report findings=%d", result.total)
        self._line()
        self._line(self._c(_SEP_DOUBLE, _BOLD))
        title = "  CODE SCANNER - Security & Privacy Report"
        if scan_label:
            title += f"  ({scan_label})"
        self._line(self._c(title, _BOLD + _WHITE))
        self._line(self._c(_SEP_DOUBLE, _BOLD))
        self._line()

        count_str = f"{result.scanned_files} file(s), {result.scanned_lines:,} line(s)"
        self._line(f"  Scanned : {count_str}")

        if result.total == 0:
            self._line(f"  Found   : {self._c('0 issues', _GREEN + _BOLD)}")
            self._line()
            self._line(self._c(_SEP_DOUBLE, _BOLD))
            self._line(self._c("  RESULT: [CLEAN] No issues found.", _GREEN + _BOLD))
            self._line(self._c(_SEP_DOUBLE, _BOLD))
            self._line()
            return

        by_sev = result.by_severity()
        counts = ", ".join(
            f"{len(v)} {s.value}"
            for s, v in by_sev.items()
            if v
        )
        self._line(f"  Found   : {self._c(str(result.total) + ' issue(s)', _RED + _BOLD)} ({counts})")
        if result.skipped_files:
            self._line(f"  Skipped : {len(result.skipped_files)} file(s) (matched .scannerignore)")
        self._line()

        # Print findings grouped by severity (most severe first).
        for severity in Severity:
            findings = by_sev[severity]
            if not findings:
                continue
            for finding in findings:
                self._print_finding(finding)

        # Summary footer.
        self._line(self._c(_SEP_DOUBLE, _BOLD))
        if result.has_blocking_issues():
            msg = "  RESULT: [FAILED] CRITICAL or HIGH issues found. Fix before publishing."
            self._line(self._c(msg, _BRIGHT_RED + _BOLD))
        else:
            msg = "  RESULT: [WARNING] Low/Medium issues found. Review before publishing."
            self._line(self._c(msg, _YELLOW + _BOLD))
        self._line(self._c(_SEP_DOUBLE, _BOLD))
        self._line()

    def _print_finding(self, f: Finding) -> None:
        self._line(self._c(_SEP_SINGLE, _DIM))

        header = f"  {self._severity_badge(f.severity)}  {self._c(f.rule_name, _BOLD)}  [{f.rule_id}]"
        self._line(header)
        self._line()

        loc = f"{f.file_path}:{f.line_number}" if f.line_number else f.file_path
        self._line(f"  {'File':<15}: {self._c(loc, _CYAN)}")
        self._line(f"  {'Match':<15}: {self._c(f.matched_text, _YELLOW)}")
        if f.line_content and f.line_content != "<filename match>":
            self._line(f"  {'Line':<15}: {self._c(f.line_content, _DIM)}")
        self._line()

        desc_lines = _wrap(f.description, width=55)
        rec_lines = _wrap(f.recommendation, width=55)

        self._line(f"  {'Description':<15}: {desc_lines[0]}")
        for extra in desc_lines[1:]:
            self._line(f"  {'':<15}  {extra}")

        self._line(f"  {'Recommendation':<15}: {rec_lines[0]}")
        for extra in rec_lines[1:]:
            self._line(f"  {'':<15}  {extra}")

        self._line()

    def print_json(self, result: ScanResult, scan_label: str = "") -> None:
        log.debug("print_json findings=%d", result.total)
        data = {
            "scan_label": scan_label,
            "summary": {
                "scanned_files": result.scanned_files,
                "scanned_lines": result.scanned_lines,
                "total_findings": result.total,
                "has_blocking_issues": result.has_blocking_issues(),
                "by_severity": {
                    s.value: len(v) for s, v in result.by_severity().items()
                },
                "skipped_files": result.skipped_files,
            },
            "findings": [_finding_to_dict(f) for f in result.findings],
        }
        print(json.dumps(data, indent=2), file=self._stream)

    def save_report(self, result: ScanResult, path: Path, scan_label: str = "") -> None:
        log.debug("save_report path=%s", path)
        with path.open("w", encoding="utf-8") as fh:
            data = {
                "scan_label": scan_label,
                "summary": {
                    "scanned_files": result.scanned_files,
                    "scanned_lines": result.scanned_lines,
                    "total_findings": result.total,
                    "has_blocking_issues": result.has_blocking_issues(),
                    "by_severity": {
                        s.value: len(v) for s, v in result.by_severity().items()
                    },
                },
                "findings": [_finding_to_dict(f) for f in result.findings],
            }
            json.dump(data, fh, indent=2)
        print(f"\nReport saved to: {path}", file=self._stream)


def _finding_to_dict(f: Finding) -> dict:
    return {
        "rule_id": f.rule_id,
        "rule_name": f.rule_name,
        "severity": f.severity.value,
        "file_path": f.file_path,
        "line_number": f.line_number,
        "line_content": f.line_content,
        "matched_text": f.matched_text,
        "description": f.description,
        "recommendation": f.recommendation,
    }


def _wrap(text: str, width: int = 70) -> list[str]:
    """Naive word-wrap that respects existing line breaks."""
    lines: list[str] = []
    for paragraph in text.split(". "):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        while len(paragraph) > width:
            cut = paragraph.rfind(" ", 0, width)
            if cut == -1:
                cut = width
            lines.append(paragraph[:cut])
            paragraph = paragraph[cut:].lstrip()
        if paragraph:
            lines.append(paragraph)
    return lines or [""]
