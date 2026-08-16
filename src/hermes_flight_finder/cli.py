"""Command-line entry point for Hermes Flight Finder."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from decimal import Decimal

from hermes_flight_finder.config import get_data_dir
from hermes_flight_finder.models import (
    Cabin,
    FlexibleDateOffer,
    FlexibleSearchQuery,
    FlightOffer,
    FlightQuery,
    MaxStops,
    Watch,
    new_watch_id,
)
from hermes_flight_finder.providers import FliFlightProvider, FlightProvider, ProviderError
from hermes_flight_finder.search import FlexibleSearchService, SearchService
from hermes_flight_finder.storage import JsonWatchRepository, StateCorruptError, WatchRepository
from hermes_flight_finder.tracking import WatchCheckService


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser and command placeholders for the V1 CLI."""
    parser = argparse.ArgumentParser(
        prog="hermes-flights",
        description="Search and monitor flight prices for Hermes Agent.",
    )
    subcommands = parser.add_subparsers(dest="command", title="commands")

    search = subcommands.add_parser("search", help="Search a specific trip.")
    search.add_argument("--from", dest="origin", required=True, metavar="IATA")
    search.add_argument("--to", dest="destination", required=True, metavar="IATA")
    search.add_argument("--departure", required=True, type=_parse_date, metavar="YYYY-MM-DD")
    search.add_argument("--return", dest="return_date", type=_parse_date, metavar="YYYY-MM-DD")
    search.add_argument("--cabin", choices=list(Cabin), default=Cabin.ECONOMY)
    search.add_argument("--passengers", type=int, default=1)
    search.add_argument("--currency", default="EUR")
    search.add_argument("--nonstop", action="store_true")
    search.add_argument("--airlines", type=_parse_airlines, default=())
    search.add_argument("--departure-window", type=_parse_departure_window, metavar="START-END")
    search.add_argument("--json", action="store_true", dest="json_output")

    dates = subcommands.add_parser("dates", help="Search flexible travel dates.")
    dates.add_argument("--from", dest="origin", required=True, metavar="IATA")
    dates.add_argument("--to", dest="destination", required=True, metavar="IATA")
    dates.add_argument("--start", required=True, type=_parse_date, metavar="YYYY-MM-DD")
    dates.add_argument("--end", required=True, type=_parse_date, metavar="YYYY-MM-DD")
    dates.add_argument("--min-nights", required=True, type=int)
    dates.add_argument("--max-nights", required=True, type=int)
    dates.add_argument("--cabin", choices=list(Cabin), default=Cabin.ECONOMY)
    dates.add_argument("--passengers", type=int, default=1)
    dates.add_argument("--currency", default="EUR")
    dates.add_argument("--nonstop", action="store_true")
    dates.add_argument("--airlines", type=_parse_airlines, default=())
    dates.add_argument("--departure-window", type=_parse_departure_window, metavar="START-END")
    dates.add_argument("--json", action="store_true", dest="json_output")

    doctor = subcommands.add_parser(
        "doctor", help="Validate the local installation and configuration."
    )
    doctor.add_argument("--json", action="store_true", dest="json_output")

    watch = subcommands.add_parser("watch", help="Manage persistent flight watches.")
    watch_subcommands = watch.add_subparsers(dest="watch_command", title="watch commands")
    watch_add = watch_subcommands.add_parser("add", help="Create a flight watch.")
    _add_watch_query_arguments(watch_add)
    watch_add.add_argument("--id", dest="watch_id")
    watch_add.add_argument("--target-price", type=_parse_decimal)
    watch_add.add_argument("--drop-percent", type=_parse_decimal)
    watch_add.add_argument("--json", action="store_true", dest="json_output")

    watch_list = watch_subcommands.add_parser("list", help="List flight watches.")
    watch_list.add_argument("--json", action="store_true", dest="json_output")

    watch_show = watch_subcommands.add_parser("show", help="Show a flight watch.")
    watch_show.add_argument("watch_id")
    watch_show.add_argument("--json", action="store_true", dest="json_output")

    watch_remove = watch_subcommands.add_parser("remove", help="Remove a flight watch.")
    watch_remove.add_argument("watch_id")
    watch_remove.add_argument("--json", action="store_true", dest="json_output")

    watch_check = watch_subcommands.add_parser("check", help="Check all flight watches.")
    watch_check.add_argument("--json", action="store_true", dest="json_output")

    return parser


def main(
    argv: Sequence[str] | None = None,
    provider: FlightProvider | None = None,
    repository: WatchRepository | None = None,
) -> int:
    """Run the CLI and return a process exit status."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "search":
        return _run_search(arguments, provider or FliFlightProvider())
    if arguments.command == "dates":
        return _run_dates(arguments, provider or FliFlightProvider())
    if arguments.command == "doctor":
        return _run_doctor(
            arguments, provider or FliFlightProvider(), repository or JsonWatchRepository()
        )
    if arguments.command == "watch" and arguments.watch_command in {
        "add",
        "list",
        "show",
        "remove",
    }:
        return _run_watch(arguments, repository or JsonWatchRepository())
    if arguments.command == "watch" and arguments.watch_command == "check":
        return _run_watch_check(
            arguments,
            provider or FliFlightProvider(),
            repository or JsonWatchRepository(),
        )
    parser.print_help()
    return 0


def _run_doctor(
    arguments: argparse.Namespace, provider: FlightProvider, repository: WatchRepository
) -> int:
    """Check local prerequisites without making a flight-provider request."""
    checks: list[dict[str, object]] = [
        {"name": "flight_provider", "ok": True, "detail": type(provider).__name__},
    ]
    data_dir = get_data_dir()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=data_dir):
            pass
        checks.append({"name": "data_directory", "ok": True, "detail": str(data_dir)})
    except OSError as error:
        checks.append({"name": "data_directory", "ok": False, "detail": str(error)})

    try:
        repository.list()
        checks.append({"name": "local_state", "ok": True, "detail": "valid"})
    except StateCorruptError as error:
        checks.append({"name": "local_state", "ok": False, "detail": str(error)})

    ok = all(check["ok"] is True for check in checks)
    payload: dict[str, object] = {"ok": ok, "checks": checks}
    if arguments.json_output:
        _write_json(payload)
    else:
        for check in checks:
            status = "ok" if check["ok"] else "failed"
            print(f"{status}: {check['name']} - {check['detail']}")
    return 0 if ok else 2


def _run_search(arguments: argparse.Namespace, provider: FlightProvider) -> int:
    try:
        query = FlightQuery(
            origin=arguments.origin,
            destination=arguments.destination,
            departure_date=arguments.departure,
            return_date=arguments.return_date,
            cabin=Cabin(arguments.cabin),
            max_stops=MaxStops.NON_STOP if arguments.nonstop else MaxStops.ANY,
            passengers=arguments.passengers,
            currency=arguments.currency,
            airlines=arguments.airlines,
            departure_window=arguments.departure_window,
        )
        offers = SearchService(provider).search(query)
    except ValueError as error:
        _write_json({"ok": False, "error": {"code": "invalid_request", "message": str(error)}})
        return 2
    except ProviderError as error:
        _write_json({"ok": False, "error": {"code": "provider_unavailable", "message": str(error)}})
        return 2

    if arguments.json_output:
        _write_json({"ok": True, "offers": [_offer_as_dict(offer) for offer in offers]})
    else:
        _write_human_offers(offers)
    return 0


def _run_dates(arguments: argparse.Namespace, provider: FlightProvider) -> int:
    try:
        query = FlexibleSearchQuery(
            origin=arguments.origin,
            destination=arguments.destination,
            start_date=arguments.start,
            end_date=arguments.end,
            min_nights=arguments.min_nights,
            max_nights=arguments.max_nights,
            cabin=Cabin(arguments.cabin),
            max_stops=MaxStops.NON_STOP if arguments.nonstop else MaxStops.ANY,
            passengers=arguments.passengers,
            currency=arguments.currency,
            airlines=arguments.airlines,
            departure_window=arguments.departure_window,
        )
        offers = FlexibleSearchService(provider).search(query)
    except ValueError as error:
        _write_json({"ok": False, "error": {"code": "invalid_request", "message": str(error)}})
        return 2
    except ProviderError as error:
        _write_json({"ok": False, "error": {"code": "provider_unavailable", "message": str(error)}})
        return 2

    if arguments.json_output:
        _write_json({"ok": True, "offers": [_flexible_offer_as_dict(offer) for offer in offers]})
    else:
        _write_human_date_offers(offers)
    return 0


def _run_watch(arguments: argparse.Namespace, repository: WatchRepository) -> int:
    try:
        if arguments.watch_command == "add":
            watch = _watch_from_arguments(arguments)
            repository.save(watch)
            _write_watch_result(arguments.json_output, watch, "Saved watch")
            return 0
        if arguments.watch_command == "list":
            watches = repository.list()
            if arguments.json_output:
                _write_json({"ok": True, "watches": [_watch_as_dict(watch) for watch in watches]})
            else:
                _write_human_watches(watches)
            return 0
        watch = repository.get(arguments.watch_id)
        if watch is None:
            _write_json(
                {
                    "ok": False,
                    "error": {"code": "watch_not_found", "message": "Flight watch was not found"},
                }
            )
            return 3
        if arguments.watch_command == "show":
            _write_watch_result(arguments.json_output, watch, "Flight watch")
            return 0
        if arguments.watch_command == "remove":
            repository.delete(watch.id)
            if arguments.json_output:
                _write_json({"ok": True, "removed_id": watch.id})
            else:
                print(f"Removed watch {watch.id}.")
            return 0
    except ValueError as error:
        _write_json({"ok": False, "error": {"code": "invalid_request", "message": str(error)}})
        return 2
    except StateCorruptError as error:
        _write_json({"ok": False, "error": {"code": "state_corrupt", "message": str(error)}})
        return 4
    raise AssertionError("Unhandled watch command")


def _run_watch_check(
    arguments: argparse.Namespace, provider: FlightProvider, repository: WatchRepository
) -> int:
    try:
        result = WatchCheckService(provider, repository).check()
    except ProviderError as error:
        _write_json({"ok": False, "error": {"code": "provider_unavailable", "message": str(error)}})
        return 2
    except StateCorruptError as error:
        _write_json({"ok": False, "error": {"code": "state_corrupt", "message": str(error)}})
        return 4
    payload: dict[str, object] = {
        "ok": True,
        "checked": result.checked,
        "alerts": [_deal_as_dict(item) for item in result.alerts],
    }
    if arguments.json_output:
        _write_json(payload)
    elif result.alerts:
        for item in result.alerts:
            print(f"{item.watch_id}: {item.currency} {item.price} ({', '.join(item.reasons)})")
    else:
        print("No new deals.")
    return 0


def _watch_from_arguments(arguments: argparse.Namespace) -> Watch:
    return Watch(
        id=arguments.watch_id or new_watch_id(arguments.origin, arguments.destination),
        origin=arguments.origin,
        destination=arguments.destination,
        start_date=arguments.start,
        end_date=arguments.end,
        min_nights=arguments.min_nights,
        max_nights=arguments.max_nights,
        cabin=Cabin(arguments.cabin),
        max_stops=MaxStops.NON_STOP if arguments.nonstop else MaxStops.ANY,
        passengers=arguments.passengers,
        currency=arguments.currency,
        airlines=arguments.airlines,
        departure_window=arguments.departure_window,
        target_price=arguments.target_price,
        drop_percent=arguments.drop_percent,
    )


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must use YYYY-MM-DD") from error


def _parse_airlines(value: str) -> tuple[str, ...]:
    return tuple(code for code in value.split(",") if code)


def _parse_departure_window(value: str) -> tuple[int, int]:
    try:
        start, end = (int(hour) for hour in value.split("-", maxsplit=1))
    except ValueError as error:
        raise argparse.ArgumentTypeError("must use START-END, for example 6-20") from error
    return start, end


def _parse_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except Exception as error:
        raise argparse.ArgumentTypeError("must be a decimal number") from error


def _add_watch_query_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from", dest="origin", required=True, metavar="IATA")
    parser.add_argument("--to", dest="destination", required=True, metavar="IATA")
    parser.add_argument("--start", required=True, type=_parse_date, metavar="YYYY-MM-DD")
    parser.add_argument("--end", required=True, type=_parse_date, metavar="YYYY-MM-DD")
    parser.add_argument("--min-nights", required=True, type=int)
    parser.add_argument("--max-nights", required=True, type=int)
    parser.add_argument("--cabin", choices=list(Cabin), default=Cabin.ECONOMY)
    parser.add_argument("--passengers", type=int, default=1)
    parser.add_argument("--currency", default="EUR")
    parser.add_argument("--nonstop", action="store_true")
    parser.add_argument("--airlines", type=_parse_airlines, default=())
    parser.add_argument("--departure-window", type=_parse_departure_window, metavar="START-END")


def _offer_as_dict(offer: FlightOffer) -> dict[str, object]:
    payload = asdict(offer)
    payload["price"] = str(offer.price) if offer.price is not None else None
    payload["airlines"] = list(offer.airlines)
    return payload


def _flexible_offer_as_dict(offer: FlexibleDateOffer) -> dict[str, object]:
    payload = asdict(offer)
    payload["price"] = str(offer.price)
    payload["nights"] = offer.nights
    return payload


def _watch_as_dict(watch: Watch) -> dict[str, object]:
    return {
        "id": watch.id,
        "origin": watch.origin,
        "destination": watch.destination,
        "start_date": watch.start_date.isoformat(),
        "end_date": watch.end_date.isoformat(),
        "min_nights": watch.min_nights,
        "max_nights": watch.max_nights,
        "cabin": watch.cabin.value,
        "max_stops": watch.max_stops.value,
        "passengers": watch.passengers,
        "currency": watch.currency,
        "airlines": list(watch.airlines),
        "departure_window": list(watch.departure_window) if watch.departure_window else None,
        "target_price": str(watch.target_price) if watch.target_price is not None else None,
        "drop_percent": str(watch.drop_percent) if watch.drop_percent is not None else None,
        "created_at": watch.created_at.isoformat(),
    }


def _deal_as_dict(deal: object) -> dict[str, object]:
    from hermes_flight_finder.models import Deal

    typed_deal = deal if isinstance(deal, Deal) else None
    if typed_deal is None:
        raise TypeError("Expected a deal")
    return {
        "watch_id": typed_deal.watch_id,
        "price": str(typed_deal.price),
        "currency": typed_deal.currency,
        "departure_date": typed_deal.departure_date.isoformat(),
        "return_date": typed_deal.return_date.isoformat(),
        "previous_best": str(typed_deal.previous_best)
        if typed_deal.previous_best is not None
        else None,
        "drop_percent": str(typed_deal.drop_percent)
        if typed_deal.drop_percent is not None
        else None,
        "reasons": list(typed_deal.reasons),
        "airlines": list(typed_deal.airlines),
        "stops": typed_deal.stops,
    }


def _write_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, default=_json_default, sort_keys=True))


def _json_default(value: object) -> str:
    if isinstance(value, (date, Decimal)):
        return value.isoformat() if isinstance(value, date) else str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _write_human_offers(offers: list[FlightOffer]) -> None:
    if not offers:
        print("No flights found.")
        return
    print("Best options\n")
    for index, offer in enumerate(offers, start=1):
        first_leg = offer.legs[0]
        last_leg = offer.legs[-1]
        price = (
            f"{offer.currency or ''} {offer.price}".strip() if offer.price else "Price unavailable"
        )
        stops = "Nonstop" if offer.stops == 0 else f"{offer.stops} stop(s)"
        print(f"{index}. {price} - {first_leg.departure_airport} -> {last_leg.arrival_airport}")
        print(f"   {first_leg.departure_at.date()} -> {last_leg.arrival_at.date()}")
        print(f"   {stops}; {', '.join(offer.airlines)}")


def _write_human_date_offers(offers: list[FlexibleDateOffer]) -> None:
    if not offers:
        print("No dates found.")
        return
    print("Best dates\n")
    for index, offer in enumerate(offers, start=1):
        price = f"{offer.currency or ''} {offer.price}".strip()
        print(f"{index}. {price} - {offer.departure_date} -> {offer.return_date}")
        print(f"   {offer.nights} night(s)")


def _write_watch_result(json_output: bool, watch: Watch, title: str) -> None:
    if json_output:
        _write_json({"ok": True, "watch": _watch_as_dict(watch)})
    else:
        print(f"{title}: {watch.id}")
        print(f"{watch.origin} -> {watch.destination}; {watch.start_date} to {watch.end_date}")
        print(f"{watch.min_nights}-{watch.max_nights} nights; {watch.currency}")


def _write_human_watches(watches: list[Watch]) -> None:
    if not watches:
        print("No flight watches saved.")
        return
    for watch in watches:
        print(f"{watch.id}: {watch.origin} -> {watch.destination}")
        print(
            f"  {watch.start_date} to {watch.end_date}; "
            f"{watch.min_nights}-{watch.max_nights} nights"
        )


if __name__ == "__main__":
    raise SystemExit(main())
