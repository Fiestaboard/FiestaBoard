---
sidebar_position: 2
description: "Contribute to FiestaBoard - learn about pull requests, coding standards, and how to help improve the project."
keywords: [FiestaBoard contributing, open source, pull request, contribution guide, GitHub, community]
---

# Contributing

Guidelines for contributing to FiestaBoard.

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork:
   ```bash
   git clone https://github.com/your-username/FiestaBoard.git
   cd FiestaBoard
   ```
3. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/my-new-feature
   ```

## Development Environment

```bash
# Set up your environment
cp env.example .env
# Edit .env with your API keys

# Start the development environment with hot reload
docker compose -f docker-compose.dev.yml up --build
```

The development environment provides:
- **Hot reload** for Python backend changes
- **Hot reload** for Next.js frontend changes
- Web UI at `http://localhost:4420`
- API at `http://localhost:4420`

## Making Changes

### Code Standards

- **Python**: Follow PEP 8 and project pylint configuration
- **TypeScript/JavaScript**: Follow ESLint rules
- **Docker-first**: All features should work in Docker
- **No secrets**: Never commit API keys or sensitive data
- **Accessibility**: FiestaBoard aims for [WCAG 2.2 Level AA](/docs/reference/accessibility). Use semantic HTML, provide alt text, ensure sufficient color contrast (4.5:1 for normal text, 3:1 for large text and UI components), and support keyboard navigation.

### Running Tests

```bash
# Python tests
pytest tests/

# Web UI tests
npm run test:web

# Lint web code
npm run lint:web
```

### Plugin Development

When creating a new plugin:
- Minimum **80% test coverage** is required
- Include `README.md` and `docs/SETUP.md`
- Follow the plugin template structure

See the [Plugin Development Guide](/docs/development/plugin-guide) for details.

## Submitting a Pull Request

1. **Commit** your changes with clear commit messages
2. **Push** to your fork
3. **Open a Pull Request** against the `main` branch
4. **Describe** your changes in the PR description
5. **Squash commits** - PRs should be squashed into a single commit when merging

### PR Checklist

- [ ] Code follows project style guidelines
- [ ] Tests pass locally
- [ ] Documentation is updated if needed
- [ ] No secrets or API keys are committed
- [ ] Changes work in Docker

## Reporting Issues

- Use [GitHub Issues](https://github.com/Fiestaboard/FiestaBoard/issues) to report bugs
- Include steps to reproduce the issue
- Include relevant log output
- Specify your environment (OS, Docker version, etc.)

## Security

For security vulnerabilities, please report them responsibly. See the [SECURITY.md](https://github.com/Fiestaboard/FiestaBoard/blob/main/SECURITY.md) file for details.

## Next Steps

- [Local Development](/docs/setup/local-development) - Development setup details
- [Plugin Development Guide](/docs/development/plugin-guide) - Creating plugins
- [Testing Guide](/docs/development/testing) - Running and writing tests
