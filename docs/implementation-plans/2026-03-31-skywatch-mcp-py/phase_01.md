# Skywatch MCP Python Implementation Plan

**Goal:** Port the existing TypeScript MCP server to Python 3.12+, exposing 21 tools across five domains via the official MCP Python SDK's FastMCP layer.

**Architecture:** Async Python MCP server using FastMCP with Pydantic v2 for input validation. Tool handlers registered via `@mcp.tool()` decorators. All I/O async throughout (clickhouse-connect, httpx, dnspython, asyncio.to_thread for WHOIS).

**Tech Stack:** Python 3.12+, uv, mcp SDK (FastMCP), Pydantic v2, pydantic-settings, clickhouse-connect, httpx, dnspython, python-whois, pytest, pytest-asyncio, pytest-mock

**Scope:** 8 phases from original design (phases 1-8)

**Codebase verified:** 2026-04-01 — greenfield repo, only docs/design-plans/ exists

---

## Acceptance Criteria Coverage

This phase is infrastructure scaffolding. No acceptance criteria are directly tested.

**Verifies: None** — operational verification only (uv sync, uv run pytest, uv run skywatch-mcp)

---

## Phase 1: Project Scaffolding

**Goal:** Initialise the uv-managed Python project with all dependencies and a minimal running MCP server.

**Done when:** `uv sync` installs all deps, `uv run skywatch-mcp` starts and connects via stdio without errors, `uv run pytest` runs (even with no tests yet)

---

<!-- START_TASK_1 -->
### Task 1: Create pyproject.toml

**Files:**
- Create: `pyproject.toml`

**Step 1: Create the file**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "skywatch-mcp"
version = "0.1.0"
description = "MCP server for investigating activity on the AT Protocol / Bluesky network"
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "clickhouse-connect>=0.7",
    "httpx>=0.27",
    "dnspython>=2.6",
    "python-whois>=0.9",
]

[project.scripts]
skywatch-mcp = "skywatch_mcp.server:main"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-mock>=3.14",
    "mypy>=1.13.0",
    "ruff>=0.4",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "--import-mode=importlib"
asyncio_mode = "auto"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.mypy]
python_version = "3.12"
strict = true
```

**Step 2: Verify operationally**

Run: `uv sync`
Expected: All dependencies install without errors

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pyproject.toml with all dependencies"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create package structure and server entry point

**Files:**
- Create: `src/skywatch_mcp/__init__.py`
- Create: `src/skywatch_mcp/server.py`

**Step 1: Create the package marker**

`src/skywatch_mcp/__init__.py` — empty file.

**Step 2: Create the minimal server**

`src/skywatch_mcp/server.py`:

```python
# pattern: Imperative Shell

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("skywatch-mcp")


def main() -> None:
    mcp.run(transport="stdio")
```

**Step 3: Verify operationally**

Run: `uv run skywatch-mcp`
Expected: Server starts and listens on stdio (will block waiting for input — Ctrl+C to stop). No import errors, no crashes.

Run: `echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1.0"}},"id":1}' | uv run skywatch-mcp`
Expected: JSON-RPC response with server capabilities (confirms stdio transport works)

**Step 4: Commit**

```bash
git add src/skywatch_mcp/__init__.py src/skywatch_mcp/server.py
git commit -m "feat: add minimal FastMCP server with stdio transport"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create test directory and conftest

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Create the files**

`tests/__init__.py` — empty file.

`tests/conftest.py`:

```python
# pattern: Imperative Shell
```

Empty conftest for now. Shared fixtures will be added in later phases as needed.

**Step 2: Verify operationally**

Run: `uv run pytest`
Expected: Runs successfully with "no tests ran" (0 collected). No import errors.

Run: `uv run pytest --co`
Expected: Shows collection output with no errors.

**Step 3: Commit**

```bash
git add tests/__init__.py tests/conftest.py
git commit -m "chore: add test directory with conftest"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Create placeholder sub-package directories

**Files:**
- Create: `src/skywatch_mcp/models/__init__.py`
- Create: `src/skywatch_mcp/lib/__init__.py`
- Create: `src/skywatch_mcp/tools/__init__.py`

**Step 1: Create all three `__init__.py` files**

All three files are empty. These establish the sub-package structure for later phases:
- `models/` — Pydantic input/output models
- `lib/` — Pure functions and client wrappers
- `tools/` — MCP tool handler modules

**Step 2: Verify operationally**

Run: `python -c "import skywatch_mcp.models; import skywatch_mcp.lib; import skywatch_mcp.tools; print('OK')"`
Expected: Prints "OK" with no import errors.

Alternatively: `uv run python -c "from skywatch_mcp.models import *; from skywatch_mcp.lib import *; from skywatch_mcp.tools import *; print('OK')"`

**Step 3: Commit**

```bash
git add src/skywatch_mcp/models/__init__.py src/skywatch_mcp/lib/__init__.py src/skywatch_mcp/tools/__init__.py
git commit -m "chore: add models, lib, and tools sub-packages"
```
<!-- END_TASK_4 -->
