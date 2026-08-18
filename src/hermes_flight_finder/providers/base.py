"""Provider boundary for retrieving normalized flight offers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hermes_flight_finder.models import (
    BookingOption,
    FlexibleDateOffer,
    FlexibleSearchQuery,
    FlightOffer,
    FlightQuery,
)


class ProviderError(Exception):
    """A flight provider could not complete a request safely."""


class BookingOptionsUnavailable(ProviderError):
    """Vendor options failed after an exact itinerary handoff was created."""

    def __init__(self, message: str, selected_offer: FlightOffer) -> None:
        super().__init__(message)
        self.selected_offer = selected_offer


@runtime_checkable
class BookingProvider(Protocol):
    """Retrieve current booking handoffs for a selected search result."""

    def booking_options(
        self, query: FlightQuery, offer_index: int
    ) -> tuple[FlightOffer, list[BookingOption]]:
        """Return the selected offer and current vendor booking options."""
        ...


class FlightProvider(Protocol):
    """Retrieve project-owned flight offers for a domain query."""

    def search(self, query: FlightQuery) -> list[FlightOffer]:
        """Search a specific trip."""
        ...

    def search_dates(self, query: FlexibleSearchQuery) -> list[FlexibleDateOffer]:
        """Search a range of round-trip dates and durations."""
        ...
