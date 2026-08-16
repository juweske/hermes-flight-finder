"""Provider boundary for retrieving normalized flight offers."""

from __future__ import annotations

from typing import Protocol

from hermes_flight_tracker.models import (
    FlexibleDateOffer,
    FlexibleSearchQuery,
    FlightOffer,
    FlightQuery,
)


class ProviderError(Exception):
    """A flight provider could not complete a request safely."""


class FlightProvider(Protocol):
    """Retrieve project-owned flight offers for a domain query."""

    def search(self, query: FlightQuery) -> list[FlightOffer]:
        """Search a specific trip."""
        ...

    def search_dates(self, query: FlexibleSearchQuery) -> list[FlexibleDateOffer]:
        """Search a range of round-trip dates and durations."""
        ...
