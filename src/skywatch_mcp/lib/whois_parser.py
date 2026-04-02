# pattern: Functional Core

import re
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class WhoisResult:
    registrar: str | None
    creation_date: str | None
    expiration_date: str | None
    nameservers: list[str]
    domain_age: int | None
    raw_text: str


def _extract_field(text: str, patterns: list[re.Pattern[str]]) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match and match.group(1):
            return match.group(1).strip()
    return None


def _extract_nameservers(text: str) -> list[str]:
    pattern = re.compile(r"Name\s+Server:\s*(.+)", re.IGNORECASE)
    return [m.group(1).strip() for m in pattern.finditer(text) if m.group(1)]


def _calculate_domain_age(creation_date_str: str | None) -> int | None:
    if not creation_date_str:
        return None
    try:
        creation_date = datetime.fromisoformat(creation_date_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_days = (now - creation_date).days
        return age_days
    except (ValueError, TypeError):
        return None


_REGISTRAR_PATTERNS = [re.compile(r"Registrar:\s*(.+)", re.IGNORECASE)]

_CREATION_PATTERNS = [
    re.compile(r"Creation\s+Date:\s*(.+)", re.IGNORECASE),
    re.compile(r"Created:\s*(.+)", re.IGNORECASE),
]

_EXPIRATION_PATTERNS = [
    re.compile(r"Registry\s+Expiry\s+Date:\s*(.+)", re.IGNORECASE),
    re.compile(r"Expiration\s+Date:\s*(.+)", re.IGNORECASE),
    re.compile(r"expires:\s*(.+)", re.IGNORECASE),
]


def parse_whois_response(raw_text: str) -> WhoisResult:
    registrar = _extract_field(raw_text, _REGISTRAR_PATTERNS)
    creation_date = _extract_field(raw_text, _CREATION_PATTERNS)
    expiration_date = _extract_field(raw_text, _EXPIRATION_PATTERNS)
    nameservers = _extract_nameservers(raw_text)
    domain_age = _calculate_domain_age(creation_date)

    return WhoisResult(
        registrar=registrar,
        creation_date=creation_date,
        expiration_date=expiration_date,
        nameservers=nameservers,
        domain_age=domain_age,
        raw_text=raw_text,
    )
