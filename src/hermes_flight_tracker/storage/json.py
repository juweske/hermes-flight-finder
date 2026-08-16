"""Versioned JSON implementation of the watch repository."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

from hermes_flight_tracker.config import get_data_dir
from hermes_flight_tracker.models import AlertRecord, Cabin, MaxStops, PriceObservation, Watch
from hermes_flight_tracker.storage.base import StateCorruptError, WatchRepository

_STATE_VERSION = 1


class JsonWatchRepository(WatchRepository):
    """Persist watches in a local, atomically written JSON document."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or get_data_dir()
        self._state_path = self._data_dir / "state.json"
        self._history_path = self._data_dir / "history.json"

    def list(self) -> list[Watch]:
        """List all saved watches."""
        return self._load()

    def get(self, watch_id: str) -> Watch | None:
        """Return a saved watch or ``None`` when it is absent."""
        return next((watch for watch in self._load() if watch.id == watch_id), None)

    def save(self, watch: Watch) -> None:
        """Create or replace a watch by id."""
        watches = self._load()
        for index, existing in enumerate(watches):
            if existing.id == watch.id:
                watches[index] = watch
                break
        else:
            watches.append(watch)
        self._write(watches)

    def delete(self, watch_id: str) -> bool:
        """Delete a watch by id."""
        watches = self._load()
        remaining = [watch for watch in watches if watch.id != watch_id]
        if len(remaining) == len(watches):
            return False
        self._write(remaining)
        observations, alerts = self._load_history()
        self._write_history(
            [item for item in observations if item.watch_id != watch_id],
            [item for item in alerts if item.watch_id != watch_id],
        )
        return True

    def list_observations(self, watch_id: str) -> list[PriceObservation]:
        observations, _ = self._load_history()
        return [item for item in observations if item.watch_id == watch_id]

    def record_observation(self, observation: PriceObservation) -> None:
        observations, alerts = self._load_history()
        observations.append(observation)
        self._write_history(observations, alerts)

    def list_alerts(self, watch_id: str) -> list[AlertRecord]:
        _, alerts = self._load_history()
        return [item for item in alerts if item.watch_id == watch_id]

    def record_alert(self, alert: AlertRecord) -> None:
        observations, alerts = self._load_history()
        alerts.append(alert)
        self._write_history(observations, alerts)

    def _load_history(self) -> tuple[list[PriceObservation], list[AlertRecord]]:
        if not self._history_path.exists():
            return ([], [])
        try:
            decoded = json.loads(self._history_path.read_text(encoding="utf-8"))
            if not isinstance(decoded, dict):
                raise ValueError("history must be an object")
            raw = cast(dict[str, object], decoded)
            observations = [
                _observation_from_dict(item) for item in _object_list(raw, "observations")
            ]
            alerts = [_alert_from_dict(item) for item in _object_list(raw, "alerts")]
            return (observations, alerts)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise StateCorruptError("Local history file is corrupt") from error

    def _write_history(
        self, observations: list[PriceObservation], alerts: list[AlertRecord]
    ) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "observations": [_observation_as_dict(item) for item in observations],
            "alerts": [_alert_as_dict(item) for item in alerts],
        }
        _atomic_write(self._history_path, json.dumps(payload, indent=2, sort_keys=True))

    def _load(self) -> list[Watch]:
        if not self._state_path.exists():
            return []
        try:
            decoded = json.loads(self._state_path.read_text(encoding="utf-8"))
            if not isinstance(decoded, dict):
                raise ValueError("unsupported state document")
            document = cast(dict[str, object], decoded)
            if document.get("version") != _STATE_VERSION:
                raise ValueError("unsupported state document")
            raw_watches = document.get("watches")
            if not isinstance(raw_watches, list):
                raise ValueError("watches must be a list")
            watches: list[Watch] = []
            for raw_watch in cast(list[object], raw_watches):
                if not isinstance(raw_watch, dict):
                    raise ValueError("watch must be an object")
                watches.append(_watch_from_dict(cast(dict[str, object], raw_watch)))
            return watches
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise StateCorruptError("Local state file is corrupt") from error

    def _write(self, watches: list[Watch]) -> None:
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(
                {
                    "version": _STATE_VERSION,
                    "watches": [_watch_as_dict(watch) for watch in watches],
                },
                indent=2,
                sort_keys=True,
            )
            _atomic_write(self._state_path, payload)
        except OSError as error:
            raise StateCorruptError("Local state file could not be written") from error


def _watch_as_dict(watch: Watch) -> dict[str, object]:
    return {
        "id": watch.id,
        "origin": watch.origin,
        "destination": watch.destination,
        "start_date": watch.start_date.isoformat(),
        "end_date": watch.end_date.isoformat(),
        "min_nights": watch.min_nights,
        "max_nights": watch.max_nights,
        "cabin": watch.cabin.value,
        "max_stops": watch.max_stops.value,
        "passengers": watch.passengers,
        "currency": watch.currency,
        "airlines": list(watch.airlines),
        "departure_window": list(watch.departure_window) if watch.departure_window else None,
        "target_price": str(watch.target_price) if watch.target_price is not None else None,
        "drop_percent": str(watch.drop_percent) if watch.drop_percent is not None else None,
        "created_at": watch.created_at.isoformat(),
    }


def _watch_from_dict(raw: dict[str, object]) -> Watch:
    departure_window = raw.get("departure_window")
    return Watch(
        id=_required_str(raw, "id"),
        origin=_required_str(raw, "origin"),
        destination=_required_str(raw, "destination"),
        start_date=datetime.fromisoformat(_required_str(raw, "start_date")).date(),
        end_date=datetime.fromisoformat(_required_str(raw, "end_date")).date(),
        min_nights=_required_int(raw, "min_nights"),
        max_nights=_required_int(raw, "max_nights"),
        cabin=Cabin(_required_str(raw, "cabin")),
        max_stops=MaxStops(_required_str(raw, "max_stops")),
        passengers=_required_int(raw, "passengers"),
        currency=_required_str(raw, "currency"),
        airlines=tuple(_required_str_list(raw, "airlines")),
        departure_window=_departure_window_from_raw(departure_window),
        target_price=_optional_decimal(raw.get("target_price")),
        drop_percent=_optional_decimal(raw.get("drop_percent")),
        created_at=datetime.fromisoformat(_required_str(raw, "created_at")),
    )


def _required_str(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _required_int(raw: dict[str, object], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


def _required_str_list(raw: dict[str, object], key: str) -> list[str]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list of strings")
    values = cast(list[object], value)
    if not all(isinstance(item, str) for item in values):
        raise ValueError(f"{key} must be a list of strings")
    return [cast(str, item) for item in values]


def _departure_window_from_raw(value: object) -> tuple[int, int] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("departure_window must be a two-item integer list")
    hours = cast(list[object], value)
    if len(hours) != 2 or not all(isinstance(hour, int) for hour in hours):
        raise ValueError("departure_window must be a two-item integer list")
    return (cast(int, hours[0]), cast(int, hours[1]))


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("decimal values must be strings")
    return Decimal(value)


def _object_list(raw: dict[str, object], key: str) -> list[dict[str, object]]:
    value = raw.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    result: list[dict[str, object]] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            raise ValueError(f"{key} items must be objects")
        result.append(cast(dict[str, object], item))
    return result


def _observation_as_dict(item: PriceObservation) -> dict[str, object]:
    return {
        "checked_at": item.checked_at.isoformat(),
        "watch_id": item.watch_id,
        "price": str(item.price),
        "currency": item.currency,
        "departure_date": item.departure_date.isoformat(),
        "return_date": item.return_date.isoformat(),
        "airlines": list(item.airlines),
        "stops": item.stops,
    }


def _observation_from_dict(raw: dict[str, object]) -> PriceObservation:
    stops = raw.get("stops")
    if stops is not None and (not isinstance(stops, int) or isinstance(stops, bool)):
        raise ValueError("stops must be an integer")
    return PriceObservation(
        datetime.fromisoformat(_required_str(raw, "checked_at")),
        _required_str(raw, "watch_id"),
        Decimal(_required_str(raw, "price")),
        _required_str(raw, "currency"),
        datetime.fromisoformat(_required_str(raw, "departure_date")).date(),
        datetime.fromisoformat(_required_str(raw, "return_date")).date(),
        tuple(_required_str_list(raw, "airlines")),
        stops,
    )


def _alert_as_dict(item: AlertRecord) -> dict[str, object]:
    return {
        "watch_id": item.watch_id,
        "price": str(item.price),
        "departure_date": item.departure_date.isoformat(),
        "return_date": item.return_date.isoformat(),
        "alerted_at": item.alerted_at.isoformat(),
    }


def _alert_from_dict(raw: dict[str, object]) -> AlertRecord:
    return AlertRecord(
        _required_str(raw, "watch_id"),
        Decimal(_required_str(raw, "price")),
        datetime.fromisoformat(_required_str(raw, "departure_date")).date(),
        datetime.fromisoformat(_required_str(raw, "return_date")).date(),
        datetime.fromisoformat(_required_str(raw, "alerted_at")),
    )


def _atomic_write(path: Path, payload: str) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix="state-", suffix=".tmp", delete=False
    ) as temporary_file:
        temporary_file.write(payload)
        temporary_file.flush()
        os.fsync(temporary_file.fileno())
        temporary_path = Path(temporary_file.name)
    temporary_path.replace(path)
