# Description:
# Data models for code scanner findings and results.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @property
    def order(self) -> int:
        return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}[self.value]

    def __lt__(self, other: "Severity") -> bool:
        return self.order < other.order


@dataclass
class Finding:
    rule_id: str
    rule_name: str
    severity: Severity
    file_path: str
    line_number: int
    line_content: str
    matched_text: str
    description: str
    recommendation: str


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    scanned_files: int = 0
    scanned_lines: int = 0
    skipped_files: list[str] = field(default_factory=list)

    def by_severity(self) -> dict[Severity, list[Finding]]:
        grouped: dict[Severity, list[Finding]] = {s: [] for s in Severity}
        for f in self.findings:
            grouped[f.severity].append(f)
        return grouped

    def has_blocking_issues(self) -> bool:
        return any(f.severity in (Severity.CRITICAL, Severity.HIGH) for f in self.findings)

    @property
    def total(self) -> int:
        return len(self.findings)
