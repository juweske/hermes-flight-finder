from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from hermes_flight_tracker.models import MaxStops, Watch
from hermes_flight_tracker.storage import JsonWatchRepository, StateCorruptError


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
