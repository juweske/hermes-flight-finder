"""Short-lived cache for successful flexible-date provider responses."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from hermes_flight_finder.config import get_data_dir
from hermes_flight_finder.models import FlexibleDateOffer, FlexibleSearchQuery


class DateSearchCache:
    """Keep successful calendar responses stable across immediate repeated searches."""

    def __init__(
        self,
        directory: Path | None = None,
        ttl: timedelta = timedelta(minutes=15),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._directory = directory or get_data_dir() / "cache" / "date-searches"
        self._ttl = ttl
        self._clock = clock or (lambda: datetime.now(UTC))
        self.last_hit_at: datetime | None = None

    def get(self, query: FlexibleSearchQuery) -> list[FlexibleDateOffer] | None:
        """Return a fresh cached result, treating invalid cache data as a miss."""
        try:
            payload = json.loads(self._path(query).read_text(encoding="utf-8"))
            saved_at = datetime.fromisoformat(payload["saved_at"])
            if self._clock() - saved_at > self._ttl:
                return None
            self.last_hit_at = saved_at
            return [
                FlexibleDateOffer(
                    departure_date=datetime.fromisoformat(item["departure_date"]).date(),
                    return_date=datetime.fromisoformat(item["return_date"]).date(),
                    price=Decimal(item["price"]),
                    currency=item["currency"],
                    booking_url=item["booking_url"],
                )
                for item in payload["offers"]
            ]
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def put(self, query: FlexibleSearchQuery, offers: list[FlexibleDateOffer]) -> None:
        """Atomically cache a non-empty successful response."""
        if not offers:
            return
        payload = {
            "saved_at": self._clock().isoformat(),
            "offers": [
                {
                    "departure_date": offer.departure_date.isoformat(),
                    "return_date": offer.return_date.isoformat(),
                    "price": str(offer.price),
                    "currency": offer.currency,
                    "booking_url": offer.booking_url,
                }
                for offer in offers
            ],
        }
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(dir=self._directory, prefix=".dates-")
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
                    json.dump(payload, temporary_file, separators=(",", ":"), sort_keys=True)
                os.replace(temporary_name, self._path(query))
            except BaseException:
                Path(temporary_name).unlink(missing_ok=True)
                raise
        except OSError:
            pass

    def _path(self, query: FlexibleSearchQuery) -> Path:
        serialized = json.dumps(
            {
                "origin": query.origin,
                "destination": query.destination,
                "start_date": query.start_date.isoformat(),
                "end_date": query.end_date.isoformat(),
                "min_nights": query.min_nights,
                "max_nights": query.max_nights,
                "cabin": query.cabin.value,
                "max_stops": query.max_stops.value,
                "passengers": query.passengers,
                "currency": query.currency,
                "airlines": query.airlines,
                "departure_window": query.departure_window,
                "origin_alternatives": query.origin_alternatives,
                "destination_alternatives": query.destination_alternatives,
                "return_origins": query.return_origins,
                "return_destinations": query.return_destinations,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        return self._directory / f"{digest}.json"
