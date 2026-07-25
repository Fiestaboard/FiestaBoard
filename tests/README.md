# tests/README.md

# Test Helpers for FiestaBoard

This directory contains shared test infrastructure to reduce boilerplate and improve test consistency across the project.

## Structure

- `conftest.py` — Shared pytest fixtures for mocks and sample data
- `factories.py` — Factory functions for creating test objects
- `helpers.py` — Helper assertions for common test patterns
- `__init__.py` — Public API exports for test helpers

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
