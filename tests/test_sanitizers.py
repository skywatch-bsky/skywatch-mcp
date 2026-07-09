# pattern: Imperative Shell

import pytest

from skywatch_mcp.lib.sanitizers import (
    sanitize_at_uri,
    sanitize_cluster_id,
    sanitize_date,
    sanitize_did,
    sanitize_hostname,
    validate_days,
    validate_limit,
    validate_q_value,
)


class TestSanitizeDid:
    def test_sanitize_did_should_preserve_valid_characters(self):
        result = sanitize_did("did:plc:abc123xyz")
        assert result == "did:plc:abc123xyz"

    def test_sanitize_did_should_strip_invalid_characters(self):
        result = sanitize_did("did:plc:ABC123!@# test")
        assert result == "did:plc:ABC123test"

    def test_sanitize_did_should_preserve_dots_and_colons(self):
        result = sanitize_did("did:key:z6mkhagvot5rgts")
        assert result == "did:key:z6mkhagvot5rgts"

    def test_sanitize_did_preserves_uppercase(self):
        """did:key multibase encodings contain uppercase characters."""
        result = sanitize_did("did:key:z6MktpcePjQ8vVvKbQqXQXQXQ")
        assert result == "did:key:z6MktpcePjQ8vVvKbQqXQXQXQ"


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

    def test_sanitize_date_should_reject_impossible_calendar_date(self):
        with pytest.raises(ValueError):
            sanitize_date("2026-13-45")


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


class TestValidateLimit:
    def test_valid_limit(self):
        assert validate_limit(50) == 50

    def test_limit_one(self):
        assert validate_limit(1) == 1

    def test_limit_zero_raises(self):
        with pytest.raises(ValueError):
            validate_limit(0)

    def test_negative_limit_raises(self):
        with pytest.raises(ValueError):
            validate_limit(-5)

    def test_limit_above_default_max_raises(self):
        with pytest.raises(ValueError):
            validate_limit(10001)

    def test_limit_with_custom_max(self):
        assert validate_limit(500, maximum=500) == 500


class TestValidateDays:
    def test_valid_days(self):
        assert validate_days(14) == 14

    def test_days_one(self):
        assert validate_days(1) == 1

    def test_days_zero_raises(self):
        with pytest.raises(ValueError):
            validate_days(0)

    def test_negative_days_raises(self):
        with pytest.raises(ValueError):
            validate_days(-1)

    def test_days_above_default_max_raises(self):
        with pytest.raises(ValueError):
            validate_days(366)


class TestValidateQValue:
    def test_valid_q_value(self):
        assert validate_q_value(0.05) == 0.05

    def test_q_value_zero(self):
        assert validate_q_value(0.0) == 0.0

    def test_q_value_one(self):
        assert validate_q_value(1.0) == 1.0

    def test_negative_q_value_raises(self):
        with pytest.raises(ValueError):
            validate_q_value(-0.01)

    def test_q_value_above_one_raises(self):
        with pytest.raises(ValueError):
            validate_q_value(1.01)

    def test_nan_q_value_raises(self):
        with pytest.raises(ValueError):
            validate_q_value(float("nan"))

    def test_inf_q_value_raises(self):
        with pytest.raises(ValueError):
            validate_q_value(float("inf"))
