# Hermes Flight Finder

Ask your Hermes agent:

> Track cheap nonstop 2-5 night trips from Hamburg to Nice during the next eight weeks.

Hermes Flight Finder will search Google Flights through `fli`, store local price history,
and let Hermes notify you when a configured deal condition is met.

## Status

V1 is ready for source distribution. Specific-date search, flexible dates, local watches, price
history, deterministic alerts, the Hermes skill bundle, and cron guidance are available.

## Roadmap

### V1: Available Now

- [x] Specific-date and flexible-date flight search
- [x] Local JSON watches, observations, and deterministic target-price or price-drop alerts
- [x] `watch history` with lowest-price-since-tracking summaries
- [x] Hermes skill, JSON-first CLI contract, and scheduled watch-check guidance
- [x] Local-first storage with no account, analytics, or API key

### P0: Booking And Trip Planning

- [x] User-approved Google Flights search handoff for selected offers
- [x] Preselected Google Flights itinerary handoff with both outbound and return flights already chosen
- [ ] Full vendor-specific booking deep links when supported by a provider
- [ ] Booking context: bag allowance, fare conditions, refundability, and change policy when available
- [x] Configurable itinerary-quality rules and warnings: long or overnight layovers, airport changes, self-transfers, and impractical total journey times
- [x] Multi-airport, open-jaw, and road-trip itineraries, with a warned separate-ticket fallback only when multi-city returns no matches
- [ ] Flexible-date price grid for comparing possible trip-date combinations
- [ ] Watch health, stale-data status, and provider error visibility

### P1: Price Intelligence And Sharing

- [ ] Historic price backfill from an optional provider, with all-time and rolling low points, trend, volatility, and fare context
- [ ] Explainable deal scoring based on price, stops, duration, time, and historical context
- [ ] Saved comparisons and CSV or JSON export
- [ ] Shareable price reports for Telegram and other Hermes channels, including a rendered price-history chart, low-point markers, and the best current date combinations

### P2: Platform And Delivery Expansion

- [ ] Per-watch notification preferences, quiet hours, and delivery controls
- [ ] Optional provider integrations for improved reliability and booking-link coverage
- [ ] MCP interface for non-Hermes agents and automation workflows
- [ ] Evaluate full in-app booking only with appropriate partners and complete payment, confirmation, changes, cancellations, and support design


## Development

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
uv run hermes-flights --help
uv run pytest -m "not live"
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

## Install

Hermes Flight Finder is distributed from this GitHub repository. Install the CLI with `uv`:

```bash
uv tool install git+https://github.com/juweske/hermes-flight-finder.git
hermes-flights doctor --json
```

For a local checkout, use `uv tool install .` from the repository root instead. `doctor` makes no
flight search: it verifies that the provider package imports, the local data directory is writable,
and any existing local state is valid.

See [testing with Hermes](docs/hermes-testing.md) for the full install, skill setup, and verification
walkthrough.

## Specific-Date Search

```bash
uv run hermes-flights search \
  --from HAM \
  --to NCE \
  --departure 2026-09-18 \
  --return 2026-09-21 \
  --nonstop \
  --currency EUR \
  --json
```

Successful JSON contains an `ok` flag and normalized offers. A provider failure returns a
non-zero exit status and a stable JSON error object; it is never represented as an empty result.
Concrete offers include `quality_status` and structured `warnings`. Acceptable itineraries are
ranked ahead of warning and avoid results, while every result remains visible.

Airport groups can be comma-separated. Open-jaw trips use `--return-from` and optionally
`--return-to`:

```bash
hermes-flights search \
  --from JFK,LGA,EWR --to NCE \
  --departure 2026-09-18 \
  --return-from MRS --return-to BOS \
  --return 2026-09-27 --currency USD --json
```

Changed return endpoints are searched as one multi-city itinerary. Only when that search returns
no matching offers does Flight Finder combine independent one-way flights. Those results use
`booking_strategy: "separate_tickets"`, expose each component price and booking URL, and include a
warning about separate purchases, baggage rules, changes, cancellations, and the lack of
cross-booking protection. A cheaper one-way combination never silently replaces an available
multi-city result.

## Flexible-Date Search

```bash
uv run hermes-flights dates \
  --from HAM \
  --to NCE \
  --start 2026-08-20 \
  --end 2026-10-15 \
  --min-nights 2 \
  --max-nights 5 \
  --nonstop \
  --currency EUR \
  --json
```

The command makes one calendar request per requested trip duration, then merges duplicate date
pairs and orders the results by price. Every result includes a Google Flights route-and-date link.
By default, the five cheapest date pairs are also searched as concrete itineraries and returned in
`quality_candidates`; `recommended_quality_candidate` prefers a practical itinerary over a cheaper
one with severe warnings. Change the request budget with `--quality-candidates N`.
For flexible open jaws, two one-way calendars identify promising date pairs, but every concrete
candidate is still searched as multi-city before the separate-ticket fallback can activate.

## Itinerary Preferences

Specific searches, flexible searches, booking handoffs, and watch checks share the same quality
flags:

```bash
hermes-flights dates ... \
  --acceptable-layover 4h \
  --airport-changes avoid \
  --overnight-layovers avoid \
  --self-transfers avoid \
  --max-stops 1 \
  --quality-candidates 5 \
  --json
```

Durations accept values such as `4h`, `2.5h`, `2h 30m`, or `150m`. Connection policies accept
`avoid`, `warn`, or `allow`. `avoid` adds a severe warning and lowers recommendation priority,
`warn` labels the itinerary without excluding it, and `allow` suppresses that warning. Results are
never silently removed by these policies.

## Booking Handoff

Use `booking options` after choosing a numbered specific-date search result, or automatically for the
top recommendation from a flexible-date search. It reruns the search and
returns a deterministic Google Flights link for the selected itinerary plus current airline-direct
or OTA links when available. If an exact itinerary link cannot be constructed, the response uses a
route-and-date Google Flights search handoff instead. It never opens a link or makes a purchase. Booking prices and availability can change before the provider
page loads.

```bash
hermes-flights booking options \
  --from HAM --to NCE \
  --departure 2026-09-18 --return 2026-09-21 \
  --offer 1 --json
```

## Flight Watches

```bash
hermes-flights watch add \
  --from HAM --to NCE \
  --start 2026-08-20 --end 2026-10-31 \
  --min-nights 2 --max-nights 5 \
  --nonstop --currency EUR \
  --target-price 90 --json

hermes-flights watch list --json
hermes-flights watch show <watch-id> --json
hermes-flights watch history <watch-id> --json
hermes-flights watch remove <watch-id> --json
```

Watch state is stored locally in `~/.hermes-flight-finder/state.json`; observations and alert
records are stored alongside it in `history.json`. Set `HERMES_FLIGHT_FINDER_DATA_DIR` to use
another local directory.

## Price Checking

`hermes-flights watch check --json` searches every saved watch, concretely evaluates the cheapest
three date pairs by default, stores the best practical current itinerary, and returns alerts only
when a target price is met or a configured percentage drop occurs. Use `--quality-candidates N`
to change that recurring request budget. Observation and alert JSON includes warning details.
The first check establishes a baseline unless its target price is already met; repeated alerts for
the same price and dates are suppressed.

`hermes-flights watch history <watch-id> --json` returns each locally recorded observation and a
summary with the latest price, the lowest price since tracking began, and whether the latest check
is that low. Current observations are marked with `source: "fli"`. A future historical provider can
add earlier observations with its own source without changing this command or existing local data.

## Hermes Skill

The Hermes skill bundle is in `skills/flight-finder/`. Once this repository is published, install
it with:

```bash
hermes skills install juweske/hermes-flight-finder/skills/flight-finder
```

Install the Python CLI separately, then start a fresh Hermes session (or use `--now` when
installing) so Hermes can load the skill. It translates travel requests into
`hermes-flights ... --json` commands and only reports returned data.

Configure per-profile defaults and itinerary preferences after installation:

```bash
hermes config migrate
```

Hermes stores these non-secret settings under `skills.config.flight_finder` in the active
profile. The setup covers home airports, currency, layover and connection policies, and separate
candidate limits for interactive searches and repeated watch checks. Interactive searches default
to five detailed candidates; watches recommend the lower default of three to limit recurring
provider traffic.

See [Hermes cron integration](docs/hermes-cron.md) to schedule watch checks and suppress quiet
runs with Hermes's `[SILENT]` delivery token.

## Privacy And Limitations

The application is local-first: it will store watch settings and price observations on your
machine, without analytics, telemetry, accounts, or a hosted backend. It uses an unofficial
Google Flights integration, is not affiliated with Google, does not book flights, and flight
prices can change at any time.

## License

MIT. See [LICENSE](LICENSE).
