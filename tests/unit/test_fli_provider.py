from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol, cast

import pytest

from hermes_flight_finder.models import FlexibleSearchQuery, FlightQuery
from hermes_flight_finder.providers import BookingOptionsUnavailable
from hermes_flight_finder.providers.fli import FliFlightProvider


@dataclass(frozen=True)
class _NamedCode:
    name: str


@dataclass(frozen=True)
class _RawLeg:
    airline: _NamedCode
    flight_number: str
    departure_airport: _NamedCode
    arrival_airport: _NamedCode
    departure_datetime: datetime
    arrival_datetime: datetime
    duration: int


@dataclass(frozen=True)
class _RawFlight:
    legs: list[_RawLeg]
    price: float | None
    currency: str | None
    duration: int
    stops: int


@dataclass(frozen=True)
class _RawBookingOption:
    vendor_name: str | None
    is_airline_direct: bool
    price: float | None
    currency: str | None
    fare_name: str | None
    booking_url: str | None
    google_click_url: str | None


class _FakeSearchClient:
    def __init__(
        self,
        results: object,
        booking_options: object = (),
        itinerary_url: str = "https://www.google.com/travel/flights/booking?tfs=TEST",
    ) -> None:
        self.results = results
        self.itinerary_url = itinerary_url
        self.booking_options = booking_options
        self.currency: str | None = None
        self.booked_flight: object | None = None

    def search(self, filters: object, top_n: int = 5, currency: str | None = None) -> object:
        self.currency = currency
        return self.results

    def get_booking_options(
        self, flight: object, filters: object, currency: str | None = None
    ) -> object:
        self.booked_flight = flight
        self.currency = currency
        if isinstance(self.booking_options, Exception):
            raise self.booking_options
        return self.booking_options

    def build_flight_booking_url(
        self,
        flight: object,
        *,
        currency: str | None = None,
        language: str | None = None,
        country: str | None = None,
    ) -> str:
        return self.itinerary_url


@dataclass(frozen=True)
class _RawDatePrice:
    date: tuple[datetime, datetime]
    price: float
    currency: str | None


class _DateFilters(Protocol):
    duration: int


class _FakeDateSearchClient:
    def __init__(self) -> None:
        self.durations: list[int] = []

    def search(self, filters: object, currency: str | None = None) -> object:
        duration = cast(_DateFilters, filters).duration
        self.durations.append(duration)
        return [
            _RawDatePrice(
                date=(datetime(2026, 9, 18), datetime(2026, 9, 18) + timedelta(days=duration)),
                price=float(100 - duration),
                currency=currency,
            )
        ]


def _raw_flight(origin: str, destination: str, price: float) -> _RawFlight:
    departure = datetime(2026, 9, 18, 8, 0)
    return _RawFlight(
        legs=[
            _RawLeg(
                airline=_NamedCode("EW"),
                flight_number="EW 123",
                departure_airport=_NamedCode(origin),
                arrival_airport=_NamedCode(destination),
                departure_datetime=departure,
                arrival_datetime=departure + timedelta(minutes=120),
                duration=120,
            )
        ],
        price=price,
        currency="EUR",
        duration=120,
        stops=0,
    )


def test_provider_normalizes_round_trip() -> None:
    outbound = _raw_flight("HAM", "NCE", 89.0)
    inbound = _raw_flight("NCE", "HAM", 89.0)
    client = _FakeSearchClient([(outbound, inbound)])
    provider = FliFlightProvider(search_factory=lambda: client)
    query = FlightQuery(
        origin="HAM",
        destination="NCE",
        departure_date=date.today() + timedelta(days=10),
        return_date=date.today() + timedelta(days=13),
        passengers=2,
        currency="EUR",
        airlines=("EW",),
    )

    offers = provider.search(query)

    assert client.currency == "EUR"
    assert str(offers[0].price) == "89.0"
    assert offers[0].duration_minutes == 240
    assert offers[0].stops == 0
    assert offers[0].airlines == ("EW",)
    assert offers[0].booking_url == ("https://www.google.com/travel/flights/booking?tfs=TEST")
    assert [leg.departure_airport for leg in offers[0].legs] == ["HAM", "NCE"]


def test_provider_rejects_generic_google_flights_url_as_itinerary_handoff() -> None:
    client = _FakeSearchClient(
        [_raw_flight("HAM", "NCE", 89.0)],
        itinerary_url="https://www.google.com/travel/flights?q=HAM+NCE",
    )
    provider = FliFlightProvider(search_factory=lambda: client)
    query = FlightQuery(
        origin="HAM",
        destination="NCE",
        departure_date=date.today() + timedelta(days=10),
    )

    offers = provider.search(query)

    assert offers[0].booking_url is None


def test_provider_expands_each_requested_duration() -> None:
    client = _FakeDateSearchClient()
    provider = FliFlightProvider(date_search_factory=lambda: client)
    query = FlexibleSearchQuery(
        origin="HAM",
        destination="NCE",
        start_date=date.today() + timedelta(days=10),
        end_date=date.today() + timedelta(days=40),
        min_nights=2,
        max_nights=4,
        currency="EUR",
    )

    offers = provider.search_dates(query)

    assert client.durations == [2, 3, 4]
    assert [offer.nights for offer in offers] == [2, 3, 4]
    assert [str(offer.price) for offer in offers] == ["98.0", "97.0", "96.0"]
    assert all(offer.booking_url for offer in offers)
    assert "Flights%20from%20HAM%20to%20NCE" in (offers[0].booking_url or "")


def test_provider_returns_direct_booking_handoffs_for_the_ranked_offer() -> None:
    expensive = _raw_flight("HAM", "NCE", 120.0)
    cheap = _raw_flight("HAM", "NCE", 89.0)
    booking_option = _RawBookingOption(
        vendor_name="Eurowings",
        is_airline_direct=True,
        price=89.0,
        currency="EUR",
        fare_name="Basic",
        booking_url="https://book.example.test/eurowings",
        google_click_url="https://google.example.test/eurowings",
    )
    client = _FakeSearchClient([expensive, cheap], [booking_option])
    provider = FliFlightProvider(search_factory=lambda: client)
    query = FlightQuery(
        origin="HAM",
        destination="NCE",
        departure_date=date.today() + timedelta(days=10),
        currency="EUR",
    )

    selected_offer, options = provider.booking_options(query, 0)

    assert str(selected_offer.price) == "89.0"
    assert selected_offer.booking_url == ("https://www.google.com/travel/flights/booking?tfs=TEST")
    assert client.booked_flight is cheap
    assert options[0].vendor_name == "Eurowings"
    assert options[0].is_airline_direct is True
    assert options[0].handoff_url == "https://book.example.test/eurowings"


def test_provider_preserves_exact_handoff_when_vendor_options_fail() -> None:
    raw_flight = _raw_flight("HAM", "NCE", 89.0)
    client = _FakeSearchClient([raw_flight], RuntimeError("temporary vendor failure"))
    provider = FliFlightProvider(search_factory=lambda: client)
    query = FlightQuery(
        origin="HAM",
        destination="NCE",
        departure_date=date.today() + timedelta(days=10),
        currency="EUR",
    )

    with pytest.raises(BookingOptionsUnavailable) as exc_info:
        provider.booking_options(query, 0)

    assert str(exc_info.value.selected_offer.price) == "89.0"
    assert exc_info.value.selected_offer.booking_url == (
        "https://www.google.com/travel/flights/booking?tfs=TEST"
    )


def test_provider_discards_truncated_booking_placeholders() -> None:
    raw_flight = _raw_flight("HAM", "NCE", 89.0)
    placeholder = _RawBookingOption(
        vendor_name="Eurowings",
        is_airline_direct=True,
        price=89.0,
        currency="EUR",
        fare_name=None,
        booking_url="www.eurowings.com/...",
        google_click_url="https://www.google.com/travel/clk/f",
    )
    client = _FakeSearchClient([raw_flight], [placeholder])
    provider = FliFlightProvider(search_factory=lambda: client)
    query = FlightQuery(
        origin="HAM",
        destination="NCE",
        departure_date=date.today() + timedelta(days=10),
        currency="EUR",
    )

    _, options = provider.booking_options(query, 0)

    assert options[0].booking_url is None
    assert options[0].google_click_url is None
    assert options[0].handoff_url is None
