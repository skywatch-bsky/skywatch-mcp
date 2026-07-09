# pattern: Imperative Shell

import pytest

from skywatch_mcp.lib.sanitizers import (
    sanitize_at_uri,
    sanitize_cluster_id,
    sanitize_date,
    sanitize_did,
    sanitize_hostname,
)


class TestSanitizeDid:
    def test_sanitize_did_should_preserve_valid_characters(self):
        result = sanitize_did("did:plc:abc123xyz")
        assert result == "did:plc:abc123xyz"

    def test_sanitize_did_should_strip_invalid_characters(self):
        result = sanitize_did("did:plc:ABC123!@# test")
        assert result == "did:plc:123test"

    def test_sanitize_did_should_preserve_dots_and_colons(self):
        result = sanitize_did("did:key:z6mkhagvot5rgts")
        assert result == "did:key:z6mkhagvot5rgts"


class TestSanitizeClusterId:
    def test_sanitize_cluster_id_should_preserve_valid_characters(self):
        result = sanitize_cluster_id("2024-01-15-0042")
        assert result == "2024-01-15-0042"

    def test_sanitize_cluster_id_should_strip_invalid_characters(self):
        result = sanitize_cluster_id("2024-01-15-0042 #HACK!")
        assert result == "2024-01-15-0042"


class TestSanitizeDate:
    def test_sanitize_date_should_accept_valid_format(self):
        result = sanitize_date("2024-01-15")
        assert result == "2024-01-15"

    def test_sanitize_date_should_reject_sql_injection_attempt(self):
        with pytest.raises(ValueError):
            sanitize_date("2024-01-15'; DROP TABLE")

    def test_sanitize_date_should_reject_invalid_format(self):
        with pytest.raises(ValueError):
            sanitize_date("not-a-date")

    def test_sanitize_date_should_reject_empty_string(self):
        with pytest.raises(ValueError):
            sanitize_date("")


class TestSanitizeHostname:
    def test_sanitize_hostname_should_preserve_valid_characters(self):
        result = sanitize_hostname("pds.example.com")
        assert result == "pds.example.com"

    def test_sanitize_hostname_should_strip_invalid_characters(self):
        result = sanitize_hostname("pds.example.com'; drop table--")
        assert result == "pds.example.comdroptable--"

    def test_sanitize_hostname_should_preserve_hyphens(self):
        result = sanitize_hostname("my-pds-host.example.org")
        assert result == "my-pds-host.example.org"


class TestSanitizeAtUri:
    def test_sanitize_at_uri_should_preserve_valid_characters(self):
        result = sanitize_at_uri("at://did:plc:abc123/app.bsky.feed.post/xyz")
        assert result == "at://did:plc:abc123/app.bsky.feed.post/xyz"

    def test_sanitize_at_uri_should_strip_invalid_characters(self):
        result = sanitize_at_uri("at://did:plc:abc123/app.bsky.feed.post/xyz'; drop")
        assert result == "at://did:plc:abc123/app.bsky.feed.post/xyzdrop"
