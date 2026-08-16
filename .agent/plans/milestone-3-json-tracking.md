# Milestone 3: JSON Watch Storage

## Purpose

Allow users to persist flexible-date flight watches locally and manage them through the CLI.

## Design

`Watch` is a validated project-owned model that captures a flexible-date query plus optional
future alert thresholds. `WatchRepository` keeps storage behind a protocol; `JsonWatchRepository`
stores a versioned state document in `HERMES_FLIGHT_TRACKER_DATA_DIR` or
`~/.hermes-flight-tracker/state.json` and writes it atomically.

The CLI will implement `watch add`, `list`, `show`, and `remove` with stable JSON. Watch checking
and observations remain Milestone 4 work.

## Verification

Test persistence across repository instances, deletion, corrupted-state handling, model
validation, and watch-command JSON. Run the normal offline test, lint, formatting, and type
checks.

## Status

Complete. The versioned, atomic JSON repository and configurable data directory are in place,
along with `watch add`, `list`, `show`, and `remove`. Offline persistence, corruption, and CLI
tests pass; the installed CLI was also verified against an isolated temporary state directory.
