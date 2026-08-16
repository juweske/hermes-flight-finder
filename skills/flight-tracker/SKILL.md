---
name: flight-tracker
description: Search flights, find flexible-date deals, manage local flight-price watches, and check saved watches using the hermes-flights CLI.
version: 0.1.0
author: Hermes Flight Finder contributors
platforms: [linux, macos]
metadata:
  hermes:
    tags: [flights, travel, google-flights, price-tracking, automation]
    requires_toolsets: [terminal]
---

# Flight Tracker

Use this skill for flight searches, flexible-trip deal searches, saved price watches, and watch
checks. Use the `hermes-flights` executable through the terminal. The CLI performs all price
comparison and alert logic; interpret its JSON rather than reimplementing it.

## Preconditions

1. Confirm `hermes-flights` is available with `hermes-flights --help` when its availability is
   unknown.
2. If it is absent, explain that the Hermes Flight Finder Python application must be installed
   before flight commands can run. Do not claim an installation succeeded unless the terminal
   confirms it.
3. Resolve natural-language dates to explicit `YYYY-MM-DD` values before invoking the CLI. Ask a
   concise follow-up when the user has not supplied enough date information.

## Required Behavior

- Always use `--json` for data commands.
- Never invent availability, fares, routes, dates, airlines, stops, watch status, or price
  history. Only report facts returned by `hermes-flights`.
- Treat `{ "ok": false }` as a failure, not an empty search. Explain the returned error briefly.
- Preserve the user's requested currency, passenger count, cabin, airline preference, direct
  requirement, and departure window when they are specified.
- Use IATA airport codes. Resolve unambiguous city names to their primary airport; ask when a city
  has multiple plausible airports or the user's preference matters.
- Do not book flights, open airline logins, or imply that a fare is guaranteed.

## Workflows

### Specific Trip

Use `search` for a fixed departure date, with `--return` for a round trip.

```bash
hermes-flights search --from HAM --to NCE --departure 2026-09-18 --return 2026-09-21 --nonstop --currency EUR --json
```

Summarize the cheapest returned options with price, dates, stops, and airlines. If `offers` is
empty, say that no matching options were returned.

### Flexible Dates

Use `dates` when the user gives a date window and a trip-duration range.

```bash
hermes-flights dates --from HAM --to NCE --start 2026-08-20 --end 2026-10-15 --min-nights 2 --max-nights 5 --nonstop --currency EUR --json
```

The returned offers are calendar price/date pairs, not guaranteed itinerary details. Describe the
price, departure date, return date, and nights only.

### Manage Watches

Use `watch add` to persist a flexible-date request. Include `--target-price` when the user gives
an absolute alert level and `--drop-percent` for a relative-drop rule.

```bash
hermes-flights watch add --from HAM --to NCE --start 2026-08-20 --end 2026-10-31 --min-nights 2 --max-nights 5 --nonstop --currency EUR --target-price 90 --json
```

Use `watch list --json`, `watch show <id> --json`, and `watch remove <id> --json` for lifecycle
requests. After adding a watch, retain the returned `watch.id` when the user refers to it later in
the same conversation.

### Check Watches

Run `hermes-flights watch check --json`.

If `alerts` is empty, report that no new deal met the configured conditions. If alerts are present,
report route from the saved watch, travel dates, current price, prior best when provided, and the
reported reasons. Do not infer an airline when the alert does not contain one.

## Scheduled Checks

Hermes owns scheduling. Do not add a scheduler to the Python application. When the user explicitly
asks to schedule checks, create a Hermes cron job that loads this skill and uses this task prompt:

```text
Run hermes-flights watch check --json. If the command reports ok false, report the error. If alerts
is empty, respond with exactly [SILENT]. If alerts are present, send a concise notification for
each deal with the saved route, dates, price, previous best or percentage drop when present, and
stops only when returned. Never invent missing fields.
```

Example standalone CLI setup:

```bash
hermes cron create "every 6h" "Run hermes-flights watch check --json. If ok is false, report the error. If alerts is empty, respond with exactly [SILENT]. Otherwise report each alert concisely with route, dates, price, and improvement." --skill flight-tracker --name "flight-price-checks" --deliver telegram
```

Scheduling is an explicit user action. Do not create, change, pause, or remove a cron job unless
the user asks for it. Use `hermes cron run <job-id>` to test a newly created job.

Read [the CLI reference](references/cli.md) for complete command and JSON contracts.
