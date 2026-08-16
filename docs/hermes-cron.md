# Hermes Cron Integration

Hermes Flight Tracker does not schedule its own work. Hermes Agent owns schedules, sessions, and
message delivery; this project exposes the deterministic `hermes-flights watch check --json`
command that a Hermes cron job invokes.

## Notification Policy

1. Run `hermes-flights watch check --json`.
2. If the CLI returns `ok: false`, report the error. Do not use a silence token.
3. If `alerts` is empty, respond with exactly `[SILENT]`.
4. If alerts exist, send a concise alert for each result with route, dates, price, and available
   comparison details.

`[SILENT]` suppresses outbound delivery only when it is the complete final response. It prevents
routine quiet checks from creating chat notifications.

## Create A Job

After installing the `flight-tracker` skill and the `hermes-flights` executable:

```bash
hermes cron create "every 6h" "Run hermes-flights watch check --json. If ok is false, report the error. If alerts is empty, respond with exactly [SILENT]. Otherwise report each alert concisely with route, dates, price, and improvement." --skill flight-tracker --name "flight-price-checks" --deliver telegram
```

Use `--deliver origin` for the source chat, or another configured Hermes delivery target. Confirm
the schedule with the user before creating it, then test it once with:

```bash
hermes cron run <job-id>
```

Manage jobs with `hermes cron list`, `pause`, `resume`, `edit`, and `remove`.
