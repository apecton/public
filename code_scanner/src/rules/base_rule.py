# Description:
# Base Rule dataclass used by all scanner rule modules.

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from src.models import Severity


@dataclass
class Rule:
    """A single detection rule."""

    id: str
    name: str
    severity: Severity
    pattern: re.Pattern[str]
    description: str
    recommendation: str
    # When set, this rule matches against the filename, not file content.
    filename_only: bool = False
    # Optional allowlist: matches that also match these patterns are suppressed.
    allowlist: Optional[list[re.Pattern[str]]] = None
