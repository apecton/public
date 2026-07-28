# Description:
# Detection rules for internal infrastructure information: private IP addresses,
# internal hostnames, user home directory paths, and database hostnames.

import re

from src.models import Severity
from src.rules.base_rule import Rule

# IPs that are safe and well-known — suppress them.
_SAFE_IPS = re.compile(
    r"(127\.0\.0\.1|0\.0\.0\.0|::1|255\.255\.255\.255)"
)

INFRA_RULES: list[Rule] = [
    Rule(
        id="INF-001",
        name="Private IPv4 Address (RFC 1918)",
        severity=Severity.MEDIUM,
        pattern=re.compile(
            r"\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|192\.168\.\d{1,3}\.\d{1,3}"
            r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
        ),
        description=(
            "A private (RFC 1918) IP address was detected. This may reveal internal network topology."
        ),
        recommendation=(
            "Replace with a config variable, placeholder (e.g. 192.168.x.x), or load from environment. "
            "Verify this is not a real internal server address."
        ),
        allowlist=[_SAFE_IPS],
    ),
    Rule(
        id="INF-002",
        name="Internal Hostname",
        severity=Severity.MEDIUM,
        pattern=re.compile(
            r"\b[\w\-]+(\.internal|\.local|\.lan|\.intranet|\.corp|\.priv)\b",
            re.IGNORECASE,
        ),
        description="A hostname with an internal TLD (.internal, .local, .lan, etc.) was detected.",
        recommendation=(
            "Replace with an environment variable or config-driven hostname. "
            "Internal service names should not appear in public code."
        ),
    ),
    Rule(
        id="INF-003",
        name="Windows User Home Path",
        severity=Severity.LOW,
        pattern=re.compile(
            r"[Cc]:[/\\][Uu]sers[/\\][A-Za-z0-9_\-\.]+[/\\]",
        ),
        description="A Windows user home directory path was detected, which may reveal a username.",
        recommendation=(
            "Replace with a relative path, environment variable (e.g. %USERPROFILE%), "
            "or a generic placeholder."
        ),
    ),
    Rule(
        id="INF-004",
        name="Unix Home Directory Path",
        severity=Severity.LOW,
        pattern=re.compile(r"/home/[A-Za-z0-9_\-\.]+/"),
        description="A Unix home directory path was detected, which may reveal a system username.",
        recommendation=(
            "Replace with a relative path or environment variable (e.g. $HOME). "
            "Hard-coded home paths break portability and reveal system usernames."
        ),
    ),
    Rule(
        id="INF-005",
        name="Docker Default Bridge IP",
        severity=Severity.LOW,
        pattern=re.compile(r"\b172\.(1[7-9]|2\d|30|31)\.\d{1,3}\.\d{1,3}\b"),
        description="An IP in the Docker default bridge network range was detected.",
        recommendation=(
            "Use Docker service names (e.g. 'db', 'redis') for inter-container communication "
            "instead of hardcoded IPs."
        ),
    ),
]
