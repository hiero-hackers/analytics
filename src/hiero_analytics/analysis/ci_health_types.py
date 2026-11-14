"""Common types for CI health checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CheckStatus = Literal["pass", "fail", "na", "review"]


@dataclass(frozen=True)
class CheckResult:
    """Result of a CI health check for a repository.

    ``subject`` names what a row is about when one check emits several rows
    for the same repository (for example one per Dependabot ecosystem).
    """

    check: str
    band: str
    status: CheckStatus
    evidence: str
    location: str
    subject: str = ""
