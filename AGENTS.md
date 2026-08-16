# AGENTS.md

## Project

Hermes Flight Tracker is a Python CLI and Hermes Agent skill for searching and monitoring
flight prices using the `fli` library. Read `docs/development.md` before architectural or
user-facing changes.

## Architecture

Keep these layers separated: domain models, flight provider abstraction, `fli` provider adapter,
search/tracking services, persistence, CLI, and Hermes skill. Only `providers/fli.py` may import
`fli`; Hermes must never contain price-comparison logic.

## Development

Use uv. Run `uv sync --extra dev`, `uv run pytest -m "not live"`, `uv run ruff check .`,
`uv run ruff format --check .`, and `uv run pyright` as applicable.

## Testing

Normal tests must not make live Google Flights requests. Use fakes and fixtures; label live
provider tests with the `live` pytest marker. Add a regression test for each bug where practical.

## Engineering Rules

- Prefer small typed modules over large scripts.
- Public domain models and service interfaces must be typed.
- Do not expose `fli` objects outside `providers/fli.py`.
- Keep machine-readable CLI output backwards-compatible.
- Never fabricate results when a provider fails.
- Never store mutable data in the installed skill directory.
- Avoid new production dependencies unless they clearly simplify implementation.

## ExecPlans

For a new provider, storage replacement, MCP support, major deal-scoring work, breaking CLI
change, or major skill redesign, create and maintain an ExecPlan following `.agent/PLANS.md`.

## Definition Of Done

Run relevant tests, lint, formatting, and type checks; confirm changed CLI behavior; and update
documentation for user-visible behavior.

