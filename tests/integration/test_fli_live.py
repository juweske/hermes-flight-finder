"""Opt-in integration tests that perform real Google Flights requests."""

from datetime import date, timedelta

import pytest

from hermes_flight_finder.models import FlightQuery
from hermes_flight_finder.providers import FliFlightProvider


@pytest.mark.live
def test_fli_provider_searches_a_future_route() -> None:
    offers = FliFlightProvider().search(
        FlightQuery(
            origin="HAM",
            destination="NCE",
            departure_date=date.today() + timedelta(days=35),
            currency="EUR",
        )
    )

    assert all(offer.legs for offer in offers)
