# pattern: Imperative Shell

import json

from skywatch_mcp.lib.clickhouse_client import get_client
from skywatch_mcp.server import mcp


def _escape_clickhouse_sql(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'")


def _build_similarity_query(escaped_text: str, threshold: float, limit: int) -> str:
    return f"""SELECT
    Handle as user,
    Handle as handle,
    PostTextCleaned as text,
    ngramDistance(PostTextCleaned, '{escaped_text}') as score,
    __timestamp as created_at
  FROM default.osprey_execution_results
  WHERE PostTextCleaned IS NOT NULL
    AND length(PostTextCleaned) > 0
    AND ngramDistance(PostTextCleaned, '{escaped_text}') < {threshold}
  ORDER BY score ASC
  LIMIT {limit}"""


@mcp.tool()
async def content_similarity(
    text: str,
    threshold: float = 0.4,
    limit: int = 20,
) -> str:
    """Find posts with similar text content using ClickHouse ngramDistance. Useful for detecting copypasta and coordinated posting.

    Args:
        text: Text to search for similar content
        threshold: Distance threshold (0=identical, 1=completely different). Lower values find more similar content. Default 0.4
        limit: Maximum number of results. Default 20
    """
    try:
        escaped_text = _escape_clickhouse_sql(text)
        query = _build_similarity_query(escaped_text, threshold, limit)
        result = await get_client().query_trusted(query)

        results = [
            {
                "user": str(row.get("user", "")),
                "handle": str(row.get("handle", "")),
                "text": str(row.get("text", "")),
                "score": float(row.get("score", 0)),
                "created_at": str(row.get("created_at", "")),
            }
            for row in result.rows
        ]

        return json.dumps(results, indent=2, default=str)
    except Exception as e:
        raise ValueError(str(e)) from e
