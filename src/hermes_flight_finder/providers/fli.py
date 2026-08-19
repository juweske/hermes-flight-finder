"""Adapter from the `fli` package to Hermes Flight Finder domain models."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol, cast
from urllib.parse import parse_qs, quote, urlsplit

from fli.core import google_flights_url
from fli.models import (
    Airline,
    Airport,
    DateSearchFilters,
    FlightSearchFilters,
    FlightSegment,
    PassengerInfo,
    SeatType,
    SortBy,
    TimeRestrictions,
    TripType,
)
from fli.models import (
    BookingOption as FliBookingOption,
)
from fli.models import (
    FlightLeg as FliFlightLeg,
)
from fli.models import (
    FlightResult as FliFlightResult,
)
from fli.models import Layover as FliLayover
from fli.models import MaxStops as FliMaxStops
from fli.search import DatePrice, SearchDates, SearchFlights

from hermes_flight_finder.models import (
    BookingOption,
    FlexibleDateOffer,
    FlexibleSearchQuery,
    FlightJourney,
    FlightLayover,
    FlightLeg,
    FlightOffer,
    FlightQuery,
)
from hermes_flight_finder.providers.base import BookingOptionsUnavailable, ProviderError
from hermes_flight_finder.providers.date_cache import DateSearchCache


class _SearchClient(Protocol):
    def search(
        self,
        filters: FlightSearchFilters,
        top_n: int = 5,
        currency: str | None = None,
        language: str | None = None,
        country: str | None = None,
    ) -> object: ...

    def get_booking_options(
        self,
        flight: FliFlightResult | tuple[FliFlightResult, ...],
        filters: FlightSearchFilters,
        currency: str | None = None,
    ) -> object: ...

    def build_flight_booking_url(
        self,
        flight: FliFlightResult | tuple[FliFlightResult, ...],
        *,
        currency: str | None = None,
        language: str | None = None,
        country: str | None = None,
    ) -> str: ...


class _DateSearchClient(Protocol):
    def search(
        self,
        filters: DateSearchFilters,
        currency: str | None = None,
        language: str | None = None,
        country: str | None = None,
    ) -> object: ...


class FliFlightProvider:
    """Search Google Flights through the direct Python API exposed by `fli`."""

    def __init__(
        self,
        search_factory: Callable[[], object] | None = None,
        date_search_factory: Callable[[], object] | None = None,
        date_cache: DateSearchCache | None = None,
    ) -> None:
        self._search_factory = search_factory or SearchFlights
        self._date_search_factory = date_search_factory or SearchDates
        self._date_cache = date_cache or (
            DateSearchCache() if date_search_factory is None else None
        )

    def search(self, query: FlightQuery) -> list[FlightOffer]:
        """Map a domain query to `fli`, then normalize its response."""
        try:
            filters = self._build_filters(query)
            client = cast(_SearchClient, self._search_factory())
            raw_results = client.search(filters, currency=query.currency)
        except Exception as error:
            raise ProviderError("Flight provider request failed") from error

        if raw_results is None:
            return []
        if not isinstance(raw_results, list):
            raise ProviderError("Flight provider returned an unexpected response")
        results = cast(list[FliFlightResult | tuple[FliFlightResult, ...]], raw_results)
        return [
            self._normalize_itinerary(
                result,
                booking_url=_itinerary_booking_url(client, result, query.currency),
            )
            for result in results
        ]

    def booking_options(
        self, query: FlightQuery, offer_index: int
    ) -> tuple[FlightOffer, list[BookingOption]]:
        """Return current vendor handoffs for one ranked result in a fresh search."""
        try:
            filters = self._build_filters(query)
            client = cast(_SearchClient, self._search_factory())
            raw_results = client.search(filters, currency=query.currency)
        except Exception as error:
            raise ProviderError("Flight provider request failed") from error

        if raw_results is None:
            raise ProviderError("Flight provider found no flight offers to book")
        if not isinstance(raw_results, list):
            raise ProviderError("Flight provider returned an unexpected response")
        ranked = sorted(
            (
                (
                    raw,
                    self._normalize_itinerary(
                        raw,
                        booking_url=_itinerary_booking_url(client, raw, query.currency),
                    ),
                )
                for raw in cast(list[FliFlightResult | tuple[FliFlightResult, ...]], raw_results)
            ),
            key=lambda item: _offer_sort_key(item[1]),
        )
        if offer_index < 0 or offer_index >= len(ranked):
            raise ValueError(f"offer index must be between 1 and {len(ranked)}")

        raw_offer, selected_offer = ranked[offer_index]
        try:
            raw_options = client.get_booking_options(raw_offer, filters, currency=query.currency)
        except Exception as error:
            if selected_offer.booking_url:
                raise BookingOptionsUnavailable(
                    "Vendor booking options are temporarily unavailable", selected_offer
                ) from error
            raise ProviderError("Flight provider could not retrieve booking options") from error
        if not isinstance(raw_options, list):
            if selected_offer.booking_url:
                raise BookingOptionsUnavailable(
                    "Vendor booking options returned an unexpected response", selected_offer
                )
            raise ProviderError("Flight provider returned unexpected booking options")
        return selected_offer, [
            self._normalize_booking_option(option)
            for option in cast(list[FliBookingOption], raw_options)
            if option.booking_url or option.google_click_url
        ]

    def search_dates(self, query: FlexibleSearchQuery) -> list[FlexibleDateOffer]:
        """Search every requested trip duration through `fli`'s calendar API."""
        cached = self._date_cache.get(query) if self._date_cache else None
        if cached is not None:
            return cached
        client = cast(_DateSearchClient, self._date_search_factory())
        offers: list[FlexibleDateOffer]
        if query.is_open_jaw:
            offers = self._search_open_jaw_dates(client, query)
        else:
            offers = []
            for nights in range(query.min_nights, query.max_nights + 1):
                try:
                    raw_results = client.search(
                        self._build_date_filters(query, nights),
                        currency=query.currency,
                    )
                except Exception as error:
                    raise ProviderError("Flight provider request failed") from error
                if raw_results is None:
                    continue
                if not isinstance(raw_results, list):
                    raise ProviderError("Flight provider returned an unexpected response")
                results = cast(list[DatePrice], raw_results)
                offers.extend(self._normalize_date_price(result, query) for result in results)
        if self._date_cache:
            self._date_cache.put(query, offers)
        return offers

    def _search_open_jaw_dates(
        self, client: _DateSearchClient, query: FlexibleSearchQuery
    ) -> list[FlexibleDateOffer]:
        try:
            outbound_raw = client.search(
                self._build_one_way_date_filters(
                    query,
                    query.outbound_origins,
                    query.outbound_destinations,
                    query.start_date,
                    query.end_date,
                ),
                currency=query.currency,
            )
            inbound_raw = client.search(
                self._build_one_way_date_filters(
                    query,
                    query.inbound_origins,
                    query.inbound_destinations,
                    query.start_date + timedelta(days=query.min_nights),
                    query.end_date + timedelta(days=query.max_nights),
                ),
                currency=query.currency,
            )
        except Exception as error:
            raise ProviderError("Flight provider request failed") from error
        outbound = _one_way_date_prices(outbound_raw)
        inbound = _one_way_date_prices(inbound_raw)
        offers: list[FlexibleDateOffer] = []
        for departure_date, (outbound_price, outbound_currency) in outbound.items():
            for return_date, (inbound_price, inbound_currency) in inbound.items():
                nights = (return_date - departure_date).days
                if not query.min_nights <= nights <= query.max_nights:
                    continue
                currency = (
                    outbound_currency if outbound_currency == inbound_currency else query.currency
                )
                offers.append(
                    FlexibleDateOffer(
                        departure_date=departure_date,
                        return_date=return_date,
                        price=outbound_price + inbound_price,
                        currency=currency,
                        booking_url=_multi_city_search_url(query, departure_date, return_date),
                    )
                )
        return offers

    @staticmethod
    def _build_filters(query: FlightQuery) -> FlightSearchFilters:
        segments = [
            _segment(
                query.outbound_origins,
                query.outbound_destinations,
                query.departure_date.isoformat(),
                query,
            ),
        ]
        trip_type = TripType.ONE_WAY
        if query.return_date is not None:
            trip_type = TripType.MULTI_CITY if query.is_open_jaw else TripType.ROUND_TRIP
            segments.append(
                _segment(
                    query.inbound_origins,
                    query.inbound_destinations,
                    query.return_date.isoformat(),
                    query,
                )
            )

        return FlightSearchFilters(
            trip_type=trip_type,
            passenger_info=PassengerInfo(adults=query.passengers),
            flight_segments=segments,
            seat_type=SeatType[query.cabin.name],
            stops=FliMaxStops[query.max_stops.name],
            airlines=[Airline[airline] for airline in query.airlines] or None,
            sort_by=SortBy.CHEAPEST,
        )

    @staticmethod
    def _build_date_filters(query: FlexibleSearchQuery, nights: int) -> DateSearchFilters:
        return_date = query.start_date + timedelta(days=nights)
        segments = [
            _segment(
                query.outbound_origins,
                query.outbound_destinations,
                query.start_date.isoformat(),
                query,
            ),
            _segment(
                query.inbound_origins,
                query.inbound_destinations,
                return_date.isoformat(),
                query,
            ),
        ]
        return DateSearchFilters(
            trip_type=TripType.ROUND_TRIP,
            passenger_info=PassengerInfo(adults=query.passengers),
            flight_segments=segments,
            seat_type=SeatType[query.cabin.name],
            stops=FliMaxStops[query.max_stops.name],
            airlines=[Airline[airline] for airline in query.airlines] or None,
            from_date=query.start_date.isoformat(),
            to_date=query.end_date.isoformat(),
            duration=nights,
        )

    @staticmethod
    def _build_one_way_date_filters(
        query: FlexibleSearchQuery,
        origins: tuple[str, ...],
        destinations: tuple[str, ...],
        start_date: date,
        end_date: date,
    ) -> DateSearchFilters:
        return DateSearchFilters(
            trip_type=TripType.ONE_WAY,
            passenger_info=PassengerInfo(adults=query.passengers),
            flight_segments=[_segment(origins, destinations, start_date.isoformat(), query)],
            seat_type=SeatType[query.cabin.name],
            stops=FliMaxStops[query.max_stops.name],
            airlines=[Airline[airline] for airline in query.airlines] or None,
            from_date=start_date.isoformat(),
            to_date=end_date.isoformat(),
        )

    @staticmethod
    def _normalize_itinerary(
        result: FliFlightResult | tuple[FliFlightResult, ...],
        *,
        booking_url: str | None = None,
    ) -> FlightOffer:
        parts = result if isinstance(result, tuple) else (result,)
        if not parts:
            raise ProviderError("Flight provider returned an empty itinerary")

        legs: list[FlightLeg] = []
        journeys: list[FlightJourney] = []
        price_part = parts[0]
        duration_minutes = 0
        stops = 0
        for part in parts:
            journey_legs = tuple(_normalize_leg(leg) for leg in part.legs)
            journey_layovers = tuple(
                _normalize_layover(layover) for layover in (part.layovers or [])
            )
            journeys.append(
                FlightJourney(
                    duration_minutes=part.duration,
                    legs=journey_legs,
                    layovers=journey_layovers,
                    self_transfer=bool(part.self_transfer),
                )
            )
            legs.extend(journey_legs)
            duration_minutes += part.duration
            stops += part.stops

        raw_price = price_part.price
        price = Decimal(str(raw_price)) if raw_price is not None else None
        raw_currency = price_part.currency
        currency = raw_currency if isinstance(raw_currency, str) else None
        return FlightOffer(
            price=price,
            currency=currency,
            duration_minutes=duration_minutes,
            stops=stops,
            legs=tuple(legs),
            booking_url=booking_url,
            journeys=tuple(journeys),
        )

    @staticmethod
    def _normalize_booking_option(raw_option: FliBookingOption) -> BookingOption:
        return BookingOption(
            vendor_name=raw_option.vendor_name,
            is_airline_direct=raw_option.is_airline_direct,
            price=Decimal(str(raw_option.price)) if raw_option.price is not None else None,
            currency=raw_option.currency,
            fare_name=raw_option.fare_name,
            booking_url=_usable_url(raw_option.booking_url),
            google_click_url=_usable_url(raw_option.google_click_url, require_query=True),
        )

    @staticmethod
    def _normalize_date_price(
        raw_price: DatePrice, query: FlexibleSearchQuery
    ) -> FlexibleDateOffer:
        if len(raw_price.date) != 2:
            raise ProviderError("Flight provider returned an unexpected date result")
        departure_at, return_at = raw_price.date
        booking_url = google_flights_url(
            query.origin,
            query.destination,
            departure_at.date().isoformat(),
            return_at.date().isoformat(),
            currency=query.currency,
            language="en",
        )
        if len(query.outbound_origins) > 1 or len(query.outbound_destinations) > 1:
            booking_url = _round_trip_group_search_url(query, departure_at.date(), return_at.date())
        return FlexibleDateOffer(
            departure_date=departure_at.date(),
            return_date=return_at.date(),
            price=Decimal(str(raw_price.price)),
            currency=raw_price.currency,
            booking_url=booking_url,
        )


def _usable_url(value: str | None, *, require_query: bool = False) -> str | None:
    if not value or "..." in value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if require_query and not parsed.query:
        return None
    return value


def _itinerary_booking_url(
    client: _SearchClient,
    result: FliFlightResult | tuple[FliFlightResult, ...],
    currency: str,
) -> str | None:
    value = client.build_flight_booking_url(result, currency=currency)
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in {"google.com", "www.google.com"}:
        return None
    if parsed.path.rstrip("/") != "/travel/flights/booking":
        return None
    if not parse_qs(parsed.query).get("tfs", [""])[0]:
        return None
    return value


def _offer_sort_key(offer: FlightOffer) -> tuple[bool, Decimal, int]:
    return (offer.price is None, offer.price or Decimal(), offer.duration_minutes)


def _segment(
    origins: str | tuple[str, ...],
    destinations: str | tuple[str, ...],
    travel_date: str,
    query: FlightQuery | FlexibleSearchQuery,
) -> FlightSegment:
    origin_codes = (origins,) if isinstance(origins, str) else origins
    destination_codes = (destinations,) if isinstance(destinations, str) else destinations
    time_restrictions = None
    if query.departure_window is not None:
        start, end = query.departure_window
        time_restrictions = TimeRestrictions(earliest_departure=start, latest_departure=end)
    return FlightSegment(
        departure_airport=[[Airport[origin], 0] for origin in origin_codes],
        arrival_airport=[[Airport[destination], 0] for destination in destination_codes],
        travel_date=travel_date,
        time_restrictions=time_restrictions,
    )


def _normalize_leg(raw_leg: FliFlightLeg) -> FlightLeg:
    try:
        airline = raw_leg.airline.name.removeprefix("_")
        departure_airport = raw_leg.departure_airport.name
        arrival_airport = raw_leg.arrival_airport.name
        return FlightLeg(
            airline=str(airline),
            flight_number=str(raw_leg.flight_number),
            departure_airport=str(departure_airport),
            arrival_airport=str(arrival_airport),
            departure_at=raw_leg.departure_datetime,
            arrival_at=raw_leg.arrival_datetime,
            duration_minutes=raw_leg.duration,
        )
    except (AttributeError, TypeError) as error:
        raise ProviderError("Flight provider returned an unexpected flight leg") from error


def _normalize_layover(raw_layover: FliLayover) -> FlightLayover:
    try:
        airport = raw_layover.airport.name
        return FlightLayover(
            airport=str(airport),
            duration_minutes=int(raw_layover.duration),
            overnight=bool(raw_layover.overnight),
            airport_change=bool(raw_layover.change_of_airport),
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise ProviderError("Flight provider returned an unexpected layover") from error


def _one_way_date_prices(
    raw_results: object,
) -> dict[date, tuple[Decimal, str | None]]:
    if raw_results is None:
        return {}
    if not isinstance(raw_results, list):
        raise ProviderError("Flight provider returned an unexpected date response")
    prices: dict[date, tuple[Decimal, str | None]] = {}
    for item in cast(list[DatePrice], raw_results):
        if len(item.date) != 1:
            raise ProviderError("Flight provider returned an unexpected one-way date result")
        travel_date = item.date[0].date()
        price = Decimal(str(item.price))
        current = prices.get(travel_date)
        if current is None or price < current[0]:
            prices[travel_date] = (price, item.currency)
    return prices


def _multi_city_search_url(
    query: FlexibleSearchQuery, departure_date: date, return_date: date
) -> str:
    outbound_origins = ",".join(query.outbound_origins)
    outbound_destinations = ",".join(query.outbound_destinations)
    inbound_origins = ",".join(query.inbound_origins)
    inbound_destinations = ",".join(query.inbound_destinations)
    search_text = (
        f"Flights from {outbound_origins} to {outbound_destinations} on {departure_date}; "
        f"then from {inbound_origins} to {inbound_destinations} on {return_date}"
    )
    return (
        f"https://www.google.com/travel/flights?q={quote(search_text)}&curr={query.currency}&hl=en"
    )


def _round_trip_group_search_url(
    query: FlexibleSearchQuery, departure_date: date, return_date: date
) -> str:
    origins = ",".join(query.outbound_origins)
    destinations = ",".join(query.outbound_destinations)
    search_text = (
        f"Flights from {origins} to {destinations} on {departure_date} returning {return_date}"
    )
    return (
        f"https://www.google.com/travel/flights?q={quote(search_text)}&curr={query.currency}&hl=en"
    )
