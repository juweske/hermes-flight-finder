"""Deterministic checking of saved flight watches."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from hermes_flight_finder.models import AlertRecord, CheckResult, Deal, PriceObservation, Watch
from hermes_flight_finder.providers.base import FlightProvider
from hermes_flight_finder.search.flexible import FlexibleSearchService
from hermes_flight_finder.storage.base import WatchRepository


class WatchCheckService:
    """Query watches, record their best price, and emit non-duplicate deals."""

    def __init__(self, provider: FlightProvider, repository: WatchRepository) -> None:
        self._provider = provider
        self._repository = repository

    def check(self) -> CheckResult:
        alerts: list[Deal] = []
        watches = self._repository.list()
        for watch in watches:
            offers = FlexibleSearchService(self._provider).search(watch.to_flexible_search_query())
            if not offers:
                continue
            offer = offers[0]
            observation = PriceObservation(
                checked_at=datetime.now(UTC),
                watch_id=watch.id,
                price=offer.price,
                currency=offer.currency or watch.currency,
                departure_date=offer.departure_date,
                return_date=offer.return_date,
                stops=0 if watch.max_stops.name == "NON_STOP" else None,
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
    )


def _already_alerted(observation: PriceObservation, alerts: list[AlertRecord]) -> bool:
    return any(
        alert.price == observation.price
        and alert.departure_date == observation.departure_date
        and alert.return_date == observation.return_date
        for alert in alerts
    )
