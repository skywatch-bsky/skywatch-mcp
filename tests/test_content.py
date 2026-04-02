import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from skywatch_mcp.lib.clickhouse_client import QueryResult
from skywatch_mcp.tools.content import (
    _escape_clickhouse_sql,
    _build_similarity_query,
    content_similarity,
)


class TestEscapeClickHouseSQL:
    """Test SQL escaping utility"""

    def test_should_escape_single_quotes(self):
        """Single quotes should be escaped with backslash"""
        result = _escape_clickhouse_sql("it's a test")
        assert result == "it\\'s a test"

    def test_should_escape_backslashes(self):
        """Backslashes should be doubled"""
        result = _escape_clickhouse_sql("back\\slash")
        assert result == "back\\\\slash"

    def test_should_escape_both(self):
        """Both quotes and backslashes should be escaped"""
        result = _escape_clickhouse_sql("it's a \\test")
        assert result == "it\\'s a \\\\test"

    def test_should_handle_empty_string(self):
        """Empty string should remain empty"""
        result = _escape_clickhouse_sql("")
        assert result == ""

    def test_should_not_escape_other_characters(self):
        """Other characters should pass through unchanged"""
        result = _escape_clickhouse_sql("hello world 123")
        assert result == "hello world 123"


class TestBuildSimilarityQuery:
    """Test SQL query builder"""

    def test_should_build_valid_ngram_distance_query(self):
        """Query should contain ngramDistance, threshold, limit"""
        query = _build_similarity_query("hello", 0.4, 20)

        assert "ngramDistance(content, 'hello')" in query
        assert "< 0.4" in query
        assert "LIMIT 20" in query
        assert "FROM default.osprey_execution_results" in query
        assert "ORDER BY score ASC" in query

    def test_should_use_custom_threshold(self):
        """Threshold should appear in WHERE clause"""
        query = _build_similarity_query("test", 0.3, 10)
        assert "< 0.3" in query

    def test_should_use_custom_limit(self):
        """Limit should appear in query"""
        query = _build_similarity_query("test", 0.4, 100)
        assert "LIMIT 100" in query

    def test_should_select_required_columns(self):
        """Query should select did, handle, content, score, created_at"""
        query = _build_similarity_query("test", 0.4, 20)

        assert "did as user" in query
        assert "handle" in query
        assert "content as text" in query
        assert "ngramDistance(content, 'test') as score" in query
        assert "created_at" in query


class TestContentSimilarityTool:
    """Test content_similarity MCP tool"""

    @pytest.mark.asyncio
    async def test_should_return_json_with_proper_structure(self):
        """Tool should return JSON with user/handle/text/score/created_at fields"""
        with patch("skywatch_mcp.tools.content.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            # Mock query result
            mock_result = QueryResult(
                columns=[
                    {"name": "user", "type": "String"},
                    {"name": "handle", "type": "String"},
                    {"name": "text", "type": "String"},
                    {"name": "score", "type": "Float32"},
                    {"name": "created_at", "type": "DateTime"},
                ],
                rows=[
                    {
                        "user": "did:plc:123abc",
                        "handle": "user1.bsky.social",
                        "text": "similar content here",
                        "score": 0.2,
                        "created_at": "2026-04-01T00:00:00Z",
                    }
                ],
            )
            mock_client.query_trusted.return_value = mock_result

            result = await content_similarity("hello world")

            import json

            parsed = json.loads(result)
            assert isinstance(parsed, list)
            assert len(parsed) == 1
            assert parsed[0]["user"] == "did:plc:123abc"
            assert parsed[0]["handle"] == "user1.bsky.social"
            assert parsed[0]["text"] == "similar content here"
            assert parsed[0]["score"] == 0.2
            assert parsed[0]["created_at"] == "2026-04-01T00:00:00Z"

    @pytest.mark.asyncio
    async def test_should_use_query_trusted(self):
        """Tool should use async query_trusted method"""
        with patch("skywatch_mcp.tools.content.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            await content_similarity("test text")

            mock_client.query_trusted.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_escape_quotes_in_query(self):
        """Tool should escape single quotes in user input"""
        with patch("skywatch_mcp.tools.content.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            await content_similarity("it's a test")

            # Verify the query passed contains escaped quote
            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "it\\'s a test" in query

    @pytest.mark.asyncio
    async def test_should_escape_backslashes_in_query(self):
        """Tool should escape backslashes in user input"""
        with patch("skywatch_mcp.tools.content.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            await content_similarity("back\\slash")

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "back\\\\slash" in query

    @pytest.mark.asyncio
    async def test_should_pass_default_threshold(self):
        """Default threshold should be 0.4"""
        with patch("skywatch_mcp.tools.content.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            await content_similarity("test")

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "< 0.4" in query

    @pytest.mark.asyncio
    async def test_should_use_custom_threshold(self):
        """Custom threshold should be passed to query"""
        with patch("skywatch_mcp.tools.content.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            await content_similarity("test", threshold=0.25)

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "< 0.25" in query

    @pytest.mark.asyncio
    async def test_should_pass_default_limit(self):
        """Default limit should be 20"""
        with patch("skywatch_mcp.tools.content.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            await content_similarity("test")

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "LIMIT 20" in query

    @pytest.mark.asyncio
    async def test_should_use_custom_limit(self):
        """Custom limit should be passed to query"""
        with patch("skywatch_mcp.tools.content.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            await content_similarity("test", limit=50)

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "LIMIT 50" in query

    @pytest.mark.asyncio
    async def test_should_handle_empty_results(self):
        """Should return empty JSON array when no results"""
        with patch("skywatch_mcp.tools.content.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            result = await content_similarity("nonexistent")

            import json

            parsed = json.loads(result)
            assert parsed == []

    @pytest.mark.asyncio
    async def test_should_handle_query_exception(self):
        """Should raise ValueError on query exception"""
        with patch("skywatch_mcp.tools.content.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query_trusted.side_effect = Exception("Query failed")

            with pytest.raises(ValueError, match="Query failed"):
                await content_similarity("test")

    @pytest.mark.asyncio
    async def test_should_convert_values_to_strings_safely(self):
        """Should safely convert all row values to strings"""
        with patch("skywatch_mcp.tools.content.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            # Mock row with various types
            mock_result = QueryResult(
                columns=[],
                rows=[
                    {
                        "user": "did:plc:123",
                        "handle": "user.bsky.social",
                        "text": "test content",
                        "score": 0.15,
                        "created_at": "2026-04-01T00:00:00Z",
                    }
                ],
            )
            mock_client.query_trusted.return_value = mock_result

            result = await content_similarity("test")

            import json

            parsed = json.loads(result)
            # All values should be JSON-serializable
            assert isinstance(parsed[0]["score"], float)
            assert isinstance(parsed[0]["user"], str)
