# Description:
# Aggregates all rule modules into a single list for the scanner.

from src.rules.base_rule import Rule
from src.rules.filetypes import FILETYPE_RULES
from src.rules.infra import INFRA_RULES
from src.rules.pii import PII_RULES
from src.rules.secrets import SECRETS_RULES

ALL_RULES: list[Rule] = SECRETS_RULES + PII_RULES + INFRA_RULES + FILETYPE_RULES

__all__ = ["ALL_RULES", "Rule"]
