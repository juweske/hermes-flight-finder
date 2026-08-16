"""Provider-independent flight search operations."""

from __future__ import annotations

from hermes_flight_finder.models import FlightOffer, FlightQuery
from hermes_flight_finder.providers.base import FlightProvider


class SearchService:
    """Search and sort offers returned by a provider."""

    def __init__(self, provider: FlightProvider) -> None:
        self._provider = provider

    def search(self, query: FlightQuery) -> list[FlightOffer]:
        """Return priced offers first, ordered from least to most expensive."""
        offers = self._provider.search(query)
        return sorted(
            offers,
            key=lambda offer: (offer.price is None, offer.price or 0, offer.duration_minutes),
        )
