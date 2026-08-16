from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from hermes_flight_finder.models import (
    FlexibleDateOffer,
    FlexibleSearchQuery,
    FlightOffer,
    FlightQuery,
    Watch,
)
from hermes_flight_finder.storage import JsonWatchRepository
from hermes_flight_finder.tracking import WatchCheckService


class _PriceProvider:
    def __init__(self, prices: list[Decimal]) -> None:
        self._prices = prices

    def search(self, query: FlightQuery) -> list[FlightOffer]:
        return []

    def search_dates(self, query: FlexibleSearchQuery) -> list[FlexibleDateOffer]:
        price = self._prices.pop(0)
        return [
            FlexibleDateOffer(
                departure_date=query.start_date,
                return_date=query.start_date + timedelta(days=query.min_nights),
                price=price,
                currency=query.currency,
            )
        ]


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
