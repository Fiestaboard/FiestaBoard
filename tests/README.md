# tests/README.md

# Test Helpers for FiestaBoard

This directory contains shared test infrastructure to reduce boilerplate and improve test consistency across the project.

## Structure

- `conftest.py` — Shared pytest fixtures for mocks and sample data
- `factories.py` — Factory functions for creating test objects
- `helpers.py` — Helper assertions for common test patterns
- `golden/` — Reviewed snapshots that tests compare against (see below)
- `__init__.py` — Public API exports for test helpers

## Golden files

### `golden/api_routes.json` — API route inventory

`test_route_inventory.py` snapshots every route on `src.api_server.app`
(path + sorted methods + endpoint name + route class) and fails on any drift.
It exists so that refactors which move routes between modules cannot silently
drop, re-path, or rename an endpoint — the change has to show up as a diff in
the golden file that a reviewer reads.

**Adding or changing a route is expected to fail this test once.** That is the
point: regenerate the golden file deliberately, then read the diff.

```bash
docker compose -f docker-compose.dev.yml exec fiestaboard \
    env UPDATE_ROUTE_INVENTORY=1 pytest tests/test_route_inventory.py
git diff tests/golden/api_routes.json
```

Never regenerate to "make CI green" without reading that diff — a removed line
is a broken client.

Note that the inventory includes the `/mcp` mount, which only exists when the
`mcp` package is installed. If that dependency ever goes missing the golden
test fails rather than the MCP surface disappearing quietly.

## Usage

### Import fixtures from conftest

```python
from tests import sample_page, mock_board_client


def test_something(sample_page, mock_board_client):
    # Use fixtures directly
    pass
```

### Use factory functions

```python
from tests import create_test_page, create_test_schedule

page = create_test_page(title="Custom Page", content="Custom content")
schedule = create_test_schedule(name="My Schedule")
```

### Apply helper validations

```python
from tests import validate_board_layout, validate_plugin_output_format

validate_board_layout(board_state)
validate_plugin_output_format(output, expected_keys=["temperature", "condition"])
```

## Priority Order (from AGENTS.md)

When picking new test work, prioritize:
1. **#506** (test helpers) — reduce boilerplate, enable faster test creation
2. **#505** (backend coverage) — target modules below 80% threshold  
3. **#499** (plugin tests) — add unit tests for untested plugins

## Next Steps

- [ ] Add page object models for Playwright E2E tests
- [ ] Expand test fixtures for common patterns
- [ ] Document additional helper utilities
- [ ] Create integration tests using shared helpers
