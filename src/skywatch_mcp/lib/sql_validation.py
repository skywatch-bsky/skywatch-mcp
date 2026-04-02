# pattern: Functional Core

import re
from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True)
class ValidationSuccess:
    normalized: str


@dataclass(frozen=True)
class ValidationFailure:
    reason: str


ValidationResult: TypeAlias = ValidationSuccess | ValidationFailure


def validate_query(sql: str) -> ValidationResult:
    trimmed = sql.strip()

    if len(trimmed) == 0:
        return ValidationFailure(reason="Query cannot be empty")

    normalized = re.sub(r"\s+", " ", trimmed)
    tokens = normalized.split()
    if not tokens:
        return ValidationFailure(reason="Query cannot be empty")

    first_token = tokens[0]
    upper_first = first_token.upper()

    if upper_first not in ("SELECT", "WITH"):
        return ValidationFailure(
            reason=f"Only SELECT queries are allowed. Query starts with '{first_token}'"
        )

    upper_normalized = normalized.upper()

    if not re.search(r"\bLIMIT\s+\d+\b", upper_normalized):
        return ValidationFailure(
            reason="Query must contain a LIMIT clause with a numeric value (e.g., LIMIT 10)"
        )

    if ";" in upper_normalized:
        return ValidationFailure(
            reason="Query cannot contain semicolons (multi-statement execution not allowed)"
        )

    if re.search(r"\bINTO\b", upper_normalized):
        return ValidationFailure(
            reason="Query cannot contain INTO keyword (data export not allowed)"
        )

    return ValidationSuccess(normalized=normalized)
