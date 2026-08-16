from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol, cast

from hermes_flight_tracker.models import FlexibleSearchQuery, FlightQuery
from hermes_flight_tracker.providers.fli import FliFlightProvider


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


class _FakeSearchClient:
    def __init__(self, results: object) -> None:
        self.results = results
        self.currency: str | None = None

    def search(self, filters: object, top_n: int = 5, currency: str | None = None) -> object:
        self.currency = currency
        return self.results


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
    outbound = _raw_flight("HAM", "NCE", 45.0)
    inbound = _raw_flight("NCE", "HAM", 44.0)
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
    assert [leg.departure_airport for leg in offers[0].legs] == ["HAM", "NCE"]


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
