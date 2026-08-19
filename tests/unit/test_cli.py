import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pytest import CaptureFixture

from hermes_flight_finder.cli import main
from hermes_flight_finder.models import (
    BookingOption,
    FlexibleDateOffer,
    FlexibleSearchQuery,
    FlightLeg,
    FlightOffer,
    FlightQuery,
    PriceObservation,
    Watch,
)
from hermes_flight_finder.providers import BookingOptionsUnavailable
from hermes_flight_finder.storage import JsonWatchRepository


class _FakeProvider:
    def search(self, query: FlightQuery) -> list[FlightOffer]:
        departure = datetime(2026, 9, 18, 8, 0)
        return [
            FlightOffer(
                price=Decimal("89"),
                currency="EUR",
                duration_minutes=120,
                stops=0,
                booking_url="https://www.google.com/travel/flights/booking?tfs=TEST",
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

    def booking_options(
        self, query: FlightQuery, offer_index: int
    ) -> tuple[FlightOffer, list[BookingOption]]:
        offer = self.search(query)[offer_index]
        return (
            offer,
            [
                BookingOption(
                    vendor_name="Example Air",
                    is_airline_direct=True,
                    price=Decimal("89"),
                    currency="EUR",
                    fare_name="Economy Light",
                    booking_url="https://book.example.test/offer",
                    google_click_url="https://google.example.test/offer",
                )
            ],
        )

    def search_dates(self, query: FlexibleSearchQuery) -> list[FlexibleDateOffer]:
        return [
            FlexibleDateOffer(
                departure_date=date(2026, 9, 18),
                return_date=date(2026, 9, 21),
                price=Decimal("79"),
                currency="EUR",
                booking_url=(
                    "https://www.google.com/travel/flights?q=HAM+NCE+2026-09-18+2026-09-21"
                ),
            )
        ]


class _UnavailableBookingProvider(_FakeProvider):
    def booking_options(
        self, query: FlightQuery, offer_index: int
    ) -> tuple[FlightOffer, list[BookingOption]]:
        raise BookingOptionsUnavailable(
            "Vendor booking options are temporarily unavailable",
            self.search(query)[offer_index],
        )


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
    monkeypatch.setenv("HERMES_FLIGHT_FINDER_DATA_DIR", str(tmp_path))

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
    assert payload["offers"][0]["booking_url"].startswith("https://www.google.com/travel/flights?")


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


def test_watch_history_reports_lowest_price_since_tracking_started(
    capsys: CaptureFixture[str], tmp_path: Path
) -> None:
    repository = JsonWatchRepository(tmp_path)
    watch = Watch(
        id="ham-nce-history",
        origin="HAM",
        destination="NCE",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 10, 1),
        min_nights=2,
        max_nights=5,
    )
    repository.save(watch)
    repository.record_observation(
        PriceObservation(
            checked_at=datetime(2026, 8, 15, 9, 0, tzinfo=UTC),
            watch_id=watch.id,
            price=Decimal("120"),
            currency="EUR",
            departure_date=date(2026, 9, 18),
            return_date=date(2026, 9, 21),
        )
    )
    repository.record_observation(
        PriceObservation(
            checked_at=datetime(2026, 8, 16, 9, 0, tzinfo=UTC),
            watch_id=watch.id,
            price=Decimal("95"),
            currency="EUR",
            departure_date=date(2026, 9, 18),
            return_date=date(2026, 9, 21),
        )
    )

    exit_code = main(["watch", "history", watch.id, "--json"], repository=repository)

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {
        "observation_count": 2,
        "tracking_started_at": "2026-08-15T09:00:00+00:00",
        "latest_price": "95",
        "currency": "EUR",
        "lowest_price": "95",
        "lowest_observed_at": "2026-08-16T09:00:00+00:00",
        "latest_is_lowest_since_tracking_started": True,
        "sources": ["fli"],
    }
    assert payload["observations"][0]["source"] == "fli"


def test_booking_options_returns_current_vendor_handoff(capsys: CaptureFixture[str]) -> None:
    exit_code = main(
        [
            "booking",
            "options",
            "--from",
            "HAM",
            "--to",
            "NCE",
            "--departure",
            "2026-09-18",
            "--return",
            "2026-09-21",
            "--offer",
            "1",
            "--json",
        ],
        provider=_FakeProvider(),
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["selected_offer"]["price"] == "89"
    assert payload["booking_handoff_url"] == (
        "https://www.google.com/travel/flights/booking?tfs=TEST"
    )
    assert payload["google_flights_search_url"] == (
        "https://www.google.com/travel/flights?hl=en&curr=EUR&"
        "q=Flights+to+NCE+from+HAM+on+2026-09-18+returning+2026-09-21"
    )
    assert payload["booking_options"] == [
        {
            "vendor_name": "Example Air",
            "is_airline_direct": True,
            "price": "89",
            "currency": "EUR",
            "fare_name": "Economy Light",
            "booking_url": "https://book.example.test/offer",
            "google_click_url": "https://google.example.test/offer",
            "handoff_url": "https://book.example.test/offer",
        }
    ]


def test_booking_options_keeps_exact_handoff_when_vendor_options_fail(
    capsys: CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "booking",
            "options",
            "--from",
            "HAM",
            "--to",
            "NCE",
            "--departure",
            "2026-09-18",
            "--return",
            "2026-09-21",
            "--offer",
            "1",
            "--json",
        ],
        provider=_UnavailableBookingProvider(),
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["booking_handoff_url"] == (
        "https://www.google.com/travel/flights/booking?tfs=TEST"
    )
    assert payload["booking_options"] == []
    assert payload["booking_options_warning"] == (
        "Vendor booking options are temporarily unavailable"
    )
