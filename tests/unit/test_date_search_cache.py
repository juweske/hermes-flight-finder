from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from hermes_flight_finder.models import FlexibleDateOffer, FlexibleSearchQuery
from hermes_flight_finder.providers.date_cache import DateSearchCache


def test_cache_round_trips_successful_date_results(tmp_path: Path) -> None:
    now = datetime(2026, 8, 19, 12, tzinfo=UTC)
    cache = DateSearchCache(tmp_path, clock=lambda: now)
    query = _query()
    offers = [
        FlexibleDateOffer(
            departure_date=date(2027, 4, 1),
            return_date=date(2027, 4, 8),
            price=Decimal("899.00"),
            currency="USD",
            booking_url="https://example.test/search",
        )
    ]

    cache.put(query, offers)

    assert cache.get(query) == offers


def test_cache_expires_and_does_not_store_empty_results(tmp_path: Path) -> None:
    current = [datetime(2026, 8, 19, 12, tzinfo=UTC)]
    cache = DateSearchCache(
        tmp_path,
        ttl=timedelta(minutes=15),
        clock=lambda: current[0],
    )
    query = _query()
    cache.put(
        query,
        [
            FlexibleDateOffer(
                date(2027, 4, 1),
                date(2027, 4, 8),
                Decimal("899"),
                "USD",
            )
        ],
    )
    current[0] += timedelta(minutes=16)

    assert cache.get(query) is None

    empty_query = _query(destination="SFO")
    cache.put(empty_query, [])
    assert cache.get(empty_query) is None


def test_cache_keys_include_open_jaw_endpoints(tmp_path: Path) -> None:
    now = datetime(2026, 8, 19, 12, tzinfo=UTC)
    cache = DateSearchCache(tmp_path, clock=lambda: now)
    query = _query()
    cache.put(
        query,
        [FlexibleDateOffer(date(2027, 4, 1), date(2027, 4, 8), Decimal("899"), "USD")],
    )

    different_return = _query(return_origins=("LAS",))

    assert cache.get(different_return) is None


def _query(
    destination: str = "LAX",
    return_origins: tuple[str, ...] = ("SFO",),
) -> FlexibleSearchQuery:
    return FlexibleSearchQuery(
        origin="JFK",
        destination=destination,
        start_date=date(2027, 4, 1),
        end_date=date(2027, 4, 10),
        min_nights=7,
        max_nights=7,
        currency="USD",
        return_origins=return_origins,
    )
