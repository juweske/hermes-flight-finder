"""Provider boundary for retrieving normalized flight offers."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from hermes_flight_finder.models import (
    BookingOption,
    FlexibleDateOffer,
    FlexibleSearchQuery,
    FlightOffer,
    FlightQuery,
)


class ProviderErrorCode(StrEnum):
    """Stable, non-HTTP failure categories exposed by the CLI."""

    CONNECTION_FAILED = "connection_failed"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    REQUEST_REFUSED = "request_refused"
    NO_RESULTS = "no_results"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_RESPONSE = "invalid_response"


class ProviderError(Exception):
    """A flight provider could not complete a request safely."""

    def __init__(
        self,
        message: str,
        code: ProviderErrorCode = ProviderErrorCode.PROVIDER_UNAVAILABLE,
    ) -> None:
        super().__init__(message)
        self.code = code


class BookingOptionsUnavailable(ProviderError):
    """Vendor options failed after an exact itinerary handoff was created."""

    def __init__(self, message: str, selected_offer: FlightOffer) -> None:
        super().__init__(message, ProviderErrorCode.PROVIDER_UNAVAILABLE)
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
