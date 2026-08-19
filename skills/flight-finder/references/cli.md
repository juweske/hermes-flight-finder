# hermes-flights CLI Reference

Use `--json` for every data command. Success returns `{"ok": true, ...}`; a provider failure
returns `{"ok": false, "error": {"code": "provider_unavailable", ...}}` and is not a no-result.

## Search

```bash
hermes-flights search --from IATA --to IATA --departure YYYY-MM-DD [--return YYYY-MM-DD] [--cabin ECONOMY|PREMIUM_ECONOMY|BUSINESS|FIRST] [--passengers N] [--currency ISO] [--nonstop|--max-stops 0|1|2|any] [quality options] [--airlines XX,YY] [--departure-window START-END] --json
```

Success contains quality-ranked `offers`, each with its original `offer_number`, price, currency,
stops, airlines, legs, `quality_status`, and structured `warnings`.

## Flexible Dates

```bash
hermes-flights dates --from IATA --to IATA --start YYYY-MM-DD --end YYYY-MM-DD --min-nights N --max-nights N [--nonstop|--max-stops 0|1|2|any] [--currency ISO] [quality options] [--quality-candidates N] --json
```

Success contains price/date offers with `departure_date`, `return_date`, `nights`, and a
`booking_url` that opens Google Flights for that route and date pair. This is a date-search handoff,
not a preselected itinerary.

The cheapest `N` date pairs are also searched as concrete itineraries. They appear in
`quality_candidates`; `recommended_quality_candidate` is the best practical option after warning
evaluation, not necessarily the lowest calendar price.

## Booking Handoff

```bash
hermes-flights booking options --from IATA --to IATA --departure YYYY-MM-DD [--return YYYY-MM-DD] [--cabin ECONOMY|PREMIUM_ECONOMY|BUSINESS|FIRST] [--passengers N] [--currency ISO] [--nonstop|--max-stops 0|1|2|any] [quality options] [--airlines XX,YY] [--departure-window START-END] [--offer NUMBER] --json
```

The command reruns the exact search and returns `selected_offer`, current `booking_options`, and a
`booking_handoff_url`. When Fli can construct a deterministic `tfs` URL, the handoff opens the
selected itinerary's Google Flights booking page; otherwise it uses `google_flights_search_url` as
the fallback. If vendor-option retrieval fails after an exact itinerary was selected,
the command still returns `ok: true`, the handoff, an empty `booking_options` list, and a
`booking_options_warning`.

Each option includes vendor details, refreshed price when available, and full direct or Google
click-through URLs when supplied by the provider. `google_flights_search_url` is always a valid
fallback handoff. The CLI never opens a URL or completes a booking.

## Quality Options

The following options apply to `search`, `dates`, `booking options`, and `watch check`:

```text
--acceptable-layover 4h
--airport-changes avoid|warn|allow
--overnight-layovers avoid|warn|allow
--self-transfers avoid|warn|allow
```

`--acceptable-layover` also accepts `2.5h`, `2h 30m`, `150m`, or a plain number of hours.
`avoid` produces a severe warning and lowers recommendation priority; no result is silently
removed. Searches also accept `--max-stops 0|1|2|any`.

## Watches

```bash
hermes-flights watch add --from IATA --to IATA --start YYYY-MM-DD --end YYYY-MM-DD --min-nights N --max-nights N [--target-price PRICE] [--drop-percent PERCENT] --json
hermes-flights watch list --json
hermes-flights watch show ID --json
hermes-flights watch history ID --json
hermes-flights watch remove ID --json
hermes-flights watch check [quality options] [--quality-candidates N] --json
```

`watch history` returns `watch`, `summary`, and ordered `observations`. The summary identifies the
lowest price since tracking started; each observation includes a `source` (`fli` for current checks),
`quality_status`, and structured `warnings`.

`watch check` returns `checked` and `alerts`. Each alert includes a price, dates, optional prior
best and percentage drop, deterministic `reasons` such as `target_price` or `price_drop`, and the
chosen concrete itinerary's quality status and warnings. The default recurring candidate budget is
three.
