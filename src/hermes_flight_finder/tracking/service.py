"""Deterministic checking of saved flight watches."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from hermes_flight_finder.models import (
    AlertRecord,
    CheckResult,
    Deal,
    FlexibleDateOffer,
    FlightQuery,
    PriceObservation,
    QualityPolicy,
    Watch,
)
from hermes_flight_finder.providers.base import FlightProvider
from hermes_flight_finder.quality import (
    AssessedDateCandidate,
    assess_and_rank_offers,
    rank_date_candidates,
)
from hermes_flight_finder.search import SearchService
from hermes_flight_finder.search.flexible import FlexibleSearchService
from hermes_flight_finder.storage.base import WatchRepository


class WatchCheckService:
    """Query watches, record their best price, and emit non-duplicate deals."""

    def __init__(
        self,
        provider: FlightProvider,
        repository: WatchRepository,
        *,
        quality_policy: QualityPolicy | None = None,
        quality_candidates: int = 3,
    ) -> None:
        if quality_candidates < 1:
            raise ValueError("quality candidates must be at least 1")
        self._provider = provider
        self._repository = repository
        self._quality_policy = quality_policy or QualityPolicy()
        self._quality_candidates = quality_candidates

    def check(self) -> CheckResult:
        alerts: list[Deal] = []
        watches = self._repository.list()
        for watch in watches:
            offers = FlexibleSearchService(self._provider).search(watch.to_flexible_search_query())
            candidates = self._concrete_candidates(watch, offers[: self._quality_candidates])
            ranked = rank_date_candidates(candidates)
            if not ranked or ranked[0].recommended_offer is None:
                continue
            candidate = ranked[0]
            assessment = candidate.recommended_offer
            assert assessment is not None
            offer = assessment.offer
            if offer.price is None:
                continue
            observation = PriceObservation(
                checked_at=datetime.now(UTC),
                watch_id=watch.id,
                price=offer.price,
                currency=offer.currency or watch.currency,
                departure_date=candidate.date_offer.departure_date,
                return_date=candidate.date_offer.return_date,
                airlines=offer.airlines,
                stops=offer.stops,
                source="fli",
                quality_status=assessment.status,
                warnings=assessment.warnings,
                booking_strategy=offer.booking_strategy,
                booking_warning=offer.booking_warning,
                routes=_offer_routes(offer),
            )
            deal = _evaluate(
                watch,
                observation,
                self._repository.list_observations(watch.id),
                self._repository.list_alerts(watch.id),
            )
            self._repository.record_observation(observation)
            if deal is not None:
                self._repository.record_alert(
                    AlertRecord(
                        watch_id=deal.watch_id,
                        price=deal.price,
                        departure_date=deal.departure_date,
                        return_date=deal.return_date,
                        alerted_at=observation.checked_at,
                    )
                )
                alerts.append(deal)
        return CheckResult(checked=len(watches), alerts=tuple(alerts))

    def _concrete_candidates(
        self, watch: Watch, date_offers: list[FlexibleDateOffer]
    ) -> list[AssessedDateCandidate]:
        candidates: list[AssessedDateCandidate] = []
        for date_offer in date_offers:
            query = FlightQuery(
                origin=watch.origin,
                destination=watch.destination,
                departure_date=date_offer.departure_date,
                return_date=date_offer.return_date,
                cabin=watch.cabin,
                max_stops=watch.max_stops,
                passengers=watch.passengers,
                currency=watch.currency,
                airlines=watch.airlines,
                departure_window=watch.departure_window,
                origin_alternatives=watch.origin_alternatives,
                destination_alternatives=watch.destination_alternatives,
                return_origins=watch.return_origins,
                return_destinations=watch.return_destinations,
            )
            offers = SearchService(self._provider).search(query)
            ranked = assess_and_rank_offers(offers, self._quality_policy)
            candidates.append(
                AssessedDateCandidate(
                    date_offer=date_offer,
                    offers=tuple(ranked[:5]),
                    offer_numbers=(),
                    recommended_offer=ranked[0] if ranked else None,
                    recommended_offer_number=None,
                )
            )
        return candidates


def _evaluate(
    watch: Watch,
    observation: PriceObservation,
    history: list[PriceObservation],
    alerts: list[AlertRecord],
) -> Deal | None:
    previous_best = min((item.price for item in history), default=None)
    reasons: list[str] = []
    if watch.target_price is not None and observation.price <= watch.target_price:
        reasons.append("target_price")
    drop_percent: Decimal | None = None
    if previous_best is not None and watch.drop_percent is not None:
        threshold = previous_best * (Decimal(1) - watch.drop_percent / Decimal(100))
        if observation.price <= threshold:
            drop_percent = (previous_best - observation.price) / previous_best * Decimal(100)
            reasons.append("price_drop")
    if not reasons or _already_alerted(observation, alerts):
        return None
    return Deal(
        watch_id=watch.id,
        price=observation.price,
        currency=observation.currency,
        departure_date=observation.departure_date,
        return_date=observation.return_date,
        previous_best=previous_best,
        drop_percent=drop_percent,
        reasons=tuple(reasons),
        airlines=observation.airlines,
        stops=observation.stops,
        quality_status=observation.quality_status,
        warnings=observation.warnings,
        booking_strategy=observation.booking_strategy,
        booking_warning=observation.booking_warning,
        routes=observation.routes,
    )


def _already_alerted(observation: PriceObservation, alerts: list[AlertRecord]) -> bool:
    return any(
        alert.price == observation.price
        and alert.departure_date == observation.departure_date
        and alert.return_date == observation.return_date
        for alert in alerts
    )


def _offer_routes(offer: object) -> tuple[tuple[str, str], ...]:
    from hermes_flight_finder.models import FlightOffer

    if not isinstance(offer, FlightOffer):
        raise TypeError("Expected a flight offer")
    return tuple(
        (journey.legs[0].departure_airport, journey.legs[-1].arrival_airport)
        for journey in offer.journeys
        if journey.legs
    )
