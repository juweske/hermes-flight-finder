"""Adapter from the `fli` package to Hermes Flight Finder domain models."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import Protocol, cast

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
    FlightLeg as FliFlightLeg,
)
from fli.models import (
    FlightResult as FliFlightResult,
)
from fli.models import MaxStops as FliMaxStops
from fli.search import DatePrice, SearchDates, SearchFlights

from hermes_flight_finder.models import (
    FlexibleDateOffer,
    FlexibleSearchQuery,
    FlightLeg,
    FlightOffer,
    FlightQuery,
)
from hermes_flight_finder.providers.base import ProviderError


class _SearchClient(Protocol):
    def search(
        self,
        filters: FlightSearchFilters,
        top_n: int = 5,
        currency: str | None = None,
        language: str | None = None,
        country: str | None = None,
    ) -> object: ...


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
    ) -> None:
        self._search_factory = search_factory or SearchFlights
        self._date_search_factory = date_search_factory or SearchDates

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
        return [self._normalize_itinerary(result) for result in results]

    def search_dates(self, query: FlexibleSearchQuery) -> list[FlexibleDateOffer]:
        """Search every requested trip duration through `fli`'s calendar API."""
        client = cast(_DateSearchClient, self._date_search_factory())
        offers: list[FlexibleDateOffer] = []
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
            offers.extend(self._normalize_date_price(result) for result in results)
        return offers

    @staticmethod
    def _build_filters(query: FlightQuery) -> FlightSearchFilters:
        segments = [
            _segment(query.origin, query.destination, query.departure_date.isoformat(), query),
        ]
        trip_type = TripType.ONE_WAY
        if query.return_date is not None:
            trip_type = TripType.ROUND_TRIP
            segments.append(
                _segment(query.destination, query.origin, query.return_date.isoformat(), query)
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
            _segment(query.origin, query.destination, query.start_date.isoformat(), query),
            _segment(query.destination, query.origin, return_date.isoformat(), query),
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
    def _normalize_itinerary(
        result: FliFlightResult | tuple[FliFlightResult, ...],
    ) -> FlightOffer:
        parts = result if isinstance(result, tuple) else (result,)
        if not parts:
            raise ProviderError("Flight provider returned an empty itinerary")

        legs: list[FlightLeg] = []
        prices: list[Decimal] = []
        currencies: set[str] = set()
        duration_minutes = 0
        stops = 0
        for part in parts:
            legs.extend(_normalize_leg(leg) for leg in part.legs)
            duration_minutes += part.duration
            stops += part.stops
            raw_price = part.price
            if raw_price is not None:
                prices.append(Decimal(str(raw_price)))
            raw_currency = part.currency
            if isinstance(raw_currency, str):
                currencies.add(raw_currency)

        currency = currencies.pop() if len(currencies) == 1 else None
        price = sum(prices, Decimal()) if len(prices) == len(parts) else None
        return FlightOffer(
            price=price,
            currency=currency,
            duration_minutes=duration_minutes,
            stops=stops,
            legs=tuple(legs),
        )

    @staticmethod
    def _normalize_date_price(raw_price: DatePrice) -> FlexibleDateOffer:
        if len(raw_price.date) != 2:
            raise ProviderError("Flight provider returned an unexpected date result")
        departure_at, return_at = raw_price.date
        return FlexibleDateOffer(
            departure_date=departure_at.date(),
            return_date=return_at.date(),
            price=Decimal(str(raw_price.price)),
            currency=raw_price.currency,
        )


def _segment(
    origin: str,
    destination: str,
    travel_date: str,
    query: FlightQuery | FlexibleSearchQuery,
) -> FlightSegment:
    time_restrictions = None
    if query.departure_window is not None:
        start, end = query.departure_window
        time_restrictions = TimeRestrictions(earliest_departure=start, latest_departure=end)
    return FlightSegment(
        departure_airport=[[Airport[origin], 0]],
        arrival_airport=[[Airport[destination], 0]],
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
