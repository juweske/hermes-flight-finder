import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pytest import CaptureFixture

from hermes_flight_tracker.cli import main
from hermes_flight_tracker.models import (
    FlexibleDateOffer,
    FlexibleSearchQuery,
    FlightLeg,
    FlightOffer,
    FlightQuery,
)
from hermes_flight_tracker.storage import JsonWatchRepository


class _FakeProvider:
    def search(self, query: FlightQuery) -> list[FlightOffer]:
        departure = datetime(2026, 9, 18, 8, 0)
        return [
            FlightOffer(
                price=Decimal("89"),
                currency="EUR",
                duration_minutes=120,
                stops=0,
                legs=(
                    FlightLeg(
                        airline="EW",
                        flight_number="EW 123",
                        departure_airport="HAM",
                        arrival_airport="NCE",
                        departure_at=departure,
                        arrival_at=departure + timedelta(minutes=120),
                        duration_minutes=120,
                    ),
                ),
            )
        ]

    def search_dates(self, query: FlexibleSearchQuery) -> list[FlexibleDateOffer]:
        return [
            FlexibleDateOffer(
                departure_date=date(2026, 9, 18),
                return_date=date(2026, 9, 21),
                price=Decimal("79"),
                currency="EUR",
            )
        ]


def test_help_exits_successfully(capsys: CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "hermes-flights" in captured.out


def test_watch_help_exits_successfully(capsys: CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["watch", "--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "watch commands" in captured.out


def test_doctor_validates_an_isolated_state_directory(
    capsys: CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_FLIGHT_TRACKER_DATA_DIR", str(tmp_path))

    exit_code = main(
        ["doctor", "--json"], provider=_FakeProvider(), repository=JsonWatchRepository(tmp_path)
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert {check["name"] for check in payload["checks"]} == {
        "flight_provider",
        "data_directory",
        "local_state",
    }


def test_search_writes_stable_json(capsys: CaptureFixture[str]) -> None:
    exit_code = main(
        [
            "search",
            "--from",
            "HAM",
            "--to",
            "NCE",
            "--departure",
            "2026-09-18",
            "--json",
        ],
        provider=_FakeProvider(),
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["offers"][0]["price"] == "89"
    assert payload["offers"][0]["legs"][0]["departure_airport"] == "HAM"


def test_dates_writes_stable_json(capsys: CaptureFixture[str]) -> None:
    exit_code = main(
        [
            "dates",
            "--from",
            "HAM",
            "--to",
            "NCE",
            "--start",
            "2026-09-01",
            "--end",
            "2026-10-01",
            "--min-nights",
            "2",
            "--max-nights",
            "5",
            "--json",
        ],
        provider=_FakeProvider(),
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["offers"][0]["nights"] == 3
    assert payload["offers"][0]["price"] == "79"


def test_watch_lifecycle_writes_stable_json(capsys: CaptureFixture[str], tmp_path: Path) -> None:
    repository = JsonWatchRepository(tmp_path)
    add_exit_code = main(
        [
            "watch",
            "add",
            "--id",
            "ham-nce-weekend",
            "--from",
            "HAM",
            "--to",
            "NCE",
            "--start",
            "2026-09-01",
            "--end",
            "2026-10-01",
            "--min-nights",
            "2",
            "--max-nights",
            "5",
            "--nonstop",
            "--target-price",
            "90",
            "--json",
        ],
        repository=repository,
    )

    assert add_exit_code == 0
    assert json.loads(capsys.readouterr().out)["watch"]["id"] == "ham-nce-weekend"

    show_exit_code = main(["watch", "show", "ham-nce-weekend", "--json"], repository=repository)
    assert show_exit_code == 0
    assert json.loads(capsys.readouterr().out)["watch"]["target_price"] == "90"

    remove_exit_code = main(["watch", "remove", "ham-nce-weekend", "--json"], repository=repository)
    assert remove_exit_code == 0
    assert json.loads(capsys.readouterr().out)["removed_id"] == "ham-nce-weekend"
