from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from hermes_flight_finder.models import (
    FlexibleDateOffer,
    FlexibleSearchQuery,
    FlightOffer,
    FlightQuery,
    Watch,
    WatchHealth,
    WatchHealthStatus,
)
from hermes_flight_finder.providers import ProviderError, ProviderErrorCode
from hermes_flight_finder.storage import JsonWatchRepository
from hermes_flight_finder.tracking import WatchCheckService


class _PriceProvider:
    def __init__(self, prices: list[Decimal]) -> None:
        self._prices = prices
        self._current_price = Decimal()

    def search(self, query: FlightQuery) -> list[FlightOffer]:
        return [
            FlightOffer(
                price=self._current_price,
                currency=query.currency,
                duration_minutes=120,
                stops=0,
                legs=(),
            )
        ]

    def search_dates(self, query: FlexibleSearchQuery) -> list[FlexibleDateOffer]:
        price = self._prices.pop(0)
        self._current_price = price
        return [
            FlexibleDateOffer(
                departure_date=query.start_date,
                return_date=query.start_date + timedelta(days=query.min_nights),
                price=price,
                currency=query.currency,
            )
        ]


class _PartiallyFailingProvider(_PriceProvider):
    def search_dates(self, query: FlexibleSearchQuery) -> list[FlexibleDateOffer]:
        if query.origin == "HAM":
            raise ProviderError(
                "The flight provider refused the request. Try again later.",
                ProviderErrorCode.REQUEST_REFUSED,
            )
        return super().search_dates(query)


def test_watch_check_records_baseline_alerts_on_drop_and_suppresses_duplicates(
    tmp_path: Path,
) -> None:
    start_date = date.today() + timedelta(days=5)
    watch = Watch(
        id="ham-nce-check",
        origin="HAM",
        destination="NCE",
        start_date=start_date,
        end_date=start_date + timedelta(days=20),
        min_nights=2,
        max_nights=2,
        target_price=Decimal("90"),
        drop_percent=Decimal("20"),
    )
    repository = JsonWatchRepository(tmp_path)
    repository.save(watch)
    service = WatchCheckService(
        _PriceProvider([Decimal("100"), Decimal("80"), Decimal("80")]), repository
    )

    first = service.check()
    second = service.check()
    third = service.check()

    assert first.checked == 1
    assert first.alerts == ()
    assert second.alerts[0].reasons == ("target_price", "price_drop")
    assert second.alerts[0].previous_best == Decimal("100")
    assert third.alerts == ()
    assert len(repository.list_observations(watch.id)) == 3
    assert len(repository.list_alerts(watch.id)) == 1


def test_watch_check_isolates_provider_failures_and_persists_health(tmp_path: Path) -> None:
    start_date = date.today() + timedelta(days=5)
    repository = JsonWatchRepository(tmp_path)
    repository.save(Watch("ham-nce-failed", "HAM", "NCE", start_date, start_date, 2, 2))
    repository.save(Watch("jfk-lax-live", "JFK", "LAX", start_date, start_date, 2, 2))
    service = WatchCheckService(_PartiallyFailingProvider([Decimal("100")]), repository)

    result = service.check()

    assert result.checked == 2
    assert [item.status for item in result.health] == [
        WatchHealthStatus.FAILED,
        WatchHealthStatus.LIVE,
    ]
    failed = repository.get_health("ham-nce-failed")
    assert failed is not None
    assert failed.error_code == "request_refused"
    assert "refused" in (failed.error_message or "")
    assert repository.get_health("jfk-lax-live") is not None


def test_watch_failure_is_stale_when_an_older_success_exists(tmp_path: Path) -> None:
    start_date = date.today() + timedelta(days=5)
    repository = JsonWatchRepository(tmp_path)
    watch = Watch("ham-nce-stale", "HAM", "NCE", start_date, start_date, 2, 2)
    repository.save(watch)
    previous_success = datetime(2026, 8, 20, 6, 0, tzinfo=UTC)
    repository.record_health(
        WatchHealth(
            watch_id=watch.id,
            status=WatchHealthStatus.LIVE,
            last_attempted_at=previous_success,
            last_success_at=previous_success,
        )
    )

    result = WatchCheckService(_PartiallyFailingProvider([]), repository).check()

    assert result.health[0].status == WatchHealthStatus.STALE
    assert result.health[0].last_success_at == previous_success
