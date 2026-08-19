"""Command-line entry point for Hermes Flight Finder."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

from hermes_flight_finder.config import get_data_dir
from hermes_flight_finder.models import (
    BookingOption,
    Cabin,
    FlexibleDateOffer,
    FlexibleSearchQuery,
    FlightOffer,
    FlightQuery,
    MaxStops,
    PriceObservation,
    Watch,
    new_watch_id,
)
from hermes_flight_finder.providers import (
    BookingOptionsUnavailable,
    BookingProvider,
    FliFlightProvider,
    FlightProvider,
    ProviderError,
)
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

    booking = subcommands.add_parser("booking", help="Retrieve booking handoff links.")
    booking_subcommands = booking.add_subparsers(dest="booking_command", title="booking commands")
    booking_options = booking_subcommands.add_parser(
        "options", help="Retrieve current vendor links for a selected flight result."
    )
    _add_specific_query_arguments(booking_options)
    booking_options.add_argument("--offer", type=int, default=1, metavar="NUMBER")
    booking_options.add_argument("--json", action="store_true", dest="json_output")

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

    watch_history = watch_subcommands.add_parser("history", help="Show locally recorded prices.")
    watch_history.add_argument("watch_id")
    watch_history.add_argument("--json", action="store_true", dest="json_output")

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
    if arguments.command == "booking" and arguments.booking_command == "options":
        return _run_booking(arguments, provider or FliFlightProvider())
    if arguments.command == "doctor":
        return _run_doctor(
            arguments, provider or FliFlightProvider(), repository or JsonWatchRepository()
        )
    if arguments.command == "watch" and arguments.watch_command in {
        "add",
        "list",
        "show",
        "remove",
        "history",
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


def _run_booking(arguments: argparse.Namespace, provider: FlightProvider) -> int:
    """Return current provider links without opening a browser or purchasing anything."""
    booking_options_warning: str | None = None
    query: FlightQuery | None = None
    if not isinstance(provider, BookingProvider):
        _write_json(
            {
                "ok": False,
                "error": {
                    "code": "booking_not_supported",
                    "message": "The configured flight provider does not support booking handoffs",
                },
            }
        )
        return 2
    try:
        if arguments.offer < 1:
            raise ValueError("offer number must be at least 1")
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
        selected_offer, options = provider.booking_options(query, arguments.offer - 1)
    except ValueError as error:
        _write_json({"ok": False, "error": {"code": "invalid_request", "message": str(error)}})
        return 2
    except BookingOptionsUnavailable as error:
        selected_offer = error.selected_offer
        options = []
        booking_options_warning = str(error)
    except ProviderError as error:
        _write_json({"ok": False, "error": {"code": "provider_unavailable", "message": str(error)}})
        return 2

    assert query is not None
    google_flights_search_url = _google_flights_search_url(query)
    booking_handoff_url = selected_offer.booking_url or google_flights_search_url
    payload: dict[str, object] = {
        "ok": True,
        "selected_offer": _offer_as_dict(selected_offer),
        "booking_handoff_url": booking_handoff_url,
        "google_flights_search_url": google_flights_search_url,
        "booking_options": [_booking_option_as_dict(option) for option in options],
    }
    if booking_options_warning:
        payload["booking_options_warning"] = booking_options_warning
    if arguments.json_output:
        _write_json(payload)
    else:
        _write_human_booking_options(
            options,
            booking_handoff_url,
            google_flights_search_url,
            booking_options_warning,
        )
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
        if arguments.watch_command == "history":
            return _run_watch_history(arguments, watch, repository.list_observations(watch.id))
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


def _run_watch_history(
    arguments: argparse.Namespace, watch: Watch, observations: list[PriceObservation]
) -> int:
    """Render local price observations without contacting a provider."""
    ordered = sorted(observations, key=lambda item: item.checked_at)
    payload: dict[str, object] = {
        "ok": True,
        "watch": _watch_as_dict(watch),
        "summary": _history_summary(ordered),
        "observations": [_observation_as_dict(item) for item in ordered],
    }
    if arguments.json_output:
        _write_json(payload)
    else:
        _write_human_history(watch, ordered)
    return 0


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


def _add_specific_query_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from", dest="origin", required=True, metavar="IATA")
    parser.add_argument("--to", dest="destination", required=True, metavar="IATA")
    parser.add_argument("--departure", required=True, type=_parse_date, metavar="YYYY-MM-DD")
    parser.add_argument("--return", dest="return_date", type=_parse_date, metavar="YYYY-MM-DD")
    parser.add_argument("--cabin", choices=list(Cabin), default=Cabin.ECONOMY)
    parser.add_argument("--passengers", type=int, default=1)
    parser.add_argument("--currency", default="EUR")
    parser.add_argument("--nonstop", action="store_true")
    parser.add_argument("--airlines", type=_parse_airlines, default=())
    parser.add_argument("--departure-window", type=_parse_departure_window, metavar="START-END")


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


def _google_flights_search_url(query: FlightQuery) -> str:
    search_text = (
        f"Flights to {query.destination} from {query.origin} on {query.departure_date.isoformat()}"
    )
    if query.return_date is not None:
        search_text += f" returning {query.return_date.isoformat()}"
    return "https://www.google.com/travel/flights?" + urlencode(
        {"hl": "en", "curr": query.currency, "q": search_text}
    )


def _booking_option_as_dict(option: BookingOption) -> dict[str, object]:
    return {
        "vendor_name": option.vendor_name,
        "is_airline_direct": option.is_airline_direct,
        "price": str(option.price) if option.price is not None else None,
        "currency": option.currency,
        "fare_name": option.fare_name,
        "booking_url": option.booking_url,
        "google_click_url": option.google_click_url,
        "handoff_url": option.handoff_url,
    }


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


def _observation_as_dict(observation: PriceObservation) -> dict[str, object]:
    return {
        "checked_at": observation.checked_at.isoformat(),
        "price": str(observation.price),
        "currency": observation.currency,
        "departure_date": observation.departure_date.isoformat(),
        "return_date": observation.return_date.isoformat(),
        "airlines": list(observation.airlines),
        "stops": observation.stops,
        "source": observation.source,
    }


def _history_summary(observations: list[PriceObservation]) -> dict[str, object]:
    if not observations:
        return {
            "observation_count": 0,
            "tracking_started_at": None,
            "latest_price": None,
            "lowest_price": None,
            "lowest_observed_at": None,
            "latest_is_lowest_since_tracking_started": None,
            "sources": [],
        }
    latest = observations[-1]
    lowest = min(observations, key=lambda item: item.price)
    return {
        "observation_count": len(observations),
        "tracking_started_at": observations[0].checked_at,
        "latest_price": str(latest.price),
        "currency": latest.currency,
        "lowest_price": str(lowest.price),
        "lowest_observed_at": lowest.checked_at,
        "latest_is_lowest_since_tracking_started": latest.price == lowest.price,
        "sources": sorted({item.source for item in observations}),
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


def _write_human_booking_options(
    options: list[BookingOption],
    booking_handoff_url: str,
    google_flights_search_url: str,
    booking_options_warning: str | None,
) -> None:
    print(f"Selected itinerary: {booking_handoff_url}")
    if booking_options_warning:
        print(f"Warning: {booking_options_warning}")
    if not options:
        print("No direct booking links are currently available for this offer.")
    for index, option in enumerate(options, start=1):
        vendor = option.vendor_name or "Unknown vendor"
        direct = "airline direct" if option.is_airline_direct else "travel seller"
        price = (
            f"{option.currency or ''} {option.price}".strip()
            if option.price
            else "Price unavailable"
        )
        print(f"{index}. {vendor} ({direct}) - {price}")
        if option.fare_name:
            print(f"   Fare: {option.fare_name}")
        if option.handoff_url:
            print(f"   {option.handoff_url}")
    if booking_handoff_url != google_flights_search_url:
        print(f"Google Flights search fallback: {google_flights_search_url}")


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
        if offer.booking_url:
            print(f"   Book: {offer.booking_url}")


def _write_human_date_offers(offers: list[FlexibleDateOffer]) -> None:
    if not offers:
        print("No dates found.")
        return
    print("Best dates\n")
    for index, offer in enumerate(offers, start=1):
        price = f"{offer.currency or ''} {offer.price}".strip()
        print(f"{index}. {price} - {offer.departure_date} -> {offer.return_date}")
        print(f"   {offer.nights} night(s)")
        if offer.booking_url:
            print(f"   Link: {offer.booking_url}")


def _write_watch_result(json_output: bool, watch: Watch, title: str) -> None:
    if json_output:
        _write_json({"ok": True, "watch": _watch_as_dict(watch)})
    else:
        print(f"{title}: {watch.id}")
        print(f"{watch.origin} -> {watch.destination}; {watch.start_date} to {watch.end_date}")
        print(f"{watch.min_nights}-{watch.max_nights} nights; {watch.currency}")


def _write_human_history(watch: Watch, observations: list[PriceObservation]) -> None:
    if not observations:
        print(f"No price observations recorded for {watch.id}.")
        return
    latest = observations[-1]
    lowest = min(observations, key=lambda item: item.price)
    sources = ", ".join(sorted({item.source for item in observations}))
    print(f"History for {watch.id}\n")
    print(
        "Latest: "
        f"{latest.currency} {latest.price} ({latest.departure_date} to {latest.return_date})"
    )
    print(
        f"Lowest since tracking started: {lowest.currency} {lowest.price} "
        f"({lowest.departure_date} to {lowest.return_date})"
    )
    print(f"Observations: {len(observations)}; sources: {sources}")


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
