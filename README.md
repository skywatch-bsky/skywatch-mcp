# skywatch-mcp

MCP server for investigating activity on the AT Protocol / Bluesky network. Exposes 20 tools across five domains: ClickHouse queries, network investigation, content similarity, co-sharing analysis, and Ozone moderation.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Install

```bash
uv sync
```

## Run

```bash
uv run skywatch-mcp
```

The server communicates over stdio using the MCP JSON-RPC protocol. Connect it to any MCP-compatible client (Claude Desktop, claude-code, mcp-inspector, etc.).

### Claude Desktop / Claude Code

Add to your MCP server config:

```json
{
  "mcpServers": {
    "skywatch-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/skywatch-mcp", "skywatch-mcp"]
    }
  }
}
```

## Environment Variables

### ClickHouse

| Variable | Default | Description |
|----------|---------|-------------|
| `CLICKHOUSE_HOST` | `http://localhost` | ClickHouse server host |
| `CLICKHOUSE_PORT` | `8123` | ClickHouse HTTP port |
| `CLICKHOUSE_USER` | `default` | ClickHouse username |
| `CLICKHOUSE_PASSWORD` | *(empty)* | ClickHouse password |
| `CLICKHOUSE_DATABASE` | `default` | ClickHouse database |
| `CLICKHOUSE_TAILNET_IP` | *(none)* | Overrides host when set (for Tailscale access) |

### Ozone

| Variable | Default | Description |
|----------|---------|-------------|
| `OZONE_HANDLE` | *(none)* | AT Protocol handle for Ozone auth |
| `OZONE_ADMIN_PASSWORD` | *(none)* | Admin password for Ozone auth |
| `OZONE_DID` | *(none)* | DID of the Ozone labeller service |
| `OZONE_PDS` | *(none)* | PDS hostname for Ozone XRPC calls |

All four Ozone variables must be set for Ozone tools to function.

## Tools

### ClickHouse (2)
- `clickhouse_query` — Execute read-only SQL queries (SELECT/WITH, requires LIMIT)
- `clickhouse_schema` — Get column definitions for all queryable tables

### Network (4)
- `domain_check` — DNS records (A, AAAA, NS, MX, TXT, CNAME, SOA) and HTTP status
- `ip_lookup` — Geographic location and network info via ip-api.com
- `url_expand` — Follow redirect chains, detect URL shorteners
- `whois_lookup` — WHOIS registration data with parsed fields

### Content (1)
- `content_similarity` — Find similar posts using ClickHouse ngramDistance

### Co-Sharing (3)
- `cosharing_clusters` — URL co-sharing cluster analysis
- `cosharing_pairs` — Raw co-sharing pairs with edge weights
- `cosharing_evolution` — Cluster evolution timeline

### Ozone Moderation (10)
- `ozone_label` — Apply/remove moderation labels
- `ozone_comment` — Add comments to moderation records
- `ozone_acknowledge` — Acknowledge subjects
- `ozone_escalate` — Escalate for review
- `ozone_tag` — Add/remove tags
- `ozone_mute` / `ozone_unmute` — Mute/unmute subjects
- `ozone_resolve_appeal` — Resolve appeals
- `ozone_query_statuses` — Query moderation queue
- `ozone_query_events` — Query moderation events

## Development

```bash
# Run tests
uv run pytest

# Lint
uv run ruff check src/ tests/

# Type check
uv run mypy src/

# Format
uv run ruff format src/ tests/
```
