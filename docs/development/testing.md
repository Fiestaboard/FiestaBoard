---
sidebar_position: 3
description: "Run and write tests for FiestaBoard using pytest for Python and Vitest for TypeScript/React components."
keywords: [FiestaBoard testing, pytest, Vitest, unit tests, integration tests, test guide, Python tests, TypeScript tests]
---

# Testing Guide

How to run and write tests for FiestaBoard.

## Running Tests

### Python Backend Tests

```bash
# Run all Python tests
pytest tests/

# Run with coverage report
pytest tests/ --cov=src --cov=plugins --cov-report=term-missing

# Run specific test file
pytest tests/test_api_server.py

# Run specific test
pytest tests/test_api_server.py::test_health_endpoint
```

### Web UI Tests

```bash
# Run all web tests
npm run test:web

# Run with coverage
cd web && npx vitest --coverage

# Run specific test file
cd web && npx vitest src/components/__tests__/PageEditor.test.tsx
```

### Linting

```bash
# Lint web code (ESLint)
npm run lint:web

# Lint Python code (Pylint)
pylint src/ plugins/
```

## Writing Tests

### Python Plugin Tests

Plugins require a minimum of **80% test coverage**. Use the provided test utilities:

`PluginBase` takes a **manifest** dict in its constructor, not a `config` kwarg.
Set config separately via the `plugin.config` attribute. `validate_config(config)`
takes the config dict as an argument and returns a **list of error strings**
(empty when valid) — it never returns a bool.

```python
from unittest.mock import patch, MagicMock

class TestMyPlugin:
    """Tests for MyPlugin."""

    def _make_plugin(self, config=None):
        """Create a plugin instance with a minimal manifest."""
        plugin = MyPlugin({"id": "my_plugin", "name": "My Plugin", "version": "1.0.0"})
        if config:
            plugin.config = config
        return plugin

    def test_fetch_data_success(self):
        """Test successful data fetching."""
        plugin = self._make_plugin({"api_key": "test"})

        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {"temp": 72}
            )
            result = plugin.fetch_data()

        assert result.available is True
        assert result.data["temp"] == 72

    def test_fetch_data_api_error(self):
        """Test handling of API errors."""
        plugin = self._make_plugin({"api_key": "test"})

        with patch("requests.get") as mock_get:
            mock_get.side_effect = Exception("API Error")
            result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    def test_validate_config(self):
        """Test configuration validation."""
        plugin = self._make_plugin()

        # Missing required key returns a non-empty list of errors
        assert plugin.validate_config({}) != []

        # Valid config returns an empty list
        assert plugin.validate_config({"api_key": "test"}) == []
```

### Web UI Component Tests

Use Vitest with React Testing Library:

```typescript
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import MyComponent from './MyComponent';

describe('MyComponent', () => {
  it('renders correctly', () => {
    render(<MyComponent title="Test" />);
    expect(screen.getByText('Test')).toBeDefined();
  });

  it('handles click events', async () => {
    const onClick = vi.fn();
    render(<MyComponent onClick={onClick} />);
    
    await screen.getByRole('button').click();
    expect(onClick).toHaveBeenCalled();
  });
});
```

## Test Best Practices

1. **Mock external APIs** - Never make real API calls in tests
2. **Test happy path and error cases** - Cover both success and failure scenarios
3. **Test edge cases** - Empty data, missing config, rate limits
4. **Keep tests focused** - One assertion per test when possible
5. **Use descriptive names** - Test names should explain what's being tested

## CI/CD Integration

Tests run automatically on every pull request via GitHub Actions. The CI pipeline:

1. Runs Python tests with coverage
2. Runs web UI tests with coverage
3. Runs linting checks
4. Reports coverage to the PR

:::info
All tests must pass before a PR can be merged. Coverage must meet the minimum threshold for plugins (80%).
:::

## Next Steps

- [Contributing](/docs/development/contributing) - How to contribute
- [Plugin Development Guide](/docs/development/plugin-guide) - Creating plugins with tests
