# Hermes Flight Finder

Ask your Hermes agent:

> Track cheap nonstop 2-5 night trips from Hamburg to Nice during the next eight weeks.

Hermes Flight Finder will search Google Flights through `fli`, store local price history,
and let Hermes notify you when a configured deal condition is met.

## Status

V1 is ready for source distribution. Specific-date search, flexible dates, local watches, price
history, deterministic alerts, the Hermes skill bundle, and cron guidance are available.

## Planned Features

- Specific-date and flexible-date flight search
- Local JSON-backed price watches and history
- Deterministic threshold and price-drop alerts
- A Hermes skill that invokes the CLI in JSON mode

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
pairs and orders the results by price.

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
hermes-flights watch remove <watch-id> --json
```

Watch state is stored locally in `~/.hermes-flight-finder/state.json`; observations and alert
records are stored alongside it in `history.json`. Set `HERMES_FLIGHT_FINDER_DATA_DIR` to use
another local directory.

## Price Checking

`hermes-flights watch check --json` searches every saved watch, stores the lowest current date
pair, and returns alerts only when a target price is met or a configured percentage drop occurs.
The first check establishes a baseline unless its target price is already met; repeated alerts for
the same price and dates are suppressed.

## Hermes Skill

The Hermes skill bundle is in `skills/flight-tracker/`. Once this repository is published, install
it with:

```bash
hermes skills install juweske/hermes-flight-finder/skills/flight-tracker
```

Install the Python CLI separately, then start a fresh Hermes session (or use `--now` when
installing) so Hermes can load the skill. It translates travel requests into
`hermes-flights ... --json` commands and only reports returned data.

See [Hermes cron integration](docs/hermes-cron.md) to schedule watch checks and suppress quiet
runs with Hermes's `[SILENT]` delivery token.

## Privacy And Limitations

The application is local-first: it will store watch settings and price observations on your
machine, without analytics, telemetry, accounts, or a hosted backend. It uses an unofficial
Google Flights integration, is not affiliated with Google, does not book flights, and flight
prices can change at any time.

## License

MIT. See [LICENSE](LICENSE).
