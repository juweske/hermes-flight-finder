"""Deterministic itinerary-quality evaluation and recommendation ordering."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from hermes_flight_finder.models import (
    ConnectionPolicy,
    FlexibleDateOffer,
    FlightOffer,
    ItineraryWarning,
    QualityPolicy,
    QualityStatus,
    WarningSeverity,
)


@dataclass(frozen=True, slots=True)
class AssessedOffer:
    """A concrete flight offer evaluated under one quality policy."""

    offer: FlightOffer
    status: QualityStatus
    warnings: tuple[ItineraryWarning, ...]


@dataclass(frozen=True, slots=True)
class AssessedDateCandidate:
    """Concrete itineraries evaluated for one flexible date pair."""

    date_offer: FlexibleDateOffer
    offers: tuple[AssessedOffer, ...]
    offer_numbers: tuple[int, ...]
    recommended_offer: AssessedOffer | None
    recommended_offer_number: int | None


def assess_offer(
    offer: FlightOffer,
    policy: QualityPolicy,
    *,
    fastest_duration_minutes: int | None = None,
) -> AssessedOffer:
    """Return structured warnings without hiding the underlying offer."""
    warnings: list[ItineraryWarning] = []
    journeys = offer.journeys
    for journey_index, journey in enumerate(journeys, start=1):
        for layover in journey.layovers:
            if layover.duration_minutes > policy.acceptable_layover_minutes:
                severe = layover.duration_minutes > policy.acceptable_layover_minutes * 2
                warnings.append(
                    ItineraryWarning(
                        code="long_layover",
                        severity=(WarningSeverity.SEVERE if severe else WarningSeverity.WARNING),
                        message=(
                            f"Journey {journey_index} has a {layover.duration_minutes}-minute "
                            f"layover at {layover.airport}."
                        ),
                        journey=journey_index,
                        actual_minutes=layover.duration_minutes,
                        threshold_minutes=policy.acceptable_layover_minutes,
                    )
                )
            _append_policy_warning(
                warnings,
                enabled=layover.airport_change,
                policy=policy.airport_change,
                code="airport_change",
                message=f"Journey {journey_index} requires changing airports.",
                journey=journey_index,
            )
            _append_policy_warning(
                warnings,
                enabled=layover.overnight,
                policy=policy.overnight_layover,
                code="overnight_layover",
                message=f"Journey {journey_index} includes an overnight layover.",
                journey=journey_index,
            )
        _append_policy_warning(
            warnings,
            enabled=journey.self_transfer,
            policy=policy.self_transfer,
            code="self_transfer",
            message=(
                f"Journey {journey_index} is a self-transfer; separate check-in and baggage "
                "handling may be required."
            ),
            journey=journey_index,
        )

    if fastest_duration_minutes and offer.duration_minutes > max(
        fastest_duration_minutes * 2, fastest_duration_minutes + 240
    ):
        warnings.append(
            ItineraryWarning(
                code="excessive_duration",
                severity=WarningSeverity.SEVERE,
                message=(
                    f"This itinerary takes {offer.duration_minutes} minutes versus "
                    f"the fastest option's {fastest_duration_minutes} minutes."
                ),
                journey=0,
                actual_minutes=offer.duration_minutes,
                threshold_minutes=max(fastest_duration_minutes * 2, fastest_duration_minutes + 240),
            )
        )

    status = QualityStatus.ACCEPTABLE
    if any(item.severity == WarningSeverity.SEVERE for item in warnings):
        status = QualityStatus.AVOID
    elif warnings:
        status = QualityStatus.WARNING
    return AssessedOffer(offer=offer, status=status, warnings=tuple(warnings))


def assess_and_rank_offers(offers: list[FlightOffer], policy: QualityPolicy) -> list[AssessedOffer]:
    """Prefer acceptable itineraries, then price and travel time."""
    fastest = min((offer.duration_minutes for offer in offers), default=None)
    assessed = [assess_offer(offer, policy, fastest_duration_minutes=fastest) for offer in offers]
    return sorted(assessed, key=_assessment_sort_key)


def rank_date_candidates(
    candidates: list[AssessedDateCandidate],
) -> list[AssessedDateCandidate]:
    """Order date pairs by their best concrete itinerary."""
    return sorted(candidates, key=_date_candidate_sort_key)


def _append_policy_warning(
    warnings: list[ItineraryWarning],
    *,
    enabled: bool,
    policy: ConnectionPolicy,
    code: str,
    message: str,
    journey: int,
) -> None:
    if not enabled or policy == ConnectionPolicy.ALLOW:
        return
    severity = (
        WarningSeverity.SEVERE if policy == ConnectionPolicy.AVOID else WarningSeverity.WARNING
    )
    warnings.append(
        ItineraryWarning(code=code, severity=severity, message=message, journey=journey)
    )


def _assessment_sort_key(
    assessment: AssessedOffer,
) -> tuple[int, bool, Decimal, int]:
    rank = {
        QualityStatus.ACCEPTABLE: 0,
        QualityStatus.WARNING: 1,
        QualityStatus.AVOID: 2,
    }[assessment.status]
    price = assessment.offer.price
    return (rank, price is None, price or Decimal(), assessment.offer.duration_minutes)


def _date_candidate_sort_key(
    candidate: AssessedDateCandidate,
) -> tuple[int, bool, Decimal, int]:
    if candidate.recommended_offer is None:
        return (3, True, Decimal(), 0)
    return _assessment_sort_key(candidate.recommended_offer)
