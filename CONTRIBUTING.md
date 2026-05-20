# Contributing to CareerBuddy

Thanks for your interest in contributing. This document covers everything you need to get a development environment running, make a change, and open a pull request.

---

## Getting Started

1. **Fork** the repository on GitHub, then clone your fork:
   ```bash
   git clone https://github.com/<your-username>/CareerBuddy.git
   cd CareerBuddy
   ```

2. **Set up the environment:**
   ```bash
   cp backend/.env.example backend/.env
   # Fill in TELEGRAM_BOT_TOKEN and OPENAI_API_KEY at minimum
   ```

3. **Install Python dependencies** (for local development without Docker):
   ```bash
   cd backend
   pip install poetry
   poetry install
   ```

   Or run everything in Docker:
   ```bash
   docker-compose up --build
   ```

4. **Apply migrations:**
   ```bash
   # Docker
   docker compose exec api alembic upgrade head

   # Local
   cd backend && alembic upgrade head
   ```

5. **Expose your local server** via ngrok so Telegram can reach the webhook:
   ```bash
   ngrok http 8000
   # Set PUBLIC_URL=<ngrok-https-url> in .env, then restart the server
   ```

---

## Running Tests

The test suite uses pytest with an in-memory SQLite database — no live services required.

```bash
cd backend
python -m pytest tests/ -q
```

Run a specific file or test:
```bash
python -m pytest tests/unit/test_conversation_router.py -q
python -m pytest tests/ -k "test_basics_step" -q
```

Run with coverage:
```bash
python -m pytest tests/ --cov=app --cov-report=term-missing -q
```

All tests must pass before opening a PR. If you add a feature, add tests for it.

---

## Branch Naming

| Prefix | Use for |
|---|---|
| `feature/` | New features or user-facing behaviour |
| `fix/` | Bug fixes |
| `docs/` | Documentation only |
| `chore/` | Dependency bumps, tooling, CI |
| `refactor/` | Internal restructure with no behaviour change |

Examples:
```
feature/revision-history
fix/cover-letter-step-skip
docs/runbook-redis-section
```

---

## Pull Request Process

1. Branch off `main`:
   ```bash
   git checkout -b feature/my-thing
   ```

2. Make your changes. Keep commits focused — one logical change per commit.

3. Run tests and confirm they pass.

4. Push your branch and open a PR against `main` on the upstream repository.

5. In the PR description:
   - Describe **what** changed and **why**
   - List any manual testing steps
   - Note any environment variable changes

6. A maintainer will review and merge. Expect feedback within a few days.

---

## Code Style

- **Formatter:** Black (`black .` from `backend/`)
- **Import order:** isort (`isort .` from `backend/`)
- **Linter:** Flake8 (`flake8 app/` from `backend/`)
- **Type hints:** Preferred for function signatures; required for new public functions
- **Comments:** Only when the *why* is non-obvious. Do not describe what the code does — well-named identifiers do that.
- **Docstrings:** One-line max for internal functions. Avoid multi-paragraph docstrings.
- **PEP 8** compliance is enforced by Flake8.

Run all style checks:
```bash
cd backend
black . && isort . && flake8 app/
```

---

## Reporting Bugs

Open a GitHub issue using the following template:

```
**Describe the bug**
A clear description of what went wrong.

**Steps to reproduce**
1. Send message '...'
2. Bot responded with '...'
3. Expected '...'

**Environment**
- Deployment: Railway / local Docker / other
- Python version: (if local)
- Relevant env vars set: (list names only, not values)

**Logs**
Paste the relevant log lines here.
```

For security vulnerabilities, do **not** open a public issue — email the maintainer directly.

---

## License

By contributing, you agree that your contributions will be licensed under the [AGPL-3.0](LICENSE).
