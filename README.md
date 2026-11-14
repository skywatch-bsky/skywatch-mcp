# skywatch-mcp

skywatch-mcp is a FastMCP server for investigators and moderators who examine activity on the AT Protocol / Bluesky network. Its 32 tools cover ClickHouse analytics, network lookups, content similarity, co-sharing analysis, anomaly results, and Ozone moderation.

Draws heavily on [Phoebe by haileyok](https://github.com/haileyok/phoebe).

## Install and run

You need:

- Python 3.12 or later.
- [uv](https://docs.astral.sh/uv/), which installs Python dependencies and runs the server.
- An MCP client, such as Claude Desktop or Claude Code. MCP lets the client call the server's tools.
- A reachable ClickHouse server with the skywatch dataset for analytics tools.
- Ozone credentials only if you use Ozone moderation tools, including moderation queries.

Network lookup tools need internet access, but do not need ClickHouse or Ozone credentials.

### Install from source

1. Download or clone this repository.
2. Open a terminal in the repository folder, which contains `pyproject.toml`.
3. Install the dependencies:

   ```bash
   uv sync
   ```

4. Create a `.env` file in that folder with the settings for your services. See [Environment variables](#environment-variables).
5. Restrict access to `.env` to your user account because it can contain passwords.

### Connect an MCP client

The client starts the server with this command:

```bash
uv run skywatch-mcp
```

The server uses standard input and output (stdio) to exchange MCP messages. It is not a standalone interactive application or a web server.

For Claude Desktop or Claude Code:

1. Add this entry to the client's MCP server configuration:

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

2. Replace `/path/to/skywatch-mcp` with the full path to your repository folder.
3. Restart the client or reload its MCP configuration.
4. Open the client's tool list.

A successful connection lists 32 skywatch-mcp tools. Tool discovery confirms the connection, not access to ClickHouse or Ozone.

With ClickHouse configured, ask the client to call `clickhouse_schema`. A successful result contains column names and types from the dataset. You can also use MCP Inspector (`mcp-inspector`) to inspect the tool list.

To stop the server, disconnect it through the client's MCP controls. If you started the command in a terminal, press `Ctrl+C`.

## Developer setup

Use Python 3.12+ and uv. Ruff targets `py312`. Mypy uses `python_version = "3.12"` and strict mode, equivalent to `--strict`.

The package uses Hatchling as its build backend. The `dev` dependency group contains pytest, pytest-asyncio, pytest-mock, mypy, and Ruff.

1. Download or clone this repository if you do not already have it.
2. Open a terminal in the repository folder.
3. Install the runtime and development dependencies:

   ```bash
   uv sync
   ```

4. Create `.env` in the repository folder for local service settings.
5. Restrict the file permissions to your user account.

Both settings classes read `.env`. The repository's `.gitignore` excludes this file, but ignore rules do not restrict local access. Do not commit passwords or copy them into client configuration examples.

Analytics calls require an existing skywatch dataset in ClickHouse. Dependency installation does not create or populate that dataset.

Run these commands from the repository folder:

| Task | Command |
| --- | --- |
| Run tests | `uv run pytest` |
| Check lint rules | `uv run ruff check src/ tests/` |
| Check types in strict mode | `uv run mypy src/` |
| Format source and tests | `uv run ruff format src/ tests/` |
| Start the stdio server | `uv run skywatch-mcp` |

The run command waits for MCP messages. Use an MCP client to confirm that the server lists its tools.

## Environment variables

Set these values in `.env` in the repository folder, or supply them as environment variables to the server process.

### ClickHouse

| Variable | Default | Purpose |
| --- | --- | --- |
| `CLICKHOUSE_HOST` | `http://localhost` | ClickHouse server host. |
| `CLICKHOUSE_PORT` | `8123` | ClickHouse HTTP port. |
| `CLICKHOUSE_USER` | `default` | ClickHouse username. |
| `CLICKHOUSE_PASSWORD` | Empty | ClickHouse password. |
| `CLICKHOUSE_DATABASE` | `default` | ClickHouse database. |
| `CLICKHOUSE_TAILNET_IP` | Unset | Overrides the host with `http://<tailnet_ip>` when set. |

ClickHouse access is read-only. User-supplied SQL must start with `SELECT` or `WITH` and include a numeric `LIMIT`. The SQL validator rejects semicolons and `INTO`.

### Ozone

| Variable | Default | Purpose |
| --- | --- | --- |
| `OZONE_SERVICE_URL` | Unset | Accepted by settings, but unused by the current Ozone request code. |
| `OZONE_HANDLE` | Unset | Account handle for authentication. |
| `OZONE_ADMIN_PASSWORD` | Unset | Password for authentication. |
| `OZONE_DID` | Unset | Ozone labeler service DID, the AT Protocol decentralized identifier. |
| `OZONE_PDS` | Unset | Personal Data Server (PDS) hostname, without `https://` or a path. |

Ozone tools require `OZONE_HANDLE`, `OZONE_ADMIN_PASSWORD`, `OZONE_DID`, and `OZONE_PDS`. `OZONE_SERVICE_URL` is not required and does not override the destination.

Authentication and moderation requests use `https://<OZONE_PDS>/xrpc/...`. The requests identify the labeler through the `atproto-proxy` header.

Ozone write tools change moderation state. Review the subject and action before you approve a call.

## Tool inventory

The server registers 32 tools from 12 modules in `src/skywatch_mcp/tools/`. The descriptions below summarize the opening descriptions in their docstrings.

### ClickHouse (2)

| Tool | Description |
| --- | --- |
| `clickhouse_query` | Execute a read-only SQL query against the ClickHouse database. |
| `clickhouse_schema` | Get column definitions, including names and types, for the known analytics tables. |

### Network lookups (4)

| Tool | Description |
| --- | --- |
| `domain_check` | Check DNS records and HTTP status for a domain. |
| `ip_lookup` | Get geographic location and network information for an IP address from ip-api.com. |
| `url_expand` | Follow a URL's redirect chain and report each hop with its status code. |
| `whois_lookup` | Get WHOIS registration data for a domain. |

### Content similarity (1)

| Tool | Description |
| --- | --- |
| `content_similarity` | Find posts with similar text content using ClickHouse `ngramDistance`. |

### Co-sharing analysis (7)

Co-sharing means that multiple accounts share the same URLs or quote the same posts.

| Tool | Description |
| --- | --- |
| `cosharing_clusters` | Find URL co-sharing clusters through TF-IDF cosine similarity and density-based dismantling. |
| `cosharing_pairs` | Get account pairs that share the same URLs on the same day. |
| `cosharing_evolution` | Trace the evolution history of a URL co-sharing cluster over time. |
| `cosharing_runs` | Get daily URL co-sharing pipeline metadata, including filter counts, thresholds, and guardrail outcomes. |
| `quote_cosharing_clusters` | Find quote-post co-sharing clusters through a Newman-weighted graph and Leiden community detection. |
| `quote_cosharing_pairs` | Get account pairs that quote the same post URIs on the same day. |
| `quote_cosharing_evolution` | Trace the evolution history of a quote-post co-sharing cluster over time. |

### URL and quote-post overdispersion (4)

These tools return anomaly results and history for sharing volume and density.

| Tool | Description |
| --- | --- |
| `url_overdispersion_results` | Get anomalous URL/domain-sharing volume or density spikes from negative-binomial and beta-binomial tests with false-discovery-rate correction. |
| `url_overdispersion_trend` | Get a single domain's URL overdispersion history across volume and density signals. |
| `quote_overdispersion_results` | Get anomalous quote-post concentration on a single quoted URI from negative-binomial and beta-binomial tests with false-discovery-rate correction. |
| `quote_overdispersion_trend` | Get quote-post overdispersion history for a single quoted URI. |

### Account entropy (2)

These tools return statistical signals of regular, bot-like posting patterns. The signals do not establish whether an account is automated.

| Tool | Description |
| --- | --- |
| `account_entropy_results` | Get bot-like posting results based on corrected normalized entropy and the coefficient of variation between posts. |
| `account_entropy_trend` | Get account entropy and coefficient-of-variation signals over time for a single account. |

### Signup anomalies (2)

| Tool | Description |
| --- | --- |
| `signup_anomalies` | Get anomalous PDS signup spikes from negative-binomial/Poisson tests with Benjamini–Hochberg false-discovery-rate correction. |
| `signup_anomaly_trend` | Get signup anomaly history for one PDS host at daily and hourly intervals. |

### Ozone moderation (10)

| Tool | Description |
| --- | --- |
| `ozone_label` | Apply or remove a moderation label on a subject through Ozone. |
| `ozone_comment` | Add a comment to a subject's moderation record. |
| `ozone_acknowledge` | Move a subject from open to reviewed status. |
| `ozone_escalate` | Escalate a subject for higher-level review by the moderation team. |
| `ozone_tag` | Add or remove tags from a subject for categorization and filtering. |
| `ozone_mute` | Temporarily suppress notifications and queue visibility for a subject. |
| `ozone_unmute` | Unmute a previously muted subject. |
| `ozone_resolve_appeal` | Resolve an appeal on a subject with a required explanation. |
| `ozone_query_statuses` | Query subject statuses from the Ozone moderation queue with optional filters and pagination. |
| `ozone_query_events` | Query moderation events from Ozone with optional filters and pagination. |
