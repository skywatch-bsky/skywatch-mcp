# pattern: Functional Core

import math
import re
from datetime import date


def sanitize_did(did: str) -> str:
    """Strip characters not valid in a DID (letters, digits, colon, dot, hyphen).

    Preserves uppercase characters, which are valid in ``did:key`` multibase
    encodings (e.g. ``did:key:z6Mk…``).
    """
    return re.sub(r"[^a-zA-Z0-9:.-]", "", did)


def sanitize_cluster_id(cluster_id: str) -> str:
    """Strip characters not valid in a cluster_id (lowercase alnum, hyphen)."""
    return re.sub(r"[^a-z0-9-]", "", cluster_id)


def sanitize_date(date_str: str) -> str:
    """Validate and return date in YYYY-MM-DD format.

    Performs both shape validation (regex) and calendar validation
    (``date.fromisoformat``), rejecting impossible dates like ``2026-99-99``.

    Raises ValueError if the date is malformed or not a real calendar date.
    """
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        raise ValueError(f"Invalid date format. Expected YYYY-MM-DD, got: {date_str}")
    try:
        date.fromisoformat(date_str)
    except ValueError:
        raise ValueError(f"Invalid calendar date: {date_str}") from None
    return date_str


def sanitize_hostname(hostname: str) -> str:
    """Normalize and validate a hostname (lowercase alnum, dot, hyphen).

    Lowercases before stripping so that valid mixed-case hostnames are
    preserved as their canonical lowercase form rather than corrupted.
    """
    return re.sub(r"[^a-z0-9.-]", "", hostname.lower())


def sanitize_at_uri(uri: str) -> str:
    """Strip characters not valid in an AT-URI (letters, digits, colon, dot, slash, underscore, hyphen).

    Preserves uppercase characters, which can appear in rkeys and
    ``did:key`` identifiers embedded in the authority component.
    """
    return re.sub(r"[^a-zA-Z0-9:./_-]", "", uri)


def validate_limit(limit: int, maximum: int = 10000) -> int:
    """Validate that ``limit`` is a positive integer within ``[1, maximum]``.

    Raises ValueError on out-of-range, non-finite, or non-integral values.
    """
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError(f"limit must be an integer, got {type(limit).__name__}: {limit}")
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    if limit > maximum:
        raise ValueError(f"limit must be <= {maximum}, got {limit}")
    return limit


def validate_days(days: int, maximum: int = 365) -> int:
    """Validate that ``days`` is a positive integer within ``[1, maximum]``.

    Raises ValueError on out-of-range or non-integral values.
    """
    if isinstance(days, bool) or not isinstance(days, int):
        raise ValueError(f"days must be an integer, got {type(days).__name__}: {days}")
    if days < 1:
        raise ValueError(f"days must be >= 1, got {days}")
    if days > maximum:
        raise ValueError(f"days must be <= {maximum}, got {days}")
    return days


def validate_q_value(q_value: float) -> float:
    """Validate that ``q_value`` is a finite float in ``[0.0, 1.0]``.

    Raises ValueError on NaN, infinity, or out-of-range values.
    """
    v = float(q_value)
    if not math.isfinite(v):
        raise ValueError(f"q_value must be finite, got {q_value}")
    if v < 0.0 or v > 1.0:
        raise ValueError(f"q_value must be in [0.0, 1.0], got {q_value}")
    return v
