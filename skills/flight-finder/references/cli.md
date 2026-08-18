# hermes-flights CLI Reference

Use `--json` for every data command. Success returns `{"ok": true, ...}`; a provider failure
returns `{"ok": false, "error": {"code": "provider_unavailable", ...}}` and is not a no-result.

## Search

```bash
hermes-flights search --from IATA --to IATA --departure YYYY-MM-DD [--return YYYY-MM-DD] [--cabin ECONOMY|PREMIUM_ECONOMY|BUSINESS|FIRST] [--passengers N] [--currency ISO] [--nonstop] [--airlines XX,YY] [--departure-window START-END] --json
```

Success contains `offers`, each with price, currency, stops, airlines, and legs.

## Flexible Dates

```bash
hermes-flights dates --from IATA --to IATA --start YYYY-MM-DD --end YYYY-MM-DD --min-nights N --max-nights N [--nonstop] [--currency ISO] --json
```

Success contains price/date offers with `departure_date`, `return_date`, and `nights`.

## Booking Handoff

```bash
hermes-flights booking options --from IATA --to IATA --departure YYYY-MM-DD [--return YYYY-MM-DD] [--cabin ECONOMY|PREMIUM_ECONOMY|BUSINESS|FIRST] [--passengers N] [--currency ISO] [--nonstop] [--airlines XX,YY] [--departure-window START-END] [--offer NUMBER] --json
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

## Watches

```bash
hermes-flights watch add --from IATA --to IATA --start YYYY-MM-DD --end YYYY-MM-DD --min-nights N --max-nights N [--target-price PRICE] [--drop-percent PERCENT] --json
hermes-flights watch list --json
hermes-flights watch show ID --json
hermes-flights watch history ID --json
hermes-flights watch remove ID --json
hermes-flights watch check --json
```

`watch history` returns `watch`, `summary`, and ordered `observations`. The summary identifies the
lowest price since tracking started; each observation includes a `source` (`fli` for current checks).

`watch check` returns `checked` and `alerts`. Each alert includes a price, dates, optional prior
best and percentage drop, and deterministic `reasons` such as `target_price` or `price_drop`.
