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

    assert offers
    assert all(offer.legs for offer in offers)


@pytest.mark.live
def test_fli_provider_searches_a_multi_city_open_jaw() -> None:
    offers = FliFlightProvider().search(
        FlightQuery(
            origin="JFK",
            destination="LAX",
            departure_date=date.today() + timedelta(days=35),
            return_date=date.today() + timedelta(days=42),
            return_origins=("SFO",),
            return_destinations=("BOS",),
            currency="USD",
        )
    )

    assert offers
    assert all(len(offer.journeys) == 2 for offer in offers)
    assert all(offer.booking_url for offer in offers)
