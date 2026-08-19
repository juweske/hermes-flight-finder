---
name: flight-finder
description: Search flights, find flexible-date deals, manage local flight-price watches, and check saved watches using the hermes-flights CLI.
version: 0.1.0
author: Hermes Flight Finder contributors
platforms: [linux, macos]
metadata:
  hermes:
    tags: [flights, travel, google-flights, price-tracking, automation]
    requires_toolsets: [terminal]
    config:
      - key: flight_finder.home_airports
        description: Default departure airport IATA codes when the user omits an origin.
        default: ""
        prompt: "Which airport or airports do you normally depart from? Use comma-separated IATA codes, for example JFK,LGA,EWR for New York City. Leave blank for no default."
      - key: flight_finder.currency
        description: Preferred currency for flight prices.
        default: USD
        prompt: "Which currency should flight prices normally use? Enter a three-letter code such as USD, EUR, or GBP."
      - key: flight_finder.acceptable_layover
        description: Longest layover considered comfortable; plain numbers mean hours.
        default: 4h
        prompt: "What is the longest layover you normally consider comfortable? Use hours, for example 4h or 2h 30m. A plain number is treated as hours."
      - key: flight_finder.airport_change_policy
        description: How to treat connections that require changing airports.
        default: avoid
        prompt: "How should connections that require changing airports be handled? Enter avoid, warn, or allow."
      - key: flight_finder.overnight_layover_policy
        description: How to treat overnight layovers.
        default: avoid
        prompt: "How should overnight layovers be handled? Enter avoid, warn, or allow."
      - key: flight_finder.self_transfer_policy
        description: How to treat self-transfers or separate-ticket connections.
        default: avoid
        prompt: "How should self-transfers or separate-ticket connections be handled? Enter avoid, warn, or allow."
      - key: flight_finder.max_stops
        description: Default maximum number of stops allowed per direction.
        default: 1
        prompt: "How many stops per direction are normally acceptable? Enter 0, 1, 2, or any."
      - key: flight_finder.interactive_quality_candidates
        description: Number of cheapest flexible date pairs evaluated as concrete itineraries in an interactive search.
        default: 5
        prompt: "How many flexible-date candidates should interactive searches evaluate in detail? Five gives a useful comparison; lower values respond faster and make fewer provider requests."
      - key: flight_finder.watch_quality_candidates
        description: Number of cheapest flexible date pairs evaluated during each repeated watch check.
        default: 3
        prompt: "How many candidates should each scheduled watch check evaluate in detail? A lower value is recommended because every watch repeats these provider requests; 3 is the suggested default."
---

# Flight Finder

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
- Treat `booking_options_warning` with `{ "ok": true }` as degraded success for
  `booking_strategy: "single_itinerary"`. Show the returned `booking_handoff_url` immediately and briefly note that
  vendor-specific options are unavailable; do not report the entire booking handoff as failed.
- Preserve the user's requested currency, passenger count, cabin, airline preference, direct
  requirement, and departure window when they are specified.
- Read the active `flight_finder` profile configuration before building commands. Use its home
  airports and currency when the user omits them. Pass its layover, airport-change, overnight,
  self-transfer, maximum-stop, and candidate-limit values to the CLI. An explicit request in the
  current conversation always overrides the saved profile value.
- Append `--acceptable-layover`, `--airport-changes`, `--overnight-layovers`, `--self-transfers`,
  and `--max-stops` to every `search`, `dates`, and `booking options` command. Append
  `--quality-candidates` to `dates` using `interactive_quality_candidates`, and to `watch check`
  using `watch_quality_candidates`.
- Use IATA airport codes. Resolve unambiguous city names to their primary airport; ask when a city
  has multiple plausible airports or the user's preference matters.
- Pass multiple acceptable airports as comma-separated groups, such as `--from JFK,LGA,EWR` or
  `--to LHR,LGW`. Report the actual airports used by each returned itinerary.
- For an open jaw or road trip, keep the outbound route in `--from` and `--to`, then pass the return
  departure group with `--return-from` and the return arrival group with `--return-to`. Omit
  `--return-to` when the trip returns to the original departure group. Do not manually split an
  open jaw into one-way commands: the CLI searches multi-city first and owns fallback logic.
- Do not book flights, open airline logins, or imply that a fare is guaranteed.
- Complete all required `dates`, `search`, and `booking options` calls before replying. Send exactly
  one user-visible response after all tool calls finish. Never send progress messages such as
  "I am searching", "I will fetch the link", or "I will send the full link next".
- Whenever a table is used, it must have exactly these five columns in this order:
  `Abflug | Nächte | Rückkehr | Ab-Preis | Link`. Do not create any other table layout. Use short
  bullets, not another table, for concrete itinerary details such as airlines, times, and stops.
- Show booking links immediately in the same response as the flight results. This is mandatory
  whenever a concrete recommended itinerary is available. Never ask whether the user wants a link, offer to
  fetch it later, or wait for a follow-up request.
- Copy every URL verbatim from CLI JSON. Never reconstruct, summarize, truncate, or add ellipses to
  a URL. In flexible-date tables, format each `Link` cell as `[Öffnen](URL)`, replacing `URL` with the
  complete `booking_url` copied verbatim. Print
  the recommended concrete itinerary's complete `booking_url` or `booking_handoff_url` on its own
  line directly beneath that itinerary. Never ask the user to request the full link.
- Use `quality_status` and `warnings` exactly as returned. Prefer `acceptable` over `warning`, and
  `warning` over `avoid`, even when the lower-ranked option is cheaper. Keep avoid results visible
  with a clear warning; never silently discard them. Explain warning messages briefly in the
  user's language and do not infer warnings the CLI did not return.
- Treat `booking_strategy: "single_itinerary"` as the normal round-trip or multi-city result. Only
  when the CLI returns `booking_strategy: "separate_tickets"`, show `booking_warning` prominently,
  label the total as a combined estimate, list every value in `component_prices`, and print every
  complete URL in `component_booking_urls`. Never describe separate tickets as one protected itinerary. Do not add
  this warning to an ordinary multi-city result.

## Workflows

### Specific Trip

Use `search` for a fixed departure date, with `--return` for a round trip.

```bash
hermes-flights search --from HAM --to NCE --departure 2026-09-18 --return 2026-09-21 --nonstop --currency EUR --json
```

Offers are quality-ranked and retain `offer_number` for later booking handoff. Summarize the best
returned options with price, dates, stops, airlines, and any warnings. If `offers` is
empty, say that no matching options were returned. Include the recommended offer's `booking_url` immediately in the same answer when present;
place the full URL directly beneath the offer. Do not ask for permission or defer the link to another
message. It opens that specific itinerary rather than a general flight search.

### Flexible Dates

Use `dates` when the user gives a date window and a trip-duration range.

```bash
hermes-flights dates --from HAM --to NCE --start 2026-08-20 --end 2026-10-15 --min-nights 2 --max-nights 5 --nonstop --currency EUR --json
```

The returned `offers` are calendar price/date pairs, not guaranteed itinerary details. Render them
in one table with exactly `Abflug | Nächte | Rückkehr | Ab-Preis | Link`. Every row must contain
that offer's returned `booking_url`; this opens Google Flights for the route and date pair but does
not preselect a concrete itinerary.

Use `quality_candidates` for concrete itinerary details and
`recommended_quality_candidate` for the default recommendation; do not recommend the first
calendar row merely because it has the lowest from-price. For an exploratory request such as a
flexible weekend trip, prepare the complete five-column table, then automatically run `booking options`
for the recommended candidate using its `recommended_offer_number` and the same route,
cabin, passenger, airline, stop, and currency constraints. Include `booking_handoff_url` directly
beneath the recommended itinerary. If it is unavailable, include `google_flights_search_url` on its
own line. Finish all commands before sending exactly one response unless the user explicitly asks only for comparison or says not to retrieve a booking handoff.

For flexible open jaws, the calendar stage uses one-way price calendars only to discover promising
date pairs. The concrete candidate search remains multi-city-first. Present separate-ticket wording
only if the concrete offer explicitly uses the separate-ticket strategy.

### Booking Handoff

When the user chooses a numbered result from a specific-date search and asks to book it, run
`booking options` with the same route, dates, filters, and `--offer` number. Also use it
automatically for the top recommendation from an exploratory flexible-date search. Present the
returned `booking_handoff_url` first. It is the selected itinerary's Google Flights booking page
when available and otherwise the route/date search fallback. Then present useful vendor options,
preferring `is_airline_direct: true` when suitable, and clearly state that the provider confirms the
final price and availability. Do not present a shortened or placeholder vendor URL as a link. Never
open a link, start a booking, or select a vendor without the user explicitly choosing it.
For a separate-ticket fallback, `booking_handoff_url` is null and `booking_handoff_urls` contains
one full URL per independent ticket. Show all links together with the returned warning.

### Manage Watches

Use `watch add` to persist a flexible-date request. Include `--target-price` when the user gives
an absolute alert level and `--drop-percent` for a relative-drop rule.

```bash
hermes-flights watch add --from HAM --to NCE --start 2026-08-20 --end 2026-10-31 --min-nights 2 --max-nights 5 --nonstop --currency EUR --target-price 90 --json
```

Use `watch list --json`, `watch show <id> --json`, and `watch remove <id> --json` for lifecycle
requests. Use `watch history <id> --json` when the user asks whether a current price is the lowest
since tracking started. Report the returned summary and do not imply history from before the watch
was created. After adding a watch, retain the returned `watch.id` when the user refers to it later
in the same conversation.

### Check Watches

Run `hermes-flights watch check` with the profile's quality flags and
`--quality-candidates <watch_quality_candidates> --json`.

If `alerts` is empty, report that no new deal met the configured conditions. If alerts are present,
report route from the saved watch, travel dates, current price, prior best when provided, the
reported reasons, and any returned warnings. Do not infer an airline when the alert does not
contain one.

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
hermes cron create "every 6h" "Run hermes-flights watch check --json. If ok is false, report the error. If alerts is empty, respond with exactly [SILENT]. Otherwise report each alert concisely with route, dates, price, and improvement." --skill flight-finder --name "flight-price-checks" --deliver telegram
```

Scheduling is an explicit user action. Do not create, change, pause, or remove a cron job unless
the user asks for it. Use `hermes cron run <job-id>` to test a newly created job.

Read [the CLI reference](references/cli.md) for complete command and JSON contracts.
