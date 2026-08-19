from datetime import date, timedelta

import pytest

from hermes_flight_finder.models import FlexibleSearchQuery, FlightQuery


def test_query_normalizes_codes() -> None:
    query = FlightQuery(
        origin="ham",
        destination="nce",
        departure_date=date.today() + timedelta(days=1),
        currency="eur",
        airlines=("ew",),
    )

    assert query.origin == "HAM"
    assert query.destination == "NCE"
    assert query.currency == "EUR"
    assert query.airlines == ("EW",)


def test_query_supports_airport_groups_and_open_jaw_returns() -> None:
    query = FlightQuery(
        origin="jfk",
        destination="lhr",
        departure_date=date.today() + timedelta(days=5),
        return_date=date.today() + timedelta(days=10),
        origin_alternatives=("lga", "ewr"),
        destination_alternatives=("lgw",),
        return_origins=("cdg", "ory"),
        return_destinations=("bos",),
    )

    assert query.outbound_origins == ("JFK", "LGA", "EWR")
    assert query.outbound_destinations == ("LHR", "LGW")
    assert query.inbound_origins == ("CDG", "ORY")
    assert query.inbound_destinations == ("BOS",)
    assert query.is_open_jaw is True


def test_query_rejects_past_dates() -> None:
    with pytest.raises(ValueError, match="must not be in the past"):
        FlightQuery(
            origin="HAM",
            destination="NCE",
            departure_date=date.today() - timedelta(days=1),
        )


def test_flexible_query_rejects_an_inverted_duration_range() -> None:
    with pytest.raises(ValueError, match="maximum nights"):
        FlexibleSearchQuery(
            origin="HAM",
            destination="NCE",
            start_date=date.today() + timedelta(days=1),
            end_date=date.today() + timedelta(days=10),
            min_nights=5,
            max_nights=2,
        )
