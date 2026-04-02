import pytest
from datetime import datetime, timezone
from skywatch_mcp.lib.whois_parser import parse_whois_response


class TestWhoisParserBasic:
    def test_extract_registrar(self):
        text = """
Domain Name: EXAMPLE.COM
Registrar: GoDaddy.com, LLC
Creation Date: 1995-08-14T04:12:00Z
Registry Expiry Date: 2024-08-13T04:12:00Z
Name Server: NS1.EXAMPLE.COM
Name Server: NS2.EXAMPLE.COM
"""
        result = parse_whois_response(text)
        assert result.registrar is not None
        assert "GoDaddy" in result.registrar

    def test_extract_creation_and_expiration_dates(self):
        text = """
Creation Date: 1995-08-14T04:12:00Z
Registry Expiry Date: 2024-08-13T04:12:00Z
"""
        result = parse_whois_response(text)
        assert result.creation_date is not None
        assert result.expiration_date is not None
        assert "1995" in result.creation_date
        assert "2024" in result.expiration_date

    def test_extract_nameservers(self):
        text = """
Name Server: NS1.EXAMPLE.COM
Name Server: NS2.EXAMPLE.COM
Name Server: NS3.EXAMPLE.COM
"""
        result = parse_whois_response(text)
        assert len(result.nameservers) == 3
        assert "NS1.EXAMPLE.COM" in result.nameservers
        assert "NS2.EXAMPLE.COM" in result.nameservers
        assert "NS3.EXAMPLE.COM" in result.nameservers

    def test_calculate_domain_age_from_creation_date(self):
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        past_date = now - timedelta(days=100)
        past_date_str = past_date.isoformat().replace("+00:00", "Z")

        text = f"Creation Date: {past_date_str}"
        result = parse_whois_response(text)

        assert result.domain_age is not None
        assert 99 <= result.domain_age <= 101

    def test_return_none_for_missing_fields(self):
        text = "No WHOIS data found"
        result = parse_whois_response(text)

        assert result.registrar is None
        assert result.creation_date is None
        assert result.expiration_date is None
        assert len(result.nameservers) == 0
        assert result.domain_age is None

    def test_handle_alternative_creation_date_formats(self):
        text = """
Created: 1995-08-14
expires: 2024-08-13
"""
        result = parse_whois_response(text)
        assert result.creation_date is not None
        assert result.expiration_date is not None

    def test_preserve_raw_text_in_result(self):
        sample_text = "This is raw WHOIS data"
        result = parse_whois_response(sample_text)
        assert result.raw_text == sample_text

    def test_case_insensitive_field_extraction(self):
        text = """
registrar: Example Registrar
creation date: 2020-01-01T00:00:00Z
registry expiry date: 2025-01-01T00:00:00Z
name server: ns1.example.com
"""
        result = parse_whois_response(text)
        assert result.registrar is not None
        assert result.creation_date is not None
        assert result.expiration_date is not None
        assert len(result.nameservers) > 0

    def test_multiple_nameserver_lines(self):
        text = """
Name Server: ns1.example.com
Name Server: ns2.example.com
Name Server: ns3.example.com
Name Server: ns4.example.com
"""
        result = parse_whois_response(text)
        assert len(result.nameservers) == 4

    def test_domain_age_with_invalid_creation_date(self):
        text = "Creation Date: invalid-date"
        result = parse_whois_response(text)
        assert result.domain_age is None

    def test_empty_text(self):
        result = parse_whois_response("")
        assert result.registrar is None
        assert result.creation_date is None
        assert result.expiration_date is None
        assert len(result.nameservers) == 0
        assert result.domain_age is None
        assert result.raw_text == ""

    def test_whitespace_handling_in_fields(self):
        text = """
Registrar:   Extra   Spaces   Inc.
Name Server:    ns1.example.com
"""
        result = parse_whois_response(text)
        assert result.registrar == "Extra   Spaces   Inc."
        assert "ns1.example.com" in result.nameservers[0]

    def test_expiration_date_alternatives(self):
        # Test "Expiration Date:" variant
        text1 = "Expiration Date: 2025-01-01T00:00:00Z"
        result1 = parse_whois_response(text1)
        assert result1.expiration_date is not None

        # Test "Registry Expiry Date:" variant
        text2 = "Registry Expiry Date: 2025-01-01T00:00:00Z"
        result2 = parse_whois_response(text2)
        assert result2.expiration_date is not None

        # Test "expires:" variant
        text3 = "expires: 2025-01-01T00:00:00Z"
        result3 = parse_whois_response(text3)
        assert result3.expiration_date is not None

    def test_iso_date_parsing(self):
        text = "Creation Date: 2020-01-01T00:00:00Z"
        result = parse_whois_response(text)
        assert result.creation_date == "2020-01-01T00:00:00Z"
        assert result.domain_age is not None
        assert result.domain_age > 0

    def test_complex_whois_record(self):
        text = """
Domain Name: GITHUB.COM
Registrar: GitHub, Inc.
Creation Date: 2008-02-14T00:00:00Z
Registry Expiry Date: 2025-02-14T00:00:00Z
Name Server: ns-1707.awsdns-21.co.uk
Name Server: ns-421.awsdns-52.com
Name Server: ns-1060.awsdns-04.org
Name Server: ns-520.awsdns-00.net
Admin Contact: Admin Name
Tech Contact: Tech Name
"""
        result = parse_whois_response(text)
        assert result.registrar == "GitHub, Inc."
        assert "2008" in result.creation_date
        assert len(result.nameservers) == 4
        assert result.domain_age is not None
        assert result.domain_age > 0

    def test_nameserver_with_trailing_slash(self):
        text = "Name Server: ns1.example.com."
        result = parse_whois_response(text)
        assert len(result.nameservers) == 1
        assert result.nameservers[0] == "ns1.example.com."
