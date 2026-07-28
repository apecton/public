# Description:
# Core scanning logic — applies rules to a single file and returns findings.
# Handles binary detection, comment suppression, and per-line allowlist checks.

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable

from src.models import Finding, ScanResult, Severity
from src.rules import ALL_RULES
from src.rules.base_rule import Rule

log = logging.getLogger(__name__)

# Lines whose non-whitespace content starts with a comment marker are lower risk.
# We still scan them (secrets in comments are a real leak) but the scanner
# records the line as-is so reviewers have full context.
_COMMENT_RE = re.compile(r"^\s*(#|//|--|/\*|\*|<!--)")

# Maximum line length to scan; skip absurdly long lines (minified JS, base64 blobs).
_MAX_LINE_LEN = 2000

# Chunk size for binary detection.
_BINARY_CHECK_BYTES = 8192


def _is_binary(content: bytes) -> bool:
    """Return True if the content looks like a binary file."""
    return b"\x00" in content[:_BINARY_CHECK_BYTES]


def _truncate(text: str, max_len: int = 80) -> str:
    return text[:max_len] + "..." if len(text) > max_len else text


def _match_suppressed(match_text: str, allowlist: list[re.Pattern[str]] | None) -> bool:
    """Return True if the matched text is on the allowlist (should be suppressed)."""
    if not allowlist:
        return False
    return any(pattern.search(match_text) for pattern in allowlist)


def scan_file_content(
    file_path: Path,
    content: str,
    rules: list[Rule] | None = None,
) -> list[Finding]:
    """
    Scan the text content of a file against all content-based rules.

    Args:
        file_path: Path used for reporting (does not need to exist on disk).
        content: Full text content of the file.
        rules: Override the default rule set (useful for testing).

    Returns:
        List of Finding objects, one per matched rule per line.
    """
    log.debug("scan_file_content file=%s content_len=%d", file_path, len(content))
    active_rules = [r for r in (rules or ALL_RULES) if not r.filename_only]
    findings: list[Finding] = []

    for line_number, line in enumerate(content.splitlines(), start=1):
        if len(line) > _MAX_LINE_LEN:
            continue

        for rule in active_rules:
            match = rule.pattern.search(line)
            if not match:
                continue

            matched_text = match.group(0)
            if _match_suppressed(matched_text, rule.allowlist):
                log.debug("suppressed %s match on line %d of %s", rule.id, line_number, file_path)
                continue

            findings.append(
                Finding(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    severity=rule.severity,
                    file_path=str(file_path),
                    line_number=line_number,
                    line_content=_truncate(line.strip()),
                    matched_text=_truncate(matched_text, 60),
                    description=rule.description,
                    recommendation=rule.recommendation,
                )
            )

    log.debug("scan_file_content findings=%d", len(findings))
    return findings


def scan_file(
    file_path: Path,
    content_reader: Callable[[Path], str | None] | None = None,
    rules: list[Rule] | None = None,
) -> list[Finding]:
    """
    Scan a file against all rules, including filename-based rules.

    Args:
        file_path: Absolute path to the file.
        content_reader: Optional callable to supply file content (e.g. git staging area reader).
                        Falls back to reading from disk.
        rules: Override the default rule set.

    Returns:
        List of Finding objects.
    """
    log.debug("scan_file %s", file_path)
    active_rules = rules or ALL_RULES
    findings: list[Finding] = []

    # --- Filename-only rules ---
    filename = file_path.name
    full_path_str = str(file_path)
    for rule in active_rules:
        if not rule.filename_only:
            continue
        if rule.pattern.search(filename) or rule.pattern.search(full_path_str):
            findings.append(
                Finding(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    severity=rule.severity,
                    file_path=str(file_path),
                    line_number=0,
                    line_content="<filename match>",
                    matched_text=filename,
                    description=rule.description,
                    recommendation=rule.recommendation,
                )
            )

    # --- Content rules ---
    try:
        if content_reader is not None:
            text = content_reader(file_path)
        else:
            raw_bytes = file_path.read_bytes()
            if _is_binary(raw_bytes):
                log.debug("skipping binary file %s", file_path)
                return findings
            text = raw_bytes.decode("utf-8", errors="replace")
    except (OSError, PermissionError) as exc:
        log.warning("cannot read %s: %s", file_path, exc)
        return findings

    if text is None:
        return findings

    findings.extend(scan_file_content(file_path, text, active_rules))
    log.debug("scan_file %s total_findings=%d", file_path, len(findings))
    return findings


def scan_directory(
    directory: Path,
    ignore_patterns: list[re.Pattern[str]] | None = None,
    rules: list[Rule] | None = None,
) -> ScanResult:
    """
    Recursively scan all files under `directory`.

    Args:
        directory: Root directory to scan.
        ignore_patterns: Compiled patterns; matching files are skipped.
        rules: Override the default rule set.

    Returns:
        ScanResult with all findings accumulated across all files.
    """
    log.debug("scan_directory %s", directory)
    result = ScanResult()

    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue

        rel = path.relative_to(directory)
        rel_str = rel.as_posix()

        if ignore_patterns and any(p.search(rel_str) for p in ignore_patterns):
            log.debug("ignored: %s", rel_str)
            result.skipped_files.append(rel_str)
            continue

        findings = scan_file(path, rules=rules)
        result.findings.extend(findings)
        result.scanned_files += 1

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            result.scanned_lines += content.count("\n") + 1
        except OSError:
            pass

    log.debug(
        "scan_directory done: files=%d lines=%d findings=%d",
        result.scanned_files,
        result.scanned_lines,
        result.total,
    )
    return result


def scan_files_list(
    files: list[Path],
    content_reader: Callable[[Path], str | None] | None = None,
    ignore_patterns: list[re.Pattern[str]] | None = None,
    rules: list[Rule] | None = None,
) -> ScanResult:
    """
    Scan a specific list of files (e.g. from git staged/diff output).

    Args:
        files: List of absolute file paths.
        content_reader: Optional callable to supply staged content.
        ignore_patterns: Compiled patterns; matching files are skipped.
        rules: Override the default rule set.

    Returns:
        ScanResult with all findings.
    """
    log.debug("scan_files_list count=%d", len(files))
    result = ScanResult()

    for file_path in files:
        rel_str = file_path.as_posix()
        if ignore_patterns and any(p.search(rel_str) for p in ignore_patterns):
            log.debug("ignored: %s", rel_str)
            result.skipped_files.append(rel_str)
            continue

        findings = scan_file(file_path, content_reader=content_reader, rules=rules)
        result.findings.extend(findings)
        result.scanned_files += 1

    log.debug("scan_files_list done: findings=%d", result.total)
    return result
