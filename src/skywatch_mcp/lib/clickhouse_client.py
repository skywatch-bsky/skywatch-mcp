# pattern: Imperative Shell

import asyncio
from dataclasses import dataclass
from typing import Any

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient

from skywatch_mcp.config import ClickHouseSettings
from skywatch_mcp.lib.sql_validation import ValidationFailure, validate_query


@dataclass(frozen=True)
class QueryResult:
    columns: list[dict[str, str]]
    rows: list[dict[str, Any]]


QUERY_DEADLINE_GRACE_SECONDS = 10

SCHEMA_TABLES = [
    "default.osprey_execution_results",
    "default.pds_signup_anomalies",
    "default.url_overdispersion_results",
    "default.account_entropy_results",
    "default.url_cosharing_pairs",
    "default.url_cosharing_clusters",
    "default.url_cosharing_membership",
    "default.url_cosharing_runs",
    "default.quote_cosharing_pairs",
    "default.quote_cosharing_clusters",
    "default.quote_cosharing_membership",
    "default.quote_overdispersion_results",
]


class ClickHouseClient:
    def __init__(self, settings: ClickHouseSettings) -> None:
        self._settings = settings
        self._client: AsyncClient | None = None

    async def _get_client(self) -> AsyncClient:
        if self._client is None:
            self._client = await clickhouse_connect.get_async_client(
                host=self._settings.effective_host.replace("http://", "").replace("https://", ""),
                port=self._settings.port,
                username=self._settings.user,
                password=self._settings.password,
                database=self._settings.database,
            )
        return self._client

    async def _execute_query(
        self, sql: str, max_execution_time: int
    ) -> QueryResult:
        deadline = max_execution_time + QUERY_DEADLINE_GRACE_SECONDS
        try:
            async with asyncio.timeout(deadline):
                client = await self._get_client()
                result = await client.query(
                    query=sql,
                    settings={"max_execution_time": max_execution_time},
                )
        except TimeoutError as exc:
            self._client = None
            raise TimeoutError(
                f"ClickHouse query timed out after {deadline} seconds"
            ) from exc
        except Exception:
            self._client = None
            raise

        columns = [
            {"name": name, "type": col_type}
            for name, col_type in zip(result.column_names, result.column_types, strict=True)
        ]
        rows = [
            dict(zip(result.column_names, row, strict=True))
            for row in result.result_rows
        ]
        return QueryResult(columns=columns, rows=rows)

    async def query(self, sql: str) -> QueryResult:
        validation = validate_query(sql)
        if isinstance(validation, ValidationFailure):
            raise ValueError(f"Query validation failed: {validation.reason}")
        return await self._execute_query(validation.normalized, 60)

    async def query_trusted(self, sql: str) -> QueryResult:
        return await self._execute_query(sql, 120)

    async def get_schema(self) -> QueryResult:
        all_rows: list[dict[str, Any]] = []
        schema_columns: list[dict[str, str]] = []

        for table in SCHEMA_TABLES:
            try:
                result = await self._execute_query(f"DESCRIBE TABLE {table}", 60)
                tagged_rows = [{**row, "table": table} for row in result.rows]
                all_rows.extend(tagged_rows)
                if not schema_columns:
                    schema_columns = [*result.columns, {"name": "table", "type": "String"}]
            except Exception:
                pass

        return QueryResult(columns=schema_columns, rows=all_rows)


# Lazy singleton — shared across all tool modules
_client: ClickHouseClient | None = None


def get_client() -> ClickHouseClient:
    global _client
    if _client is None:
        _client = ClickHouseClient(ClickHouseSettings())
    return _client
