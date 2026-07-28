# Description:
# Detection rules for secrets: API keys, tokens, private keys, passwords, JWTs,
# database URLs with credentials, and bearer tokens.

import re

from src.models import Severity
from src.rules.base_rule import Rule

# Values that look like secrets but are clearly placeholders.
_PLACEHOLDER_PATTERN = re.compile(
    r"(?i)(your[_-]?(password|secret|key|token)|change[_-]?me|replace[_-]?me"
    r"|<[A-Z_]+>|xxx+|placeholder|changeit|example|dummy|test123|password123"
    r"|insert[_-]?here|todo|fixme|\*{3,})"
)

SECRETS_RULES: list[Rule] = [
    Rule(
        id="SEC-001",
        name="Private Key Block",
        severity=Severity.CRITICAL,
        pattern=re.compile(
            r"-----BEGIN\s+(RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE
        ),
        description="A private key block was found. Private keys must never be committed to version control.",
        recommendation=(
            "Remove the key immediately. Store private keys in a secrets manager or environment variable. "
            "If already pushed, rotate the key now."
        ),
    ),
    Rule(
        id="SEC-002",
        name="AWS Access Key ID",
        severity=Severity.CRITICAL,
        pattern=re.compile(r"AKIA[0-9A-Z]{16}"),
        description="An AWS access key ID was detected.",
        recommendation=(
            "Remove the key. Use IAM roles, AWS Secrets Manager, or environment variables. "
            "Rotate the key if it was exposed."
        ),
    ),
    Rule(
        id="SEC-003",
        name="AWS Secret Access Key",
        severity=Severity.CRITICAL,
        pattern=re.compile(
            r'(?i)(aws[_\-\s]?secret[_\-\s]?access[_\-\s]?key|aws[_\-\s]?secret)'
            r'\s*[:=]\s*["\']?([A-Za-z0-9/+=]{40})["\']?'
        ),
        description="An AWS secret access key was detected in the code.",
        recommendation="Use environment variables or AWS Secrets Manager. Rotate the key immediately.",
        allowlist=[_PLACEHOLDER_PATTERN],
    ),
    Rule(
        id="SEC-004",
        name="GitHub Token",
        severity=Severity.CRITICAL,
        pattern=re.compile(
            r"(ghp_[A-Za-z0-9_]{36,}"
            r"|ghs_[A-Za-z0-9_]{36,}"
            r"|gho_[A-Za-z0-9_]{36,}"
            r"|github_pat_[A-Za-z0-9_]{22,})"
        ),
        description="A GitHub personal access token or app token was detected.",
        recommendation="Revoke this token immediately via GitHub Settings > Developer settings > Tokens.",
    ),
    Rule(
        id="SEC-005",
        name="Stripe Secret Key",
        severity=Severity.CRITICAL,
        pattern=re.compile(r"sk_(live|test)_[0-9a-zA-Z]{24,}"),
        description="A Stripe secret key was detected. Live keys grant full API access to your Stripe account.",
        recommendation=(
            "Remove the key. Use environment variables. If it is a live key, rotate it in the "
            "Stripe Dashboard immediately."
        ),
    ),
    Rule(
        id="SEC-006",
        name="Twilio Auth Token",
        severity=Severity.HIGH,
        pattern=re.compile(
            r'(?i)(twilio[_\-\s]?auth[_\-\s]?token|auth[_\-\s]?token)\s*[:=]\s*["\']?([0-9a-f]{32})["\']?'
        ),
        description="A Twilio auth token (32-character hex string) was detected.",
        recommendation="Store Twilio credentials in environment variables. Rotate via the Twilio Console.",
        allowlist=[_PLACEHOLDER_PATTERN],
    ),
    Rule(
        id="SEC-007",
        name="Mailchimp API Key",
        severity=Severity.HIGH,
        pattern=re.compile(r"[0-9a-f]{32}-us\d{1,2}"),
        description="A Mailchimp API key was detected.",
        recommendation="Use environment variables. Revoke and regenerate the key via the Mailchimp account panel.",
    ),
    Rule(
        id="SEC-008",
        name="Generic API Key or Token",
        severity=Severity.HIGH,
        pattern=re.compile(
            r'(?i)(api[_\-]?key|api[_\-]?token|access[_\-]?token|auth[_\-]?token|secret[_\-]?key)'
            r'\s*[:=]\s*["\']([A-Za-z0-9\-_]{16,})["\']'
        ),
        description="A generic API key or token assignment was detected.",
        recommendation=(
            "Use environment variables (os.environ) instead of hardcoding credentials in source files."
        ),
        allowlist=[_PLACEHOLDER_PATTERN],
    ),
    Rule(
        id="SEC-009",
        name="Hardcoded Password or Secret",
        severity=Severity.HIGH,
        pattern=re.compile(
            r'(?i)(password|passwd|secret|pwd|pass)\s*[:=]\s*["\']([^"\']{4,})["\']'
        ),
        description="A hardcoded password or secret value was found in an assignment.",
        recommendation=(
            "Move credentials to environment variables. Never hardcode secrets in source files "
            "that may be committed."
        ),
        allowlist=[_PLACEHOLDER_PATTERN],
    ),
    Rule(
        id="SEC-010",
        name="JWT Token",
        severity=Severity.HIGH,
        pattern=re.compile(
            r"eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_.+/]*"
        ),
        description="A JWT token (three base64url-encoded segments) was detected.",
        recommendation=(
            "Remove embedded tokens. Generate tokens at runtime via your auth service. "
            "If this token grants real access, revoke it."
        ),
    ),
    Rule(
        id="SEC-011",
        name="Database URL with Credentials",
        severity=Severity.CRITICAL,
        pattern=re.compile(
            r"(?i)(postgres|postgresql|mysql|mongodb|redis|mssql)"
            r":\/\/[^:\s@]+:[^@\s]+@[^\s/\"']+"
        ),
        description="A database connection URL containing credentials was detected.",
        recommendation=(
            "Use environment variables for database URLs. Never embed credentials in connection strings "
            "in source code."
        ),
    ),
    Rule(
        id="SEC-012",
        name="Bearer Token",
        severity=Severity.HIGH,
        pattern=re.compile(
            r'(?i)bearer\s+["\']?([A-Za-z0-9\-._~+/]{20,}=*)["\']?'
        ),
        description="A Bearer token was hardcoded in source code.",
        recommendation=(
            "Inject tokens at runtime via environment variables or a secrets manager, not in source files."
        ),
        allowlist=[_PLACEHOLDER_PATTERN],
    ),
]
