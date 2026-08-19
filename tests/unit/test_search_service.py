from datetime import date, datetime, timedelta
from decimal import Decimal

from hermes_flight_finder.models import (
    BookingStrategy,
    FlexibleDateOffer,
    FlexibleSearchQuery,
    FlightLeg,
    FlightOffer,
    FlightQuery,
)
from hermes_flight_finder.search import FlexibleSearchService, SearchService


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


class _OpenJawProvider:
    def __init__(self, multi_city_offers: list[FlightOffer]) -> None:
        self.multi_city_offers = multi_city_offers
        self.queries: list[FlightQuery] = []

    def search(self, query: FlightQuery) -> list[FlightOffer]:
        self.queries.append(query)
        if query.is_open_jaw:
            return self.multi_city_offers
        if query.origin == "HAM":
            offer = _offer(Decimal("70"), 120)
            return [
                FlightOffer(
                    price=offer.price,
                    currency=offer.currency,
                    duration_minutes=offer.duration_minutes,
                    stops=offer.stops,
                    legs=offer.legs,
                    booking_url="https://book.example/outbound",
                )
            ]
        offer = _offer(Decimal("85"), 130)
        return [
            FlightOffer(
                price=offer.price,
                currency=offer.currency,
                duration_minutes=offer.duration_minutes,
                stops=offer.stops,
                legs=offer.legs,
                booking_url="https://book.example/inbound",
            )
        ]

    def search_dates(self, query: FlexibleSearchQuery) -> list[FlexibleDateOffer]:
        return []


def _open_jaw_query() -> FlightQuery:
    return FlightQuery(
        origin="HAM",
        destination="NCE",
        departure_date=date.today() + timedelta(days=5),
        return_date=date.today() + timedelta(days=12),
        return_origins=("MRS",),
        return_destinations=("BER",),
    )


def test_open_jaw_prefers_multi_city_without_one_way_fallback() -> None:
    multi_city = _offer(Decimal("180"), 260)
    provider = _OpenJawProvider([multi_city])

    results = SearchService(provider).search(_open_jaw_query())

    assert results == [multi_city]
    assert len(provider.queries) == 1


def test_open_jaw_uses_warned_separate_tickets_only_when_multi_city_is_empty() -> None:
    provider = _OpenJawProvider([])

    results = SearchService(provider).search(_open_jaw_query())

    assert len(provider.queries) == 3
    assert results[0].price == Decimal("155")
    assert results[0].booking_strategy == BookingStrategy.SEPARATE_TICKETS
    assert results[0].component_prices == (Decimal("70"), Decimal("85"))
    assert results[0].component_booking_urls == (
        "https://book.example/outbound",
        "https://book.example/inbound",
    )
    assert "independent one-way bookings" in (results[0].booking_warning or "")


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
