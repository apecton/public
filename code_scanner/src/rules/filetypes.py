# Description:
# Detection rules that trigger on filename alone, without scanning content.
# Used to catch dangerous file types before they reach a public repository.

import re

from src.models import Severity
from src.rules.base_rule import Rule

FILETYPE_RULES: list[Rule] = [
    Rule(
        id="FT-001",
        name="Environment File (.env)",
        severity=Severity.CRITICAL,
        pattern=re.compile(r"(^|[/\\])\.env(\.[a-zA-Z0-9_\-]+)?$"),
        description=(
            ".env files commonly contain secrets, API keys, and database credentials. "
            "They must never be published."
        ),
        recommendation=(
            "Add .env to .gitignore. Use .env.example (with placeholder values only) "
            "to document required variables."
        ),
        filename_only=True,
    ),
    Rule(
        id="FT-002",
        name="PEM / Private Key File",
        severity=Severity.CRITICAL,
        pattern=re.compile(
            r"(?i)\.(pem|key|pk8|p8)$"
        ),
        description="A file with a private key extension was detected.",
        recommendation=(
            "Remove from the repository immediately. Store private keys in a secrets manager "
            "or hardware security module (HSM). Rotate if already exposed."
        ),
        filename_only=True,
    ),
    Rule(
        id="FT-003",
        name="SSH Private Key File",
        severity=Severity.CRITICAL,
        pattern=re.compile(
            r"(^|[/\\])(id_rsa|id_dsa|id_ecdsa|id_ed25519|id_rsa\.old)$"
        ),
        description="An SSH private key file was detected.",
        recommendation=(
            "Remove from the repository. SSH private keys grant server access - rotate them "
            "and remove the old key from authorized_keys on all servers."
        ),
        filename_only=True,
    ),
    Rule(
        id="FT-004",
        name="Credentials or Secrets File",
        severity=Severity.CRITICAL,
        pattern=re.compile(
            r"(?i)(^|[/\\])(credentials|secrets|secret|service[_\-]?account"
            r"|keyfile|auth[_\-]?keys|api[_\-]?keys?)\.(json|yaml|yml|toml|ini|cfg|conf)$"
        ),
        description="A file with a name suggestive of credentials or secrets was detected.",
        recommendation=(
            "Move secrets to a secrets manager or environment variables. "
            "Commit only .example files with placeholder values."
        ),
        filename_only=True,
    ),
    Rule(
        id="FT-005",
        name="Database File",
        severity=Severity.HIGH,
        pattern=re.compile(r"(?i)\.(sqlite3?|db|mdb|accdb)$"),
        description="A database file was detected. It may contain sensitive user data.",
        recommendation=(
            "Add database files to .gitignore. Use migrations and seed scripts instead "
            "of committing populated databases."
        ),
        filename_only=True,
    ),
    Rule(
        id="FT-006",
        name="PKCS / Certificate Store File",
        severity=Severity.HIGH,
        pattern=re.compile(r"(?i)\.(p12|pfx|jks|keystore)$"),
        description=(
            "A PKCS or Java KeyStore file was detected. These typically contain private keys "
            "and/or certificate chains."
        ),
        recommendation=(
            "Remove from the repository. Use a secrets manager. Rotate certificates if exposed."
        ),
        filename_only=True,
    ),
]
