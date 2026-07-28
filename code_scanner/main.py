#!/usr/bin/env python3
# Description:
# CLI entry point for the public code scanner.
# Scans files for secrets, PII, and internal infrastructure details before
# they are published to a public repository.
#
# Usage:
#   python main.py [--staged] [--full] [--diff BRANCH]
#                  [--path PATH] [--min-severity LEVEL]
#                  [--output json] [--report FILE] [--no-color]

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

# Ensure src/ is importable when running as `python main.py` from this directory.
_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from src.file_scanner import scan_directory, scan_files_list
from src.git import get_diff_files, get_repo_root, get_staged_files, read_staged_content
from src.models import ScanResult, Severity
from src.reporter import Reporter
from src.rules import ALL_RULES

_DEFAULT_SCAN_PATH = _HERE.parent  # public/

_IGNORE_FILE = _HERE / ".scannerignore"

_LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(stream=sys.stderr, format=_LOG_FORMAT, level=level)


def _load_ignore_patterns(ignore_file: Path) -> list[re.Pattern[str]]:
    """Parse .scannerignore — one glob-like pattern per line, # comments ignored."""
    if not ignore_file.exists():
        return []
    patterns: list[re.Pattern[str]] = []
    for raw_line in ignore_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Convert simple glob wildcards to regex equivalents.
        regex = re.escape(line).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
        try:
            patterns.append(re.compile(regex))
        except re.error:
            logging.warning("Invalid pattern in .scannerignore: %s", line)
    return patterns


def _min_severity_filter(result: ScanResult, min_severity: Severity) -> ScanResult:
    """Return a new ScanResult with only findings at or above `min_severity`."""
    filtered = [f for f in result.findings if f.severity.order <= min_severity.order]
    return ScanResult(
        findings=filtered,
        scanned_files=result.scanned_files,
        scanned_lines=result.scanned_lines,
        skipped_files=result.skipped_files,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="code_scanner",
        description=(
            "Scan code changes for secrets, PII, and internal infrastructure details "
            "before publishing to a public repository."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Scan modes (pick one; default is --staged):
  --staged          Scan git staged files under --path
  --full            Scan all files under --path recursively
  --diff BRANCH     Scan files changed between BRANCH and HEAD

Examples:
  python main.py                          # scan staged files under public/
  python main.py --full                   # scan all files under public/
  python main.py --diff main              # scan changes vs main branch
  python main.py --full --min-severity HIGH
  python main.py --staged --output json --report findings.json
""",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--staged",
        action="store_true",
        default=False,
        help="Scan git-staged files (default mode)",
    )
    mode.add_argument(
        "--full",
        action="store_true",
        default=False,
        help="Scan all files under --path recursively",
    )
    mode.add_argument(
        "--diff",
        metavar="BRANCH",
        default=None,
        help="Scan files changed between BRANCH and HEAD",
    )
    parser.add_argument(
        "--path",
        default=str(_DEFAULT_SCAN_PATH),
        help=f"Root directory to scan (default: {_DEFAULT_SCAN_PATH})",
    )
    parser.add_argument(
        "--min-severity",
        choices=[s.value for s in Severity],
        default="LOW",
        help="Minimum severity level to report (default: LOW — report everything)",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--report",
        metavar="FILE",
        default=None,
        help="Save JSON report to FILE (always JSON, regardless of --output)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        help="Disable colored output",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=False,
        help="Enable debug logging",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    _setup_logging(args.verbose)

    log = logging.getLogger(__name__)

    scan_path = Path(args.path).resolve()
    if not scan_path.exists():
        print(f"ERROR: scan path does not exist: {scan_path}", file=sys.stderr)
        return 2

    ignore_patterns = _load_ignore_patterns(_IGNORE_FILE)
    min_severity = Severity(args.min_severity)
    reporter = Reporter(color=not args.no_color)

    # --- Determine scan mode ---
    # Default to --staged if neither --full nor --diff was given.
    use_full = args.full
    diff_branch = args.diff
    use_staged = args.staged or (not use_full and diff_branch is None)

    # --- Execute scan ---
    result: ScanResult

    if use_full:
        scan_label = f"full scan of {scan_path}"
        print(f"\nScanning all files under: {scan_path}", file=sys.stderr)
        result = scan_directory(scan_path, ignore_patterns=ignore_patterns)

    elif diff_branch:
        scan_label = f"diff vs {diff_branch}"
        print(f"\nScanning files changed vs '{diff_branch}'...", file=sys.stderr)
        try:
            repo_root = get_repo_root(scan_path)
            files = get_diff_files(repo_root, diff_branch, path_filter=scan_path)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        if not files:
            print("No changed files found.", file=sys.stderr)
            result = ScanResult()
        else:
            print(f"Found {len(files)} changed file(s).", file=sys.stderr)
            result = scan_files_list(files, ignore_patterns=ignore_patterns)

    else:  # use_staged
        scan_label = "staged files"
        print("\nScanning git staged files...", file=sys.stderr)
        try:
            repo_root = get_repo_root(scan_path)
            files = get_staged_files(repo_root, path_filter=scan_path)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        if not files:
            print("No staged files found under the scan path.", file=sys.stderr)
            result = ScanResult()
        else:
            print(f"Found {len(files)} staged file(s).", file=sys.stderr)

            def _staged_reader(p: Path) -> str | None:
                return read_staged_content(repo_root, p)

            result = scan_files_list(
                files,
                content_reader=_staged_reader,
                ignore_patterns=ignore_patterns,
            )

    # --- Apply severity filter ---
    result = _min_severity_filter(result, min_severity)

    # --- Output ---
    if args.output == "json":
        reporter.print_json(result, scan_label=scan_label)
    else:
        reporter.print_report(result, scan_label=scan_label)

    if args.report:
        report_path = Path(args.report)
        reporter.save_report(result, report_path, scan_label=scan_label)

    # Exit code: 1 = blocking issues (CRITICAL/HIGH), 0 = clean or low/medium only.
    return 1 if result.has_blocking_issues() else 0


if __name__ == "__main__":
    sys.exit(main())
