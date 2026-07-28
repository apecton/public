# Description:
# Detection rules for personally identifiable information (PII):
# email addresses, phone numbers, Canadian SINs, and US SSNs.

import re

from src.models import Severity
from src.rules.base_rule import Rule

# Common placeholder / test email domains — lower the noise for code examples.
_EMAIL_PLACEHOLDER = re.compile(
    r"@(example\.com|test\.com|domain\.com|yourdomain\.com|sample\.com"
    r"|placeholder\.com|acme\.com|foo\.com|bar\.com|email\.com"
    r"|company\.com|mysite\.com|noone\.com|noreply\.|localhost)",
    re.IGNORECASE,
)

# Suppress only when 555 is the area code (common test numbers), not in the exchange.
# Pattern anchors to the start of the matched phone number (match.group(0)).
_PHONE_PLACEHOLDER = re.compile(
    r"^(\+?1[-.\s]?)?\(?555\)?[-.\s]\d{3}[-.\s]\d{4}"
)

PII_RULES: list[Rule] = [
    Rule(
        id="PII-001",
        name="Email Address",
        severity=Severity.MEDIUM,
        pattern=re.compile(
            r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
        ),
        description=(
            "An email address was detected. Real user emails or internal team addresses "
            "must not appear in public code."
        ),
        recommendation=(
            "Replace with a placeholder (e.g. user@example.com) or load from config/environment. "
            "Audit whether this is a real address or a test fixture."
        ),
        allowlist=[_EMAIL_PLACEHOLDER],
    ),
    Rule(
        id="PII-002",
        name="Phone Number (North American)",
        severity=Severity.MEDIUM,
        pattern=re.compile(
            r"(?<!\d)(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"
        ),
        description="A North American phone number pattern was detected.",
        recommendation=(
            "Replace real phone numbers with test numbers (e.g. 555-555-5555) or load from configuration."
        ),
        allowlist=[_PHONE_PLACEHOLDER],
    ),
    Rule(
        id="PII-003",
        name="Canadian Social Insurance Number (SIN)",
        severity=Severity.CRITICAL,
        pattern=re.compile(r"\b\d{3}[-\s]\d{3}[-\s]\d{3}\b"),
        description="A pattern matching a Canadian SIN (3-3-3 digit format) was detected.",
        recommendation=(
            "Remove immediately. SINs are highly sensitive personal data and must never appear in code, "
            "logs, or configuration files."
        ),
    ),
    Rule(
        id="PII-004",
        name="US Social Security Number (SSN)",
        severity=Severity.CRITICAL,
        pattern=re.compile(r"\b(?!000|666|9\d{2})\d{3}[-\s](?!00)\d{2}[-\s](?!0000)\d{4}\b"),
        description="A pattern matching a US SSN (3-2-4 digit format) was detected.",
        recommendation=(
            "Remove immediately. SSNs are highly sensitive personal data and must never appear in code, "
            "logs, or configuration files."
        ),
    ),
]
