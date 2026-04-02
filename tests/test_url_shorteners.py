from skywatch_mcp.lib.url_shorteners import is_known_shortener


class TestKnownShorteners:
    """Test URL shortener domain recognition"""

    def test_all_known_shorteners_return_true(self):
        shorteners = [
            "bit.ly",
            "bitly.com",
            "t.co",
            "goo.gl",
            "tinyurl.com",
            "ow.ly",
            "is.gd",
            "v.gd",
            "buff.ly",
            "amzn.to",
            "youtu.be",
            "rb.gy",
            "shorturl.at",
            "tiny.cc",
            "cutt.ly",
        ]
        for shortener in shorteners:
            assert is_known_shortener(shortener) is True, f"{shortener} should be recognized"

    def test_case_insensitive_matching(self):
        assert is_known_shortener("BIT.LY") is True
        assert is_known_shortener("Bit.Ly") is True
        assert is_known_shortener("T.CO") is True
        assert is_known_shortener("gOo.Gl") is True

    def test_unknown_domains_return_false(self):
        assert is_known_shortener("example.com") is False
        assert is_known_shortener("google.com") is False
        assert is_known_shortener("github.com") is False
        assert is_known_shortener("test.com") is False

    def test_empty_string_returns_false(self):
        assert is_known_shortener("") is False

    def test_partial_match_returns_false(self):
        assert is_known_shortener("bit") is False
        assert is_known_shortener("bitly") is False
        assert is_known_shortener("bit.l") is False
