# Milestone 1: fli Provider And Specific-Date Search

## Purpose

Deliver `hermes-flights search` for one-way and round-trip queries. The command must return
project-owned, stable JSON and must never expose `fli` objects or substitute an empty response
for a provider failure.

## Current State

The repository has a standard-library CLI placeholder, package tooling, offline tests, and CI.
There are no domain models, provider interfaces, services, or provider dependencies yet.

The upstream package is distributed as `flights` and imported as `fli`. Its public examples use
`SearchFlights`, `FlightSearchFilters`, `FlightSegment`, `PassengerInfo`, `SeatType`, and
`MaxStops`. A round-trip search returns outbound/return flight pairs.

## Design

Introduce immutable dataclass domain models for query, leg, and offer data. Define
`FlightProvider` as a protocol and implement `FliFlightProvider` as the only module importing
`fli`. The provider maps a domain query to upstream filters, converts every result into domain
objects, and raises a project-owned provider error for upstream failures.

`SearchService` depends only on `FlightProvider`, sorts normalized offers by price, and supplies
the CLI. The CLI validates user input, renders stable JSON on success, and writes a structured
JSON error to stdout with a non-zero exit status when the provider fails. Tests use a fake
provider; one opt-in live smoke test exercises the real provider.

## Steps

1. Add the `flights` dependency and inspect its installed type/source surface.
2. Implement domain models and validation for IATA codes, dates, passenger count, cabin, stops,
   airlines, and departure windows.
3. Implement the provider protocol, `FliFlightProvider`, result normalization, and provider
   error translation.
4. Implement `SearchService` and connect the `search` CLI with human and JSON renderers.
5. Add fixture-backed adapter tests, fake-provider service/CLI tests, and an opt-in live test.
6. Update the README, run the full quality suite, and mark this plan complete.

## Verification

Run `uv run pytest -m "not live"`, `uv run ruff check .`, `uv run ruff format --check .`, and
`uv run pyright`. Exercise `uv run hermes-flights search --help`. Optionally run the marked live
test or a future-date CLI query locally; it must not run in CI.

## Risks

`fli` is an unofficial Google Flights integration and its result shape can change. The isolated
adapter, fixtures, and provider error boundary limit that exposure. Provider requests are never
made in normal tests or CI.

## Status

Complete. The `flights` 0.9.0 dependency is locked; normalized models, provider protocol,
`FliFlightProvider`, `SearchService`, search CLI, offline tests, and a marked live test are in
place. A live HAM-NCE round-trip smoke search returned a normalized nonstop result successfully.
