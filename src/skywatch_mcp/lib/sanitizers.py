# pattern: Functional Core

import re


def sanitize_did(did: str) -> str:
    """Strip characters not valid in a DID (lowercase alnum, colon, dot)."""
    return re.sub(r"[^a-z0-9:.]", "", did)


def sanitize_cluster_id(cluster_id: str) -> str:
    """Strip characters not valid in a cluster_id (lowercase alnum, hyphen)."""
    return re.sub(r"[^a-z0-9-]", "", cluster_id)


def sanitize_date(date: str) -> str:
    """Validate and return date in YYYY-MM-DD format.

    Raises ValueError if the date does not match the expected format.
    """
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise ValueError(f"Invalid date format. Expected YYYY-MM-DD, got: {date}")
    return date


def sanitize_hostname(hostname: str) -> str:
    """Strip characters not valid in a hostname (lowercase alnum, dot, hyphen)."""
    return re.sub(r"[^a-z0-9.-]", "", hostname)


def sanitize_at_uri(uri: str) -> str:
    """Strip characters not valid in an AT-URI (lowercase alnum, colon, dot, slash)."""
    return re.sub(r"[^a-z0-9:./]", "", uri)
