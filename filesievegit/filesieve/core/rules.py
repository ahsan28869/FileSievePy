"""Pydantic models for file routing rules with regex safety checks."""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


MAX_REGEX_LENGTH = 200
MAX_NAME_CONTAINS = 20


def _validate_regex_safety(pattern: str) -> str:
    """Reject patterns that are too long or obviously ReDoS-prone."""
    if len(pattern) > MAX_REGEX_LENGTH:
        raise ValueError(f"Regex too long (max {MAX_REGEX_LENGTH} chars)")

    # Reject nested quantifiers like (a+)+ or (a*)* — the classic ReDoS shape
    if re.search(r"\([^)]*[+*][^)]*\)[+*{]", pattern):
        raise ValueError("Regex contains nested quantifiers (potential ReDoS)")

    # Also reject backreferences — often catastrophic
    if re.search(r"\\[1-9]", pattern):
        raise ValueError("Regex backreferences are not supported")

    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regex: {exc}") from exc

    return pattern


class Rule(BaseModel):
    """A single file routing rule."""

    name: str = Field(..., min_length=1, max_length=100, description="Human readable rule name")
    enabled: bool = Field(default=True)
    priority: int = Field(default=0, ge=0, le=10000, description="Higher priority wins")

    # Matching criteria
    mime_types: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="MIME types or wildcards, e.g. 'image/*'",
    )
    extensions: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="File extensions, e.g. '.pdf'",
    )
    name_contains: list[str] = Field(
        default_factory=list,
        max_length=MAX_NAME_CONTAINS,
        description="Substrings the filename must contain",
    )
    name_regex: Optional[str] = Field(
        default=None,
        description="Regex pattern the filename must match",
    )
    min_size_bytes: Optional[int] = Field(default=None, ge=0)
    max_size_bytes: Optional[int] = Field(default=None, ge=0)

    # Destination
    destination: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Relative destination path, supports {year}/{month}",
    )
    rename_pattern: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Optional rename pattern using {name}, {ext}, {date}",
    )
    organize_by_date: bool = Field(default=True)

    @field_validator("extensions")
    @classmethod
    def _normalize_extensions(cls, v: list[str]) -> list[str]:
        out = []
        for e in v:
            e = e.strip().lower()
            if not e:
                continue
            if not e.startswith("."):
                e = "." + e
            if len(e) > 16 or any(c in e for c in "/\\ "):
                raise ValueError(f"Invalid extension: {e!r}")
            out.append(e)
        return out

    @field_validator("name_regex")
    @classmethod
    def _check_regex(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return _validate_regex_safety(v)

    @field_validator("name_contains")
    @classmethod
    def _check_contains(cls, v: list[str]) -> list[str]:
        return [s[:200] for s in v if s]

    @field_validator("destination")
    @classmethod
    def _check_destination(cls, v: str) -> str:
        if "\x00" in v:
            raise ValueError("Destination contains NUL byte")
        return v


class RuleSet(BaseModel):
    """A collection of rules."""

    schema_version: int = Field(default=1)
    rules: list[Rule] = Field(default_factory=list, max_length=200)

    def sorted_rules(self) -> list[Rule]:
        """Return enabled rules sorted deterministically by priority, specificity, and name."""
        def specificity(rule: Rule) -> int:
            score = 0
            if rule.name_regex:
                score += 100
            if rule.name_contains:
                score += 50
            if rule.extensions:
                score += 20
            if rule.mime_types:
                score += 10
            return score

        return sorted(
            (r for r in self.rules if r.enabled),
            key=lambda r: (-r.priority, -specificity(r), r.name.lower()),
        )


def default_rules() -> RuleSet:
    """Return a sensible default rule set."""
    return RuleSet(
        schema_version=1,
        rules=[
            Rule(
                name="Invoices",
                priority=100,
                mime_types=["application/pdf"],
                name_contains=["invoice", "receipt", "bill"],
                destination="Finance/Invoices/{year}/{month}",
            ),
            Rule(
                name="Images",
                priority=50,
                mime_types=["image/*"],
                destination="Media/Images/{year}/{month}",
            ),
            Rule(
                name="Videos",
                priority=50,
                mime_types=["video/*"],
                destination="Media/Videos/{year}/{month}",
            ),
            Rule(
                name="Audio",
                priority=50,
                mime_types=["audio/*"],
                destination="Media/Audio/{year}/{month}",
            ),
            Rule(
                name="Archives",
                priority=40,
                extensions=[".zip", ".rar", ".7z", ".tar", ".gz"],
                destination="Archives/{year}/{month}",
            ),
            Rule(
                name="Installers",
                priority=40,
                extensions=[".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm"],
                destination="Installers/{year}/{month}",
            ),
            Rule(
                name="Documents",
                priority=30,
                mime_types=[
                    "application/pdf",
                    "application/msword",
                    "application/vnd.openxmlformats-officedocument.*",
                    "text/plain",
                ],
                destination="Documents/{year}/{month}",
            ),
            Rule(
                name="Spreadsheets",
                priority=30,
                extensions=[".xls", ".xlsx", ".csv", ".ods"],
                destination="Documents/Spreadsheets/{year}/{month}",
            ),
            Rule(
                name="Code",
                priority=30,
                extensions=[
                    ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h",
                    ".cs", ".go", ".rs", ".rb", ".php", ".html", ".css",
                    ".json", ".xml", ".yaml", ".yml", ".toml",
                ],
                destination="Code/{year}/{month}",
            ),
        ],
    )