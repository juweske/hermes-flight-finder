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
