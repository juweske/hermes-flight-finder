# Test With Hermes

This walkthrough verifies the installed CLI, the Hermes skill, a real flight search, a saved watch,
and optional scheduled checks.

## 1. Install The CLI

Install Python 3.11+ and [uv](https://docs.astral.sh/uv/), then run:

```bash
uv tool install git+https://github.com/juweske/hermes-flight-finder.git
hermes-flights doctor --json
```

Expected result: the JSON response has `"ok": true` and successful `flight_provider`,
`data_directory`, and `local_state` checks. This command does not search Google Flights.

For a local checkout, replace the install command with `uv tool install .` from the project root.

## 2. Verify A Live CLI Search

Choose a future trip and run a narrow query:

```bash
hermes-flights search --from HAM --to NCE --departure 2026-10-16 --return 2026-10-19 --nonstop --currency EUR --json
```

Expected result: a JSON object with `"ok": true` and an `offers` array. An empty array is a valid
result when no route matches. A provider issue returns `"ok": false` and a non-zero exit status;
retry later rather than treating it as no flights.

## 3. Install The Hermes Skill

Install the skill from the published repository:

```bash
hermes skills install juweske/hermes-flight-finder/skills/flight-tracker --now
```

`--now` loads the skill in the current Hermes session. Without it, start a fresh Hermes session.
Confirm that `hermes-flights --help` runs in the terminal environment used by Hermes.

## 4. Verify The Agent Workflow

Ask Hermes:

```text
Find the cheapest nonstop return flights from Hamburg to Nice for 2-5 nights between 2026-10-01 and 2026-11-15, in EUR.
```

Verify that Hermes returns actual dates and prices from the command result, and does not invent
itinerary details for flexible-date results.

## 5. Verify A Price Watch

Ask Hermes:

```text
Track nonstop 2-5 night trips from Hamburg to Nice between 2026-10-01 and 2026-11-15, and alert me at EUR 120 or less.
```

Then verify the persisted watch and run its first check:

```bash
hermes-flights watch list --json
hermes-flights watch check --json
```

Expected result: `watch list` contains the new watch. The first check stores a baseline; it only
returns an alert immediately when the target price is met. Repeating the exact same successful
check does not repeat an alert for unchanged price and dates.

## 6. Verify Scheduled Delivery (Optional)

After the watch works, ask Hermes to create the schedule, or use the command in
[Hermes cron integration](hermes-cron.md). Run it once with `hermes cron run <job-id>`.

Expected result: a qualifying deal is delivered as a concise message. When there are no new alerts,
the task ends with `[SILENT]`, so no routine notification is sent.
