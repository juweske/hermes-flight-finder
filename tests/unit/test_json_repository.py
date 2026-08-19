import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from hermes_flight_finder.models import (
    ItineraryWarning,
    MaxStops,
    PriceObservation,
    QualityStatus,
    WarningSeverity,
    Watch,
)
from hermes_flight_finder.storage import JsonWatchRepository, StateCorruptError


def _watch() -> Watch:
    return Watch(
        id="ham-nce-test",
        origin="HAM",
        destination="NCE",
        start_date=date.today() + timedelta(days=5),
        end_date=date.today() + timedelta(days=35),
        min_nights=2,
        max_nights=5,
        max_stops=MaxStops.NON_STOP,
        target_price=Decimal("90"),
        drop_percent=Decimal("20"),
        created_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )


def test_repository_persists_watches_across_instances(tmp_path: Path) -> None:
    repository = JsonWatchRepository(tmp_path)
    watch = _watch()

    repository.save(watch)

    reloaded = JsonWatchRepository(tmp_path)
    assert reloaded.get(watch.id) == watch


def test_repository_deletes_watches(tmp_path: Path) -> None:
    repository = JsonWatchRepository(tmp_path)
    watch = _watch()
    repository.save(watch)

    assert repository.delete(watch.id) is True
    assert repository.delete(watch.id) is False
    assert repository.list() == []


def test_repository_reports_corrupt_state(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text("not json", encoding="utf-8")

    with pytest.raises(StateCorruptError, match="corrupt"):
        JsonWatchRepository(tmp_path).list()


def test_repository_preserves_observation_source(tmp_path: Path) -> None:
    repository = JsonWatchRepository(tmp_path)
    observation = PriceObservation(
        checked_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        watch_id="ham-nce-test",
        price=Decimal("89"),
        currency="EUR",
        departure_date=date(2026, 9, 18),
        return_date=date(2026, 9, 21),
        source="serpapi",
        quality_status=QualityStatus.AVOID,
        warnings=(
            ItineraryWarning(
                code="overnight_layover",
                severity=WarningSeverity.SEVERE,
                message="Journey 1 includes an overnight layover.",
                journey=1,
            ),
        ),
    )

    repository.record_observation(observation)

    assert JsonWatchRepository(tmp_path).list_observations(observation.watch_id) == [observation]


def test_repository_defaults_legacy_observation_source_to_fli(tmp_path: Path) -> None:
    (tmp_path / "history.json").write_text(
        json.dumps(
            {
                "observations": [
                    {
                        "checked_at": "2026-08-15T12:00:00+00:00",
                        "watch_id": "ham-nce-test",
                        "price": "89",
                        "currency": "EUR",
                        "departure_date": "2026-09-18",
                        "return_date": "2026-09-21",
                        "airlines": [],
                        "stops": 0,
                    }
                ],
                "alerts": [],
            }
        ),
        encoding="utf-8",
    )

    observations = JsonWatchRepository(tmp_path).list_observations("ham-nce-test")

    assert observations[0].source == "fli"
    assert observations[0].quality_status == QualityStatus.ACCEPTABLE
    assert observations[0].warnings == ()
