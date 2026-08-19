from decimal import Decimal

from hermes_flight_finder.models import (
    ConnectionPolicy,
    FlightJourney,
    FlightLayover,
    FlightOffer,
    QualityPolicy,
    QualityStatus,
)
from hermes_flight_finder.quality import assess_and_rank_offers, assess_offer


def _offer(
    price: str,
    duration: int,
    *,
    layover: FlightLayover | None = None,
    self_transfer: bool = False,
) -> FlightOffer:
    journey = FlightJourney(
        duration_minutes=duration,
        legs=(),
        layovers=(layover,) if layover else (),
        self_transfer=self_transfer,
    )
    return FlightOffer(Decimal(price), "EUR", duration, 1, (), journeys=(journey,))


def test_avoid_policies_create_severe_structured_warnings() -> None:
    offer = _offer(
        "80",
        600,
        layover=FlightLayover("LGW", 360, overnight=True, airport_change=True),
        self_transfer=True,
    )

    assessed = assess_offer(offer, QualityPolicy(acceptable_layover_minutes=240))

    assert assessed.status == QualityStatus.AVOID
    assert {warning.code for warning in assessed.warnings} == {
        "long_layover",
        "airport_change",
        "overnight_layover",
        "self_transfer",
    }


def test_allow_policies_suppress_connection_warnings() -> None:
    offer = _offer(
        "80",
        300,
        layover=FlightLayover("LGW", 300, overnight=True, airport_change=True),
        self_transfer=True,
    )
    policy = QualityPolicy(
        acceptable_layover_minutes=360,
        airport_change=ConnectionPolicy.ALLOW,
        overnight_layover=ConnectionPolicy.ALLOW,
        self_transfer=ConnectionPolicy.ALLOW,
    )

    assert assess_offer(offer, policy).warnings == ()


def test_ranking_prefers_acceptable_offer_over_cheaper_impractical_offer() -> None:
    fast = _offer("120", 180)
    slow = _offer("80", 720)

    ranked = assess_and_rank_offers([slow, fast], QualityPolicy())

    assert ranked[0].offer is fast
    assert ranked[1].status == QualityStatus.AVOID
    assert ranked[1].warnings[-1].code == "excessive_duration"
