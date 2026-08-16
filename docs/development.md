# Development Guide

This repository implements the Hermes Flight Finder V1 development guide supplied with the
project. The guide is the product source of truth for the initial milestones.

## Milestones

1. Repository bootstrap
2. `fli` provider and specific-date search
3. Flexible-date search
4. JSON tracking
5. Watch checking and deterministic alerts
6. Hermes skill and cron documentation
7. Public distribution

## Core Constraints

- The application is CLI-first; Hermes calls deterministic CLI commands.
- The `fli` adapter is isolated to `src/hermes_flight_tracker/providers/fli.py`.
- Persist only normalized, project-owned domain models.
- Keep state local and behind a repository interface.
- Keep regular tests offline; reserve provider calls for `live` tests.
