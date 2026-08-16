from datetime import date, datetime, timedelta
from decimal import Decimal

from hermes_flight_tracker.models import (
    FlexibleDateOffer,
    FlexibleSearchQuery,
    FlightLeg,
    FlightOffer,
    FlightQuery,
)
from hermes_flight_tracker.search import FlexibleSearchService, SearchService


class _FakeProvider:
    def __init__(self, offers: list[FlightOffer]) -> None:
        self.offers = offers

    def search(self, query: FlightQuery) -> list[FlightOffer]:
        return self.offers

    def search_dates(self, query: FlexibleSearchQuery) -> list[FlexibleDateOffer]:
        return []


def _offer(price: Decimal | None, duration_minutes: int) -> FlightOffer:
    departure = datetime(2026, 9, 18, 8, 0)
    leg = FlightLeg(
        airline="EW",
        flight_number="EW 123",
        departure_airport="HAM",
        arrival_airport="NCE",
        departure_at=departure,
        arrival_at=departure + timedelta(minutes=duration_minutes),
        duration_minutes=duration_minutes,
    )
    return FlightOffer(
        price=price,
        currency="EUR",
        duration_minutes=duration_minutes,
        stops=0,
        legs=(leg,),
    )


def test_search_sorts_priced_offers_before_unknown_prices() -> None:
    offers = [_offer(None, 90), _offer(Decimal("99"), 120), _offer(Decimal("79"), 150)]
    query = FlightQuery("HAM", "NCE", date.today() + timedelta(days=5))

    results = SearchService(_FakeProvider(offers)).search(query)

    assert [offer.price for offer in results] == [Decimal("79"), Decimal("99"), None]


class _FakeDateProvider:
    def __init__(self, offers: list[FlexibleDateOffer]) -> None:
        self.offers = offers

    def search(self, query: FlightQuery) -> list[FlightOffer]:
        return []

    def search_dates(self, query: FlexibleSearchQuery) -> list[FlexibleDateOffer]:
        return self.offers


def test_flexible_search_deduplicates_and_sorts_by_price() -> None:
    departure_date = date.today() + timedelta(days=5)
    offers = [
        FlexibleDateOffer(departure_date, departure_date + timedelta(days=2), Decimal("99"), "EUR"),
        FlexibleDateOffer(departure_date, departure_date + timedelta(days=2), Decimal("79"), "EUR"),
        FlexibleDateOffer(
            departure_date + timedelta(days=1),
            departure_date + timedelta(days=4),
            Decimal("89"),
            "EUR",
        ),
    ]
    query = FlexibleSearchQuery(
        "HAM",
        "NCE",
        departure_date,
        departure_date + timedelta(days=20),
        2,
        3,
    )

    results = FlexibleSearchService(_FakeDateProvider(offers)).search(query)

    assert [offer.price for offer in results] == [Decimal("79"), Decimal("89")]
