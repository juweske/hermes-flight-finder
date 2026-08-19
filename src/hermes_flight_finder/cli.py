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
    BookingStrategy,
    Cabin,
    ConnectionPolicy,
    FlexibleDateOffer,
    FlexibleSearchQuery,
    FlightOffer,
    FlightQuery,
    MaxStops,
    PriceObservation,
    QualityPolicy,
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
from hermes_flight_finder.quality import (
    AssessedDateCandidate,
    AssessedOffer,
    assess_and_rank_offers,
    assess_offer,
    rank_date_candidates,
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
    search.add_argument("--return-from", metavar="IATA[,IATA]")
    search.add_argument("--return-to", metavar="IATA[,IATA]")
    search.add_argument("--cabin", choices=list(Cabin), default=Cabin.ECONOMY)
    search.add_argument("--passengers", type=int, default=1)
    search.add_argument("--currency", default="EUR")
    search.add_argument("--nonstop", action="store_true")
    search.add_argument("--max-stops", choices=("0", "1", "2", "any"), default="any")
    search.add_argument("--airlines", type=_parse_airlines, default=())
    search.add_argument("--departure-window", type=_parse_departure_window, metavar="START-END")
    _add_quality_arguments(search)
    search.add_argument("--json", action="store_true", dest="json_output")

    dates = subcommands.add_parser("dates", help="Search flexible travel dates.")
    dates.add_argument("--from", dest="origin", required=True, metavar="IATA")
    dates.add_argument("--to", dest="destination", required=True, metavar="IATA")
    dates.add_argument("--start", required=True, type=_parse_date, metavar="YYYY-MM-DD")
    dates.add_argument("--end", required=True, type=_parse_date, metavar="YYYY-MM-DD")
    dates.add_argument("--min-nights", required=True, type=int)
    dates.add_argument("--max-nights", required=True, type=int)
    dates.add_argument("--return-from", metavar="IATA[,IATA]")
    dates.add_argument("--return-to", metavar="IATA[,IATA]")
    dates.add_argument("--cabin", choices=list(Cabin), default=Cabin.ECONOMY)
    dates.add_argument("--passengers", type=int, default=1)
    dates.add_argument("--currency", default="EUR")
    dates.add_argument("--nonstop", action="store_true")
    dates.add_argument("--max-stops", choices=("0", "1", "2", "any"), default="any")
    dates.add_argument("--airlines", type=_parse_airlines, default=())
    dates.add_argument("--departure-window", type=_parse_departure_window, metavar="START-END")
    _add_quality_arguments(dates)
    dates.add_argument("--quality-candidates", type=_positive_int, default=5, metavar="N")
    dates.add_argument("--json", action="store_true", dest="json_output")

    booking = subcommands.add_parser("booking", help="Retrieve booking handoff links.")
    booking_subcommands = booking.add_subparsers(dest="booking_command", title="booking commands")
    booking_options = booking_subcommands.add_parser(
        "options", help="Retrieve current vendor links for a selected flight result."
    )
    _add_specific_query_arguments(booking_options)
    _add_quality_arguments(booking_options)
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
    _add_quality_arguments(watch_check)
    watch_check.add_argument("--quality-candidates", type=_positive_int, default=3, metavar="N")
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
        query = _flight_query_from_arguments(arguments)
        offers = SearchService(provider).search(query)
        policy = _quality_policy_from_arguments(arguments)
    except ValueError as error:
        _write_json({"ok": False, "error": {"code": "invalid_request", "message": str(error)}})
        return 2
    except ProviderError as error:
        _write_json({"ok": False, "error": {"code": "provider_unavailable", "message": str(error)}})
        return 2

    if arguments.json_output:
        assessed_offers = assess_and_rank_offers(offers, policy)
        _write_json(
            {
                "ok": True,
                "offers": [
                    _assessed_offer_as_dict(assessment, offers.index(assessment.offer) + 1)
                    for assessment in assessed_offers
                ],
            }
        )
    else:
        _write_human_offers(offers)
    return 0


def _run_booking(arguments: argparse.Namespace, provider: FlightProvider) -> int:
    """Return current provider links without opening a browser or purchasing anything."""
    booking_options_warning: str | None = None
    query: FlightQuery | None = None
    selected_offer: FlightOffer
    options: list[BookingOption]
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
        offer_number = int(arguments.offer)
        if offer_number < 1:
            raise ValueError("offer number must be at least 1")
        query = _flight_query_from_arguments(arguments)
        selected_offer, options = provider.booking_options(query, offer_number - 1)
        policy = _quality_policy_from_arguments(arguments)
    except ValueError as error:
        _write_json({"ok": False, "error": {"code": "invalid_request", "message": str(error)}})
        return 2
    except BookingOptionsUnavailable as error:
        selected_offer = error.selected_offer
        options = []
        booking_options_warning = str(error)
        policy = _quality_policy_from_arguments(arguments)
    except ProviderError as error:
        assert query is not None
        google_flights_search_url = _google_flights_search_url(query)
        payload: dict[str, object] = {
            "ok": True,
            "selected_offer": None,
            "booking_handoff_url": google_flights_search_url,
            "booking_handoff_link_markdown": _markdown_link(google_flights_search_url),
            "booking_handoff_urls": [],
            "booking_handoff_links_markdown": [],
            "google_flights_search_url": google_flights_search_url,
            "booking_options": [],
            "booking_options_warning": str(error),
            "booking_refresh_failed": True,
        }
        if arguments.json_output:
            _write_json(payload)
        else:
            _write_human_booking_options(
                [], google_flights_search_url, google_flights_search_url, str(error)
            )
        return 0

    assert query is not None
    google_flights_search_url = _google_flights_search_url(query)
    is_separate_ticket = selected_offer.booking_strategy == BookingStrategy.SEPARATE_TICKETS
    separate_handoffs = [url for url in selected_offer.component_booking_urls if url]
    booking_handoff_url = (
        None if is_separate_ticket else selected_offer.booking_url or google_flights_search_url
    )
    payload: dict[str, object] = {
        "ok": True,
        "selected_offer": _assessed_offer_as_dict(assess_offer(selected_offer, policy)),
        "booking_handoff_url": booking_handoff_url,
        "booking_handoff_link_markdown": _markdown_link(booking_handoff_url),
        "booking_handoff_urls": separate_handoffs,
        "booking_handoff_links_markdown": [
            _markdown_link(url, f"Open ticket {index}")
            for index, url in enumerate(separate_handoffs, start=1)
        ],
        "google_flights_search_url": google_flights_search_url,
        "booking_options": [_booking_option_as_dict(option) for option in options],
    }
    if booking_options_warning:
        payload["booking_options_warning"] = booking_options_warning
    if arguments.json_output:
        _write_json(payload)
    else:
        if is_separate_ticket:
            print(f"Warning: {booking_options_warning}")
            if separate_handoffs:
                for index, url in enumerate(separate_handoffs, start=1):
                    print(f"Ticket {index}: {url}")
            else:
                print("No exact separate-ticket handoffs are currently available.")
        else:
            assert booking_handoff_url is not None
            _write_human_booking_options(
                options,
                booking_handoff_url,
                google_flights_search_url,
                booking_options_warning,
            )
    return 0


def _run_dates(arguments: argparse.Namespace, provider: FlightProvider) -> int:
    try:
        query = _flexible_query_from_arguments(arguments)
        offers = FlexibleSearchService(provider).search(query)
        policy = _quality_policy_from_arguments(arguments)
        quality_candidates = _evaluate_date_candidates(
            provider, query, offers[: arguments.quality_candidates], policy
        )
    except ValueError as error:
        _write_json({"ok": False, "error": {"code": "invalid_request", "message": str(error)}})
        return 2
    except ProviderError as error:
        _write_json({"ok": False, "error": {"code": "provider_unavailable", "message": str(error)}})
        return 2

    if arguments.json_output:
        _write_json(
            {
                "ok": True,
                "offers": [_flexible_offer_as_dict(offer) for offer in offers],
                "quality_candidates": [
                    _date_candidate_as_dict(candidate) for candidate in quality_candidates
                ],
                "recommended_quality_candidate": _recommended_date_candidate(quality_candidates),
            }
        )
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
        result = WatchCheckService(
            provider,
            repository,
            quality_policy=_quality_policy_from_arguments(arguments),
            quality_candidates=arguments.quality_candidates,
        ).check()
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
    origins = _airport_group(arguments.origin)
    destinations = _airport_group(arguments.destination)
    return Watch(
        id=arguments.watch_id or new_watch_id(origins[0], destinations[0]),
        origin=origins[0],
        destination=destinations[0],
        start_date=arguments.start,
        end_date=arguments.end,
        min_nights=arguments.min_nights,
        max_nights=arguments.max_nights,
        cabin=Cabin(arguments.cabin),
        max_stops=_max_stops_from_arguments(arguments),
        passengers=arguments.passengers,
        currency=arguments.currency,
        airlines=arguments.airlines,
        departure_window=arguments.departure_window,
        origin_alternatives=origins[1:],
        destination_alternatives=destinations[1:],
        return_origins=_airport_group(arguments.return_from) if arguments.return_from else (),
        return_destinations=_airport_group(arguments.return_to) if arguments.return_to else (),
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


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _parse_duration(value: str) -> int:
    """Parse a user-facing duration and return whole minutes."""
    normalized = value.strip().lower().replace(" ", "")
    try:
        if normalized.endswith("m") and "h" not in normalized:
            minutes = int(normalized[:-1])
        elif "h" in normalized:
            hours_text, minutes_text = normalized.split("h", maxsplit=1)
            hours = Decimal(hours_text or "0")
            trailing_minutes = int(minutes_text.removesuffix("m") or "0")
            minutes = int(hours * 60) + trailing_minutes
        else:
            minutes = int(Decimal(normalized) * 60)
    except (ArithmeticError, ValueError) as error:
        raise argparse.ArgumentTypeError(
            "must use hours such as 4h, 2.5h, or 2h 30m; plain numbers mean hours"
        ) from error
    if minutes < 0:
        raise argparse.ArgumentTypeError("duration must not be negative")
    return minutes


def _add_quality_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--acceptable-layover",
        type=_parse_duration,
        default=240,
        metavar="DURATION",
        help="Longest comfortable layover, for example 4h or 2h 30m.",
    )
    parser.add_argument(
        "--airport-changes",
        choices=list(ConnectionPolicy),
        default=ConnectionPolicy.AVOID,
    )
    parser.add_argument(
        "--overnight-layovers",
        choices=list(ConnectionPolicy),
        default=ConnectionPolicy.AVOID,
    )
    parser.add_argument(
        "--self-transfers",
        choices=list(ConnectionPolicy),
        default=ConnectionPolicy.AVOID,
    )


def _quality_policy_from_arguments(arguments: argparse.Namespace) -> QualityPolicy:
    return QualityPolicy(
        acceptable_layover_minutes=arguments.acceptable_layover,
        airport_change=ConnectionPolicy(arguments.airport_changes),
        overnight_layover=ConnectionPolicy(arguments.overnight_layovers),
        self_transfer=ConnectionPolicy(arguments.self_transfers),
    )


def _airport_group(value: str) -> tuple[str, ...]:
    airports = tuple(item.strip().upper() for item in value.split(",") if item.strip())
    if not airports:
        raise ValueError("airport groups must contain at least one IATA code")
    return airports


def _flight_query_from_arguments(arguments: argparse.Namespace) -> FlightQuery:
    origins = _airport_group(arguments.origin)
    destinations = _airport_group(arguments.destination)
    return_origins = _airport_group(arguments.return_from) if arguments.return_from else ()
    return_destinations = _airport_group(arguments.return_to) if arguments.return_to else ()
    return FlightQuery(
        origin=origins[0],
        destination=destinations[0],
        departure_date=arguments.departure,
        return_date=arguments.return_date,
        cabin=Cabin(arguments.cabin),
        max_stops=_max_stops_from_arguments(arguments),
        passengers=arguments.passengers,
        currency=arguments.currency,
        airlines=arguments.airlines,
        departure_window=arguments.departure_window,
        origin_alternatives=origins[1:],
        destination_alternatives=destinations[1:],
        return_origins=return_origins,
        return_destinations=return_destinations,
    )


def _flexible_query_from_arguments(arguments: argparse.Namespace) -> FlexibleSearchQuery:
    origins = _airport_group(arguments.origin)
    destinations = _airport_group(arguments.destination)
    return_origins = _airport_group(arguments.return_from) if arguments.return_from else ()
    return_destinations = _airport_group(arguments.return_to) if arguments.return_to else ()
    return FlexibleSearchQuery(
        origin=origins[0],
        destination=destinations[0],
        start_date=arguments.start,
        end_date=arguments.end,
        min_nights=arguments.min_nights,
        max_nights=arguments.max_nights,
        cabin=Cabin(arguments.cabin),
        max_stops=_max_stops_from_arguments(arguments),
        passengers=arguments.passengers,
        currency=arguments.currency,
        airlines=arguments.airlines,
        departure_window=arguments.departure_window,
        origin_alternatives=origins[1:],
        destination_alternatives=destinations[1:],
        return_origins=return_origins,
        return_destinations=return_destinations,
    )


def _max_stops_from_arguments(arguments: argparse.Namespace) -> MaxStops:
    if arguments.nonstop or arguments.max_stops == "0":
        return MaxStops.NON_STOP
    return {
        "1": MaxStops.ONE_STOP_OR_FEWER,
        "2": MaxStops.TWO_OR_FEWER_STOPS,
        "any": MaxStops.ANY,
    }[arguments.max_stops]


def _add_specific_query_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from", dest="origin", required=True, metavar="IATA")
    parser.add_argument("--to", dest="destination", required=True, metavar="IATA")
    parser.add_argument("--departure", required=True, type=_parse_date, metavar="YYYY-MM-DD")
    parser.add_argument("--return", dest="return_date", type=_parse_date, metavar="YYYY-MM-DD")
    parser.add_argument("--return-from", metavar="IATA[,IATA]")
    parser.add_argument("--return-to", metavar="IATA[,IATA]")
    parser.add_argument("--cabin", choices=list(Cabin), default=Cabin.ECONOMY)
    parser.add_argument("--passengers", type=int, default=1)
    parser.add_argument("--currency", default="EUR")
    parser.add_argument("--nonstop", action="store_true")
    parser.add_argument("--max-stops", choices=("0", "1", "2", "any"), default="any")
    parser.add_argument("--airlines", type=_parse_airlines, default=())
    parser.add_argument("--departure-window", type=_parse_departure_window, metavar="START-END")


def _add_watch_query_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from", dest="origin", required=True, metavar="IATA")
    parser.add_argument("--to", dest="destination", required=True, metavar="IATA")
    parser.add_argument("--start", required=True, type=_parse_date, metavar="YYYY-MM-DD")
    parser.add_argument("--end", required=True, type=_parse_date, metavar="YYYY-MM-DD")
    parser.add_argument("--min-nights", required=True, type=int)
    parser.add_argument("--max-nights", required=True, type=int)
    parser.add_argument("--return-from", metavar="IATA[,IATA]")
    parser.add_argument("--return-to", metavar="IATA[,IATA]")
    parser.add_argument("--cabin", choices=list(Cabin), default=Cabin.ECONOMY)
    parser.add_argument("--passengers", type=int, default=1)
    parser.add_argument("--currency", default="EUR")
    parser.add_argument("--nonstop", action="store_true")
    parser.add_argument("--max-stops", choices=("0", "1", "2", "any"), default="any")
    parser.add_argument("--airlines", type=_parse_airlines, default=())
    parser.add_argument("--departure-window", type=_parse_departure_window, metavar="START-END")


def _offer_as_dict(offer: FlightOffer) -> dict[str, object]:
    payload = asdict(offer)
    payload["price"] = str(offer.price) if offer.price is not None else None
    payload["airlines"] = list(offer.airlines)
    payload["booking_strategy"] = offer.booking_strategy.value
    payload["component_prices"] = [
        str(price) if price is not None else None for price in offer.component_prices
    ]
    payload["component_booking_urls"] = list(offer.component_booking_urls)
    payload["booking_link_markdown"] = _markdown_link(offer.booking_url)
    payload["component_booking_links_markdown"] = [
        _markdown_link(url, f"Open ticket {index}")
        for index, url in enumerate(offer.component_booking_urls, start=1)
        if url
    ]
    return payload


def _assessed_offer_as_dict(
    assessment: AssessedOffer, offer_number: int | None = None
) -> dict[str, object]:
    payload = _offer_as_dict(assessment.offer)
    if offer_number is not None:
        payload["offer_number"] = offer_number
    payload["quality_status"] = assessment.status.value
    payload["warnings"] = [_warning_as_dict(item) for item in assessment.warnings]
    return payload


def _evaluate_date_candidates(
    provider: FlightProvider,
    query: FlexibleSearchQuery,
    date_offers: list[FlexibleDateOffer],
    policy: QualityPolicy,
) -> list[AssessedDateCandidate]:
    candidates: list[AssessedDateCandidate] = []
    service = SearchService(provider)
    for date_offer in date_offers:
        exact_query = FlightQuery(
            origin=query.origin,
            destination=query.destination,
            departure_date=date_offer.departure_date,
            return_date=date_offer.return_date,
            cabin=query.cabin,
            max_stops=query.max_stops,
            passengers=query.passengers,
            currency=query.currency,
            airlines=query.airlines,
            departure_window=query.departure_window,
            origin_alternatives=query.origin_alternatives,
            destination_alternatives=query.destination_alternatives,
            return_origins=query.return_origins,
            return_destinations=query.return_destinations,
        )
        offers = service.search(exact_query)
        ranked = assess_and_rank_offers(offers, policy)
        recommended = ranked[0] if ranked else None
        displayed = ranked[:5]
        candidates.append(
            AssessedDateCandidate(
                date_offer=date_offer,
                offers=tuple(displayed),
                offer_numbers=tuple(offers.index(item.offer) + 1 for item in displayed),
                recommended_offer=recommended,
                recommended_offer_number=(offers.index(recommended.offer) + 1)
                if recommended is not None
                else None,
            )
        )
    return candidates


def _date_candidate_as_dict(candidate: AssessedDateCandidate) -> dict[str, object]:
    return {
        "date_offer": _flexible_offer_as_dict(candidate.date_offer),
        "offers": [
            _assessed_offer_as_dict(item, offer_number)
            for item, offer_number in zip(candidate.offers, candidate.offer_numbers, strict=True)
        ],
        "recommended_offer_number": candidate.recommended_offer_number,
        "recommended_offer": (
            _assessed_offer_as_dict(candidate.recommended_offer, candidate.recommended_offer_number)
            if candidate.recommended_offer is not None
            else None
        ),
    }


def _recommended_date_candidate(
    candidates: list[AssessedDateCandidate],
) -> dict[str, object] | None:
    ranked = rank_date_candidates(candidates)
    return _date_candidate_as_dict(ranked[0]) if ranked else None


def _warning_as_dict(warning: object) -> dict[str, object]:
    from hermes_flight_finder.models import ItineraryWarning

    if not isinstance(warning, ItineraryWarning):
        raise TypeError("Expected an itinerary warning")
    payload = asdict(warning)
    payload["severity"] = warning.severity.value
    return payload


def _google_flights_search_url(query: FlightQuery) -> str:
    if (
        len(query.outbound_origins) == 1
        and len(query.outbound_destinations) == 1
        and not query.is_open_jaw
    ):
        search_text = (
            f"Flights to {query.destination} from {query.origin} "
            f"on {query.departure_date.isoformat()}"
        )
        if query.return_date is not None:
            search_text += f" returning {query.return_date.isoformat()}"
        return "https://www.google.com/travel/flights?" + urlencode(
            {"hl": "en", "curr": query.currency, "q": search_text}
        )
    origins = ",".join(query.outbound_origins)
    destinations = ",".join(query.outbound_destinations)
    search_text = f"Flights from {origins} to {destinations} on {query.departure_date.isoformat()}"
    if query.return_date is not None:
        return_origins = ",".join(query.inbound_origins)
        return_destinations = ",".join(query.inbound_destinations)
        search_text += (
            f" then from {return_origins} to {return_destinations} "
            f"on {query.return_date.isoformat()}"
        )
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
        "handoff_link_markdown": _markdown_link(option.handoff_url),
    }


def _flexible_offer_as_dict(offer: FlexibleDateOffer) -> dict[str, object]:
    payload = asdict(offer)
    payload["price"] = str(offer.price)
    payload["nights"] = offer.nights
    payload["booking_link_markdown"] = _markdown_link(offer.booking_url)
    return payload


def _markdown_link(url: str | None, label: str = "Open") -> str | None:
    """Return a ready-to-render link so agents never need to transcribe long URLs."""
    return f"[{label}]({url})" if url else None


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
        "origin_alternatives": list(watch.origin_alternatives),
        "destination_alternatives": list(watch.destination_alternatives),
        "return_origins": list(watch.return_origins),
        "return_destinations": list(watch.return_destinations),
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
        "quality_status": observation.quality_status.value,
        "warnings": [_warning_as_dict(item) for item in observation.warnings],
        "booking_strategy": observation.booking_strategy.value,
        "booking_warning": observation.booking_warning,
        "routes": [
            {"origin": origin, "destination": destination}
            for origin, destination in observation.routes
        ],
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
        "quality_status": typed_deal.quality_status.value,
        "warnings": [_warning_as_dict(item) for item in typed_deal.warnings],
        "booking_strategy": typed_deal.booking_strategy.value,
        "booking_warning": typed_deal.booking_warning,
        "routes": [
            {"origin": origin, "destination": destination}
            for origin, destination in typed_deal.routes
        ],
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
